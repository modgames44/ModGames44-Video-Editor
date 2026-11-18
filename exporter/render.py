"""Exportación no destructiva de secuencias V1-V3 y A1-A3 con FFmpeg.

Se generan filtros por clip y una composición de la secuencia completa.
Incluye render de zoom y máscara animados mediante filtros FFmpeg.
"""
from dataclasses import dataclass, replace
from exporter.encoder_settings import video_codec_args
from math import isfinite
from pathlib import Path
from effects.model import merged_effects, censor_mask, zoom_state, is_valid_speed
from effects.audio import audio_filter_chain
from timeline.fades import video_fade_filters, audio_fade_filters
from exporter.animated_effects import zoompan_filter, mask_geq
from effects.title_overlay import render_title_png, default_style
from effects.image_overlay import render_image_png
from effects.keyframe_expressions import ffmpeg_expression


@dataclass(frozen=True)
class ExportProfile:
    title: str
    codec: str
    extension: str
    width: int
    height: int
    fps: int
    bitrate: str          # techo de tasa (calidad constante) o tasa fija
    ten_bit: bool = False # HEVC/AV1 en 10 bits: menos bandas en degradados


# Las tasas son el TECHO de la calidad constante: YouTube recomprime todo,
# así que conviene subirle más calidad que su mínimo recomendado.
PROFILES = {
    'YouTube 1080p 30': ExportProfile('YouTube 1080p 30', 'h264', 'mp4', 1920, 1080, 30, '24M'),
    'YouTube 1080p 60': ExportProfile('YouTube 1080p 60', 'h264', 'mp4', 1920, 1080, 60, '40M'),
    'YouTube 1440p 60': ExportProfile('YouTube 1440p 60', 'h264', 'mp4', 2560, 1440, 60, '60M'),
    'YouTube 4K 60': ExportProfile('YouTube 4K 60', 'h264', 'mp4', 3840, 2160, 60, '100M'),
    'Shorts / TikTok 1080x1920 30': ExportProfile('Shorts / TikTok 1080x1920 30', 'h264', 'mp4', 1080, 1920, 30, '24M'),
    'Shorts / TikTok 1080x1920 60': ExportProfile('Shorts / TikTok 1080x1920 60', 'h264', 'mp4', 1080, 1920, 60, '35M'),
    'MP4 H.265 1080p': ExportProfile('MP4 H.265 1080p', 'hevc', 'mp4', 1920, 1080, 30, '16M'),
    'MP4 H.265 1080p 60': ExportProfile('MP4 H.265 1080p 60', 'hevc', 'mp4', 1920, 1080, 60, '25M'),
    'MP4 H.265 10-bit 1440p 60': ExportProfile('MP4 H.265 10-bit 1440p 60', 'hevc', 'mp4', 2560, 1440, 60, '45M', True),
    'MP4 H.265 10-bit 4K 60': ExportProfile('MP4 H.265 10-bit 4K 60', 'hevc', 'mp4', 3840, 2160, 60, '80M', True),
    'MP4 AV1 1080p': ExportProfile('MP4 AV1 1080p', 'av1', 'mp4', 1920, 1080, 30, '12M'),
    'MP4 AV1 1080p 60': ExportProfile('MP4 AV1 1080p 60', 'av1', 'mp4', 1920, 1080, 60, '20M'),
    'MP4 AV1 10-bit 1440p 60': ExportProfile('MP4 AV1 10-bit 1440p 60', 'av1', 'mp4', 2560, 1440, 60, '35M', True),
    'MP4 AV1 10-bit 4K 60': ExportProfile('MP4 AV1 10-bit 4K 60', 'av1', 'mp4', 3840, 2160, 60, '60M', True),
    'MOV ProRes 422 1080p': ExportProfile('MOV ProRes 422 1080p', 'prores', 'mov', 1920, 1080, 30, '0'),
    'WebM VP9 1080p': ExportProfile('WebM VP9 1080p', 'vp9', 'webm', 1920, 1080, 30, '8M'),
}


def validate_project(clips):
    if not clips:
        raise ValueError('La Timeline está vacía')
    for c in clips:
        if c.get('kind', 'video') not in ('title','subtitle') and not Path(c['path']).is_file():
            raise FileNotFoundError('No se encontró el medio: ' + c['path'])
        if c.get('kind', 'video') not in ('video', 'audio','title','subtitle','image'):
            raise ValueError('Clip con tipo desconocido')
        for key in ('start_ms', 'in_ms', 'duration_ms'):
            value = float(c[key])
            if not isfinite(value) or value < 0:
                raise ValueError(f'Clip con {key} inválido')
        if c['duration_ms'] < 1:
            raise ValueError('Clip de duración nula')
        speed = float(c.get('speed', 1))
        if not is_valid_speed(speed):
            raise ValueError('Velocidad de clip incompatible')
    return max(c['start_ms'] + c['duration_ms'] for c in clips)


def _s(value):
    return f'{float(value):.6f}'.rstrip('0').rstrip('.') or '0'


@dataclass(frozen=True)
class _Frame:
    """Geometría de trabajo de un clip: la fuente escalada dentro del perfil."""
    width: int
    height: int
    fps: int


def fitted_frame(clip, profile):
    """Tamaño par de la fuente encajada en el perfil, sin barras negras.

    Zoom y censura se definen en coordenadas normalizadas de la FUENTE (igual
    que en el monitor), así que se aplican sobre esta imagen y el ``pad`` a la
    resolución del perfil se hace después. Sin dimensiones conocidas se usa
    el lienzo completo (comportamiento anterior).
    """
    from services.media_probe import probe
    meta = probe(clip['path']) if clip.get('path') else {}
    src_w, src_h = int(meta.get('width') or 0), int(meta.get('height') or 0)
    if src_w <= 0 or src_h <= 0:
        return _Frame(profile.width, profile.height, profile.fps)
    scale = min(profile.width / src_w, profile.height / src_h)
    width = min(profile.width, max(2, round(src_w * scale / 2) * 2))
    height = min(profile.height, max(2, round(src_h * scale / 2) * 2))
    return _Frame(width, height, profile.fps)


def blur_radius(strength, frame_height):
    """Desviación típica en píxeles; misma fórmula que el monitor (renderer)."""
    return max(1., min(80., float(strength))) * max(1, frame_height) / 1080


def mosaic_block(strength, frame_height):
    return max(2, round(max(1, min(80, int(strength))) * max(1, frame_height) / 1080))


def _boxblur(sigma, width, height):
    # boxblur con potencia 3 aproxima una gaussiana de sigma ≈ radio.
    # El radio no puede superar la mitad del plano de croma (submuestreado).
    limit = max(1, min(width, height) // 4)
    return f'boxblur={max(1, min(limit, round(sigma)))}:3'


def _video_filters(clip, profile, warnings, frame=None):
    frame = frame or _Frame(profile.width, profile.height, profile.fps)
    effects = merged_effects(clip.get('effects'))
    w, h = frame.width, frame.height
    filters = [f'fps={profile.fps}', f'scale={w}:{h}', 'setsar=1']
    # Mismo orden que effects.renderer.render_frame: color/espejo, zoom, censura.
    color = effects['color']
    if color['enabled']:
        brightness = max(-1, min(1, float(color['brightness']) / 100))
        contrast = max(0, min(2, float(color['contrast'])))
        saturation = max(0, min(3, float(color['saturation'])))
        if color['grayscale']:
            saturation = 0
        if color['mirror']:
            filters.append('hflip')
        filters.append(f'eq=brightness={_s(brightness)}:contrast={_s(contrast)}:saturation={_s(saturation)}')
    zoom = effects['zoom']
    if zoom['enabled']:
        if len(zoom.get('keys', [])) > 1:
            filters.append(zoompan_filter(clip, effects, frame))
        else:
            z = zoom_state(effects, float(clip.get('in_ms', 0)))
            cw = max(2, round(w / z['scale'] / 2) * 2)
            ch = max(2, round(h / z['scale'] / 2) * 2)
            x = max(0, min(w - cw, round(z['cx'] * w - cw / 2)))
            y = max(0, min(h - ch, round(z['cy'] * h - ch / 2)))
            filters += [f'crop={cw}:{ch}:{x}:{y}', f'scale={w}:{h}', 'setsar=1']
    return filters, effects


def _masked_censor(graph, stream, clip, effects, profile, index, warnings, frame=None):
    frame = frame or _Frame(profile.width, profile.height, profile.fps)
    c = effects['censor']
    if not c['enabled']:
        return stream
    w, h = frame.width, frame.height
    if len(c.get('keys', [])) > 1 or float(c.get('feather',0)) > 0:
        # Se desenfoca toda la imagen y se mezcla sólo la zona indicada por
        # una máscara gris calculada en cada fotograma de la Timeline.
        duration=clip['duration_ms']/1000
        mask=mask_geq(clip,effects,frame)
        graph.append(f'[{stream}]split=2[clean{index}][blurinput{index}]')
        if c['mode']=='mosaic':
            pixel=mosaic_block(c['strength'],h)
            graph.append(f'[blurinput{index}]scale={max(2,w//pixel)}:{max(2,h//pixel)}:flags=neighbor,'
                         f'scale={w}:{h}:flags=neighbor,format=yuv444p[blurred{index}]')
        else:
            graph.append(f'[blurinput{index}]{_boxblur(blur_radius(c["strength"],h),w,h)},'
                         f'format=yuv444p[blurred{index}]')
        graph.append(f'nullsrc=s={w}x{h}:r={profile.fps}:d={_s(duration)},'
                     f"format=yuv444p,geq=lum='{mask}':cb='{mask}':cr='{mask}'[mask{index}]")
        graph.append(f'[clean{index}]format=yuv444p[cleanfmt{index}]')
        graph.append(f'[cleanfmt{index}][blurred{index}][mask{index}]maskedmerge[censored{index}]')
        return f'censored{index}'
    m = censor_mask(effects, float(clip.get('in_ms', 0)))
    mw = max(2, min(w, round(w * m['w'] / 2) * 2))
    mh = max(2, min(h, round(h * m['h'] / 2) * 2))
    x = max(0, min(w - mw, round(m['x'] * w)))
    y = max(0, min(h - mh, round(m['y'] * h)))
    graph.append(f'[{stream}]split=2[clean{index}][rawblur{index}]')
    if c['mode'] == 'mosaic':
        pixel = mosaic_block(c['strength'], h)
        inner = f'crop={mw}:{mh}:{x}:{y},scale={max(2,mw//pixel)}:{max(2,mh//pixel)}:flags=neighbor,scale={mw}:{mh}:flags=neighbor'
    else:
        inner = f'crop={mw}:{mh}:{x}:{y},{_boxblur(blur_radius(c["strength"],h),mw,mh)}'
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
    warnings_early = []
    if profile.ten_bit and encoder_option.get('ten_bit') is False:
        profile = replace(profile, ten_bit=False)
        warnings_early.append('El codificador elegido no admite 10 bits: se exporta en 8 bits.')
    args = [ffmpeg, '-hide_banner', '-y', '-nostdin', '-loglevel', 'error', '-stats_period', '0.25',
            '-progress', 'pipe:1', '-f', 'lavfi', '-i',
            f'color=c=black:s={profile.width}x{profile.height}:r={profile.fps}:d={_s(duration)}',
            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    # Indices 0: base de vídeo; 1: silencio para preservar espacios vacíos.
    images = {'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}
    title_files={}
    for idx,clip in enumerate(clips,start=2):
        if clip.get('kind') in ('title','subtitle','image'):
            png,_=(render_image_png(clip,profile.width,profile.height) if clip.get('kind')=='image'
                   else render_title_png(clip,profile.width,profile.height))
            title_files[idx]=png
            args += ['-loop','1','-framerate',str(profile.fps),'-i',str(png)]
        else:
            if Path(clip['path']).suffix.lower() in images:
                args += ['-loop','1','-framerate',str(profile.fps),'-i',clip['path']]
            else:
                # Seek ANTES de -i: FFmpeg salta al fotograma exacto sin
                # decodificar el archivo desde el principio para cada clip.
                # Con decenas de fragmentos (Quitar silencios) es ~9x más rápido.
                source_len = clip['duration_ms'] * float(clip.get('speed', 1)) / 1000
                args += ['-ss', _s(clip['in_ms'] / 1000), '-t', _s(source_len + 0.5),
                         '-i', clip['path']]
    graph, warnings = [], []
    video = sorted(((idx, c) for idx, c in enumerate(clips, start=2) if c.get('kind') == 'video'),
                   key=lambda pair: (int(pair[1].get('track', 0)), pair[0]))
    audio = [(idx,c) for idx,c in enumerate(clips,start=2) if c.get('kind') == 'audio']
    # Base de video. Usar colas transparentes para clips con huecos y capas.
    v_prev = '0:v'
    for k, (idx, c) in enumerate(video):
        is_image = Path(c['path']).suffix.lower() in images
        # El seek de entrada ya situó el archivo en in_ms (salvo imágenes).
        start = c['in_ms'] / 1000 if is_image else 0
        length_src = c['duration_ms'] * float(c.get('speed', 1)) / 1000
        speed = float(c.get('speed', 1))
        frame = fitted_frame(c, profile)
        vf, fx = _video_filters(c, profile, warnings, frame)
        part = f'vpart{k}'
        graph.append(f'[{idx}:v:0]trim=start={_s(start)}:duration={_s(length_src)},'
                     f'setpts=(PTS-STARTPTS)/{_s(speed)},' + ','.join(vf) + f'[{part}]')
        part = _masked_censor(graph, part, c, fx, profile, k, warnings, frame)
        graph.append(f'[{part}]pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2:black,'
                     f'setsar=1[vpad{k}]')
        part = f'vpad{k}'
        tr=c.get('transition_in') or {}
        tr_kind=tr.get('kind')
        tr_len=max(.001,float(tr.get('duration_ms',0))/1000)
        if tr_kind=='wipe':
            # Revelar la capa entrante de izquierda a derecha usando su alfa.
            # T es tiempo local del clip, previo al desplazamiento de PTS.
            mask=(f'alpha(X\\,Y)*max(0\\,min(1\\, '
                  f'(T/{_s(tr_len)}-X/W)*90))')
            graph.append(f'[{part}]format=gbrap,geq=r=\'r(X,Y)\':g=\'g(X,Y)\':'
                         f'b=\'b(X,Y)\':a=\'{mask}\',format=rgba[twipe{k}]')
            part=f'twipe{k}'
        # Desvanecimiento al final de la cadena, también sobre la censura:
        # si hay capas inferiores, alpha=1 deja verlas durante el fundido.
        fade_filters=video_fade_filters(c)
        if fade_filters:
            graph.append(f'[{part}]' + ','.join(fade_filters) + f'[fade{k}]')
            part=f'fade{k}'
        # Desplazamiento a posición absoluta de la secuencia en PTS.
        graph.append(f'[{part}]setpts=PTS+{_s(c["start_ms"]/1000)}/TB[vt{k}]')
        output = f'vo{k}'
        if tr_kind=='slide':
            x=f'W*max(0\\,1-(t-{_s(c["start_ms"]/1000)})/{_s(tr_len)})'
            graph.append(f'[{v_prev}][vt{k}]overlay=x={x}:y=0:eval=frame:'
                         f'eof_action=pass:shortest=0:repeatlast=0[{output}]')
        else:
            graph.append(f'[{v_prev}][vt{k}]overlay=0:0:eof_action=pass:shortest=0:repeatlast=0[{output}]')
        v_prev = output
    # Títulos/subtítulos/imágenes como PNG RGBA. Se superponen al video final;
    # nunca se confunden con medios externos o pistas de audio.
    for idx,c in enumerate(clips,start=2):
        if idx not in title_files:continue
        start=_s(c['start_ms']/1000)
        length=_s(c['duration_ms']/1000)
        sty=default_style(c)
        layer=f'textlayer{idx}'
        chain=f'[{idx}:v:0]trim=duration={length},setpts=PTS-STARTPTS,format=rgba'
        keys=c.get('transform_keys') or []
        if any('opacity' in k for k in keys):
            opacity=ffmpeg_expression(keys,'opacity',1,time='T')
            # geq procesa la máscara alfa original del PNG, sin recomprimir
            # el resto de los clips. Se evalúa en cada frame del título.
            chain+=(',format=gbrap,geq=r=\'r(X,Y)\':g=\'g(X,Y)\':'
                    'b=\'b(X,Y)\':a=\'alpha(X,Y)*max(0\\,min(1\\,'+opacity+'))\',format=rgba')
        if any('scale' in k for k in keys):
            z=ffmpeg_expression(keys,'scale',1,time='t')
            chain+=f",scale=w='iw*max(0.2\\,{z})':h='ih*max(0.2\\,{z})':eval=frame"
        if any('rotation' in k for k in keys):
            angle=ffmpeg_expression(keys,'rotation',0,time='t')
            chain+=f",rotate=a='({angle})*PI/180':ow=rotw(iw):oh=roth(ih):c=none"
        # Fundido alfa, no oscurecimiento del fondo.
        if sty['animation'] in ('aparecer','subir','deslizar'):
            fd=min(.3,c['duration_ms']/3000)
            chain+=f',fade=t=in:st=0:d={_s(fd)}:alpha=1'
        chain+=f',setpts=PTS+{start}/TB[{layer}]'
        graph.append(chain)
        keys=c.get('transform_keys') or []
        # Las posiciones se interpolan realmente en cada fotograma.
        default_y= .87 if sty['position']=='bottom' else (.12 if sty['position']=='top' else .5)
        xpos=ffmpeg_expression(keys,'x',.5,time='t',offset=c['start_ms']/1000)
        ypos=ffmpeg_expression(keys,'y',default_y,time='t',offset=c['start_ms']/1000)
        xexpr=f'W*({xpos})-w/2'
        yexpr=f'H*({ypos})-h/2'
        if sty['animation']=='subir':
            yexpr+=f'+max(0\\,({start}+0.35-t))*240'
        elif sty['animation']=='deslizar':
            xexpr+=f'-max(0\\,({start}+0.35-t))*600'
        output=f'textmix{idx}'
        # end exclusive evita un fotograma residual sobre el corte siguiente.
        graph.append(f'[{v_prev}][{layer}]overlay=x={xexpr}:y={yexpr}:'
                     f'eval=frame:eof_action=pass:repeatlast=0:shortest=0[{output}]')
        v_prev=output
    graph.append(f'[{v_prev}]trim=duration={_s(duration)},setpts=PTS-STARTPTS[vout]')

    a_parts = []
    for k, (idx, c) in enumerate(audio):
        source_start = 0  # seek de entrada en in_ms
        source_length = c['duration_ms'] * float(c.get('speed',1)) / 1000
        a_fx = audio_filter_chain(c.get('audio_fx'), c.get('speed',1))
        name = f'a{k}'
        chain = (f'[{idx}:a:0]atrim=start={_s(source_start)}:duration={_s(source_length)},'
                 'asetpts=PTS-STARTPTS')
        if a_fx:
            chain += ',' + ','.join(a_fx)
        if c.get('volume_keys'):
            curve=ffmpeg_expression(c['volume_keys'],'volume',1,time='t')
            chain += f",volume='{curve}':eval=frame"
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
    args += video_codec_args(encoder, profile, tuned=encoder_option.get('tuned', 'full'))
    if profile.extension == 'webm':
        args += ['-c:a', 'libopus', '-b:a', '160k']
    else:
        args += ['-c:a', 'aac' if profile.extension == 'mp4' else 'pcm_s16le', '-b:a', '192k']
    if profile.extension == 'mp4':
        args += ['-movflags', '+faststart']
    args += ['-t', _s(duration), str(dest)]
    return args, list(dict.fromkeys(warnings_early + warnings))


def export_attempts(clips, profile, dest, discovery, mode='auto'):
    """Intentos de exportación en orden: [(etiqueta, argv, advertencias)].

    1. El encoder elegido (GPU con ajustes de calidad si está disponible).
    2. Si era NVENC optimizado: el mismo NVENC en modo compatible.
    3. Si era GPU: la CPU como último recurso (p. ej. NVENC ocupado por OBS
       o por otra grabación). La exportación indica qué se usó al final.
    """
    from exporter.hardware import select_encoder, cpu_option
    from exporter.encoder_settings import NVENC_LEVELS
    chosen = select_encoder(profile.codec, mode, discovery)
    options = [chosen]
    if chosen.get('tuned'):
        level = 'full' if chosen['tuned'] is True else chosen['tuned']
        for lower in NVENC_LEVELS[NVENC_LEVELS.index(level) + 1:]:
            options.append(dict(chosen, tuned=lower))
    if chosen['vendor'] != 'CPU':
        cpu = cpu_option(discovery)
        if cpu is not None:
            options.append(cpu)
    attempts = []
    for option in options:
        argv, warnings = build_export_command(clips, profile, dest, option)
        attempts.append((encoder_label(option), argv, warnings))
    return attempts


def encoder_label(option):
    if option['vendor'] == 'CPU':
        return f"CPU · {option['encoder']}"
    tuned = option.get('tuned')
    mode = {'full': 'calidad máxima', True: 'calidad máxima',
            'safe': 'calidad optimizada'}.get(tuned, 'modo compatible')
    return f"{option['vendor']} · {option['encoder']} ({mode})"
