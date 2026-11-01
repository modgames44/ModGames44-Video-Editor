"""Exportación no destructiva de secuencias V1-V3 y A1-A3 con FFmpeg.

Se generan filtros por clip y una composición de la secuencia completa.
No realiza render de fotogramas clave animados de zoom/máscara; se advierte.
"""
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re
import subprocess
from effects.model import merged_effects, censor_mask, zoom_state
from effects.audio import audio_filter_chain
from exporter.hardware import select_encoder
from timeline.fades import video_fade_filters, audio_fade_filters


@dataclass(frozen=True)
class ExportProfile:
    title: str
    codec: str
    extension: str
    width: int
    height: int
    fps: int
    bitrate: str


PROFILES = {
    'YouTube 1080p 30': ExportProfile('YouTube 1080p 30', 'h264', 'mp4', 1920, 1080, 30, '12M'),
    'YouTube 1080p 60': ExportProfile('YouTube 1080p 60', 'h264', 'mp4', 1920, 1080, 60, '16M'),
    'YouTube 1440p 60': ExportProfile('YouTube 1440p 60', 'h264', 'mp4', 2560, 1440, 60, '24M'),
    'YouTube 4K 60': ExportProfile('YouTube 4K 60', 'h264', 'mp4', 3840, 2160, 60, '48M'),
    'MP4 H.265 1080p': ExportProfile('MP4 H.265 1080p', 'hevc', 'mp4', 1920, 1080, 30, '8M'),
    'MP4 AV1 1080p': ExportProfile('MP4 AV1 1080p', 'av1', 'mp4', 1920, 1080, 30, '6M'),
    'MOV ProRes 422 1080p': ExportProfile('MOV ProRes 422 1080p', 'prores', 'mov', 1920, 1080, 30, '0'),
    'WebM VP9 1080p': ExportProfile('WebM VP9 1080p', 'vp9', 'webm', 1920, 1080, 30, '8M'),
}


def validate_project(clips):
    if not clips:
        raise ValueError('La Timeline está vacía')
    for c in clips:
        if not Path(c['path']).is_file():
            raise FileNotFoundError('No se encontró el medio: ' + c['path'])
        if c.get('kind', 'video') not in ('video', 'audio'):
            raise ValueError('Clip con tipo desconocido')
        for key in ('start_ms', 'in_ms', 'duration_ms'):
            value = float(c[key])
            if not isfinite(value) or value < 0:
                raise ValueError(f'Clip con {key} inválido')
        if c['duration_ms'] < 1:
            raise ValueError('Clip de duración nula')
        speed = float(c.get('speed', 1))
        if not isfinite(speed) or not .25 <= speed <= 4:
            raise ValueError('Velocidad de clip incompatible')
    return max(c['start_ms'] + c['duration_ms'] for c in clips)


def _s(value):
    return f'{float(value):.6f}'.rstrip('0').rstrip('.') or '0'


def _video_filters(clip, profile, warnings):
    effects = merged_effects(clip.get('effects'))
    filters = [f'fps={profile.fps}',
               f'scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease',
               f'pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2:black',
               'setsar=1']
    zoom = effects['zoom']
    if zoom['enabled']:
        if len(zoom.get('keys', [])) > 1:
            warnings.append('El zoom animado se exportará con su valor estático (sin animación).')
        z = zoom_state(effects, float(clip.get('in_ms', 0)))
        w, h = profile.width, profile.height
        cw = max(2, round(w / z['scale'] / 2) * 2)
        ch = max(2, round(h / z['scale'] / 2) * 2)
        x = max(0, min(w - cw, round(z['cx'] * w - cw / 2)))
        y = max(0, min(h - ch, round(z['cy'] * h - ch / 2)))
        filters += [f'crop={cw}:{ch}:{x}:{y}', f'scale={w}:{h}']
    color = effects['color']
    if color['enabled']:
        brightness = max(-1, min(1, float(color['brightness']) / 100))
        contrast = max(0, min(2, float(color['contrast'])))
        saturation = max(0, min(3, float(color['saturation'])))
        if color['grayscale']:
            saturation = 0
        filters.append(f'eq=brightness={_s(brightness)}:contrast={_s(contrast)}:saturation={_s(saturation)}')
        if color['mirror']:
            filters.append('hflip')
    return filters, effects


def _masked_censor(graph, stream, clip, effects, profile, index, warnings):
    c = effects['censor']
    if not c['enabled']:
        return stream
    if len(c.get('keys', [])) > 1:
        warnings.append('La máscara animada se exportará en su posición estática inicial.')
    if float(c.get('feather',0)) > 0:
        warnings.append('El borde suave de censura no se aplica aún a la exportación.')
    m = censor_mask(effects, float(clip.get('in_ms', 0)))
    w, h = profile.width, profile.height
    mw = max(2, min(w, round(w * m['w'] / 2) * 2))
    mh = max(2, min(h, round(h * m['h'] / 2) * 2))
    x = max(0, min(w - mw, round(m['x'] * w)))
    y = max(0, min(h - mh, round(m['y'] * h)))
    graph.append(f'[{stream}]split=2[clean{index}][rawblur{index}]')
    if c['mode'] == 'mosaic':
        pixel = max(2, min(80, int(c['strength'])))
        inner = f'crop={mw}:{mh}:{x}:{y},scale={max(2,mw//pixel)}:{max(2,mh//pixel)}:flags=neighbor,scale={mw}:{mh}:flags=neighbor'
    else:
        blur = max(1, min(40, int(c['strength']) // 2))
        inner = f'crop={mw}:{mh}:{x}:{y},boxblur={blur}:1'
    graph.append(f'[rawblur{index}]{inner}[blurred{index}]')
    graph.append(f'[clean{index}][blurred{index}]overlay={x}:{y}:shortest=1[censored{index}]')
    return f'censored{index}'


def build_export_command(clips, profile, dest, encoder_option, *, has_audio=True):
    """Devuelve (argv, advertencias) sin ejecutar herramientas externas.

    Los segmentos se sitúan en la Timeline usando setpts y adelay.
    Los solapamientos de V1/V2/V3 se componen por prioridad de pista.
    """
    duration_ms = validate_project(clips)
    duration = duration_ms / 1000
    ffmpeg, encoder = encoder_option['ffmpeg'], encoder_option['encoder']
    args = [ffmpeg, '-hide_banner', '-y', '-nostdin', '-loglevel', 'error', '-stats_period', '0.25',
            '-progress', 'pipe:1', '-f', 'lavfi', '-i',
            f'color=c=black:s={profile.width}x{profile.height}:r={profile.fps}:d={_s(duration)}',
            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    # Indices 0: base de vídeo; 1: silencio para preservar espacios vacíos.
    images = {'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}
    for clip in clips:
        if Path(clip['path']).suffix.lower() in images:
            args += ['-loop','1','-framerate',str(profile.fps)]
        args += ['-i', clip['path']]
    graph, warnings = [], []
    video = sorted(((idx, c) for idx, c in enumerate(clips, start=2) if c.get('kind') == 'video'),
                   key=lambda pair: (int(pair[1].get('track', 0)), pair[0]))
    audio = [(idx,c) for idx,c in enumerate(clips,start=2) if c.get('kind') == 'audio']
    # Base de video. Usar colas transparentes para clips con huecos y capas.
    v_prev = '0:v'
    for k, (idx, c) in enumerate(video):
        start = c['in_ms'] / 1000
        length_src = c['duration_ms'] * float(c.get('speed', 1)) / 1000
        speed = float(c.get('speed', 1))
        vf, fx = _video_filters(c, profile, warnings)
        part = f'vpart{k}'
        graph.append(f'[{idx}:v:0]trim=start={_s(start)}:duration={_s(length_src)},'
                     f'setpts=(PTS-STARTPTS)/{_s(speed)},' + ','.join(vf) + f'[{part}]')
        part = _masked_censor(graph, part, c, fx, profile, k, warnings)
        # Desvanecimiento al final de la cadena, también sobre la censura:
        # si hay capas inferiores, alpha=1 deja verlas durante el fundido.
        fade_filters=video_fade_filters(c)
        if fade_filters:
            graph.append(f'[{part}]' + ','.join(fade_filters) + f'[fade{k}]')
            part=f'fade{k}'
        # Desplazamiento a posición absoluta de la secuencia en PTS.
        graph.append(f'[{part}]setpts=PTS+{_s(c["start_ms"]/1000)}/TB[vt{k}]')
        output = f'vo{k}'
        graph.append(f'[{v_prev}][vt{k}]overlay=0:0:eof_action=pass:shortest=0:repeatlast=0[{output}]')
        v_prev = output
    if video:
        graph.append(f'[{v_prev}]trim=duration={_s(duration)},setpts=PTS-STARTPTS[vout]')
    else:
        graph.append(f'[0:v]trim=duration={_s(duration)},setpts=PTS-STARTPTS[vout]')

    a_parts = []
    for k, (idx, c) in enumerate(audio):
        source_start = c['in_ms'] / 1000
        source_length = c['duration_ms'] * float(c.get('speed',1)) / 1000
        a_fx = audio_filter_chain(c.get('audio_fx'), c.get('speed',1))
        name = f'a{k}'
        chain = (f'[{idx}:a:0]atrim=start={_s(source_start)}:duration={_s(source_length)},'
                 'asetpts=PTS-STARTPTS')
        if a_fx:
            chain += ',' + ','.join(a_fx)
        fades=audio_fade_filters(c)
        if fades:
            chain += ',' + ','.join(fades)
        chain += f',aresample=48000,aformat=channel_layouts=stereo,adelay={int(c["start_ms"])}:all=1[{name}]'
        graph.append(chain)
        a_parts.append(name)
    graph.append(f'[1:a]atrim=duration={_s(duration)},asetpts=PTS-STARTPTS[abase]')
    audio_inputs = '[abase]' + ''.join(f'[{p}]' for p in a_parts)
    graph.append(f'{audio_inputs}amix=inputs={len(a_parts)+1}:duration=longest:normalize=0,'
                 f'atrim=duration={_s(duration)},alimiter=limit=0.95[aout]')
    args += ['-filter_complex', ';'.join(graph), '-map', '[vout]', '-map', '[aout]',
             '-c:v', encoder, '-r', str(profile.fps)]
    if encoder.startswith('libx264') or encoder.startswith('libx265'):
        args += ['-preset', 'medium']
    if encoder == 'prores_ks':
        args += ['-profile:v', '3', '-pix_fmt', 'yuv422p10le']
    else:
        args += ['-pix_fmt', 'yuv420p']
    if profile.bitrate != '0':
        args += ['-b:v', profile.bitrate]
    if profile.extension == 'webm':
        args += ['-c:a', 'libopus', '-b:a', '160k']
    else:
        args += ['-c:a', 'aac' if profile.extension == 'mp4' else 'pcm_s16le', '-b:a', '192k']
    if profile.extension == 'mp4':
        args += ['-movflags', '+faststart']
    args += ['-t', _s(duration), str(dest)]
    return args, list(dict.fromkeys(warnings))
