"""Detección conservadora de GPU y validación real del encoder FFmpeg."""
import re
import shutil
import subprocess
import sys


CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
CODEC_ENCODERS = {
    'h264': {'NVIDIA': 'h264_nvenc', 'AMD': 'h264_amf', 'Intel': 'h264_qsv', 'CPU': 'libx264'},
    'hevc': {'NVIDIA': 'hevc_nvenc', 'AMD': 'hevc_amf', 'Intel': 'hevc_qsv', 'CPU': 'libx265'},
    'av1': {'NVIDIA': 'av1_nvenc', 'AMD': 'av1_amf', 'Intel': 'av1_qsv', 'CPU': 'libsvtav1'},
    'prores': {'CPU': 'prores_ks'},
    'vp9': {'CPU': 'libvpx-vp9'},
}


def ffmpeg_candidates():
    found = []
    executable = shutil.which('ffmpeg')
    if executable:
        found.append(executable)
    try:
        from services.media_probe import executable as imageio_exe
        found.append(imageio_exe())
    except (ImportError, OSError, RuntimeError):
        pass
    return list(dict.fromkeys(found))


def available_encoders(ffmpeg):
    try:
        p = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], capture_output=True,
                           text=True, timeout=12, creationflags=CREATE_NO_WINDOW)
        return set(re.findall(r'^\s*[A-Z\.]{6}\s+(\S+)', p.stdout, re.M))
    except (OSError, subprocess.TimeoutExpired):
        return set()


def detect_gpus():
    """Windows CIM, solo datos de nombre. No presupone capacidad de codificación."""
    if sys.platform != 'win32':
        return []
    powershell = shutil.which('powershell') or shutil.which('powershell.exe')
    if not powershell:
        return []
    try:
        p = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command',
                            '(Get-CimInstance Win32_VideoController).Name'],
                           capture_output=True, text=True, timeout=12,
                           creationflags=CREATE_NO_WINDOW)
        return [s.strip() for s in p.stdout.splitlines() if s.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def vendor(name):
    lower = name.lower()
    if 'nvidia' in lower or 'geforce' in lower or 'quadro' in lower: return 'NVIDIA'
    if 'amd' in lower or 'radeon' in lower: return 'AMD'
    if 'intel' in lower or 'iris' in lower or 'uhd graphics' in lower: return 'Intel'
    return None


# NVENC no codifica por debajo de 145 px (H.264) / 129 px (HEVC) en RTX 20 y
# posteriores: la prueba anterior a 128x128 fallaba SIEMPRE y el programa
# caía en la CPU sin avisar. 256x256 está por encima de todos los mínimos.
SMOKE_SIZE = '256x256'
GPU_VENDORS = ('NVIDIA', 'AMD', 'Intel')


def encoder_smoke_test(ffmpeg, encoder, codec='h264', extra_args=(), pix_fmt='yuv420p'):
    """Codifica unos fotogramas reales en una salida nula (GPU, driver, opciones)."""
    args = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', f'testsrc2=size={SMOKE_SIZE}:rate=30',
            '-frames:v', '8', '-pix_fmt', pix_fmt, '-c:v', encoder, *extra_args]
    if encoder.endswith('_qsv'):
        args += ['-global_quality', '25']
    args += ['-f', 'null', '-']
    try:
        # La primera inicialización de NVENC tras arrancar Windows puede
        # tardar varios segundos.
        p = subprocess.run(args, capture_output=True, timeout=25,
                           creationflags=CREATE_NO_WINDOW)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def gpu_capabilities(ffmpeg, encoder, codec):
    """None si el encoder GPU no funciona; si funciona, qué ajustes acepta."""
    from exporter.encoder_settings import NVENC, NVENC_LEVELS, TEN_BIT_PIX_FMT, nvenc_args
    from exporter.render import ExportProfile
    if not encoder_smoke_test(ffmpeg, encoder, codec):
        return None
    caps = {'tuned': False, 'ten_bit': False}
    if encoder in NVENC:
        probe_profile = ExportProfile('prueba', codec, 'mp4', 256, 256, 30, '8M')
        for level in NVENC_LEVELS[:-1]:
            if encoder_smoke_test(ffmpeg, encoder, codec, nvenc_args(encoder, probe_profile, level)):
                caps['tuned'] = level
                break
    if encoder in TEN_BIT_PIX_FMT:
        extra = ['-profile:v', 'main10'] if encoder == 'hevc_nvenc' else []
        caps['ten_bit'] = encoder_smoke_test(ffmpeg, encoder, codec, extra,
                                             pix_fmt=TEN_BIT_PIX_FMT[encoder])
    return caps


def discover(codec='h264', verify=True):
    """Devuelve FFmpeg seleccionado, GPUs reconocidas y encoders utilizables.

    Se prueban los encoders GPU de TODOS los fabricantes que FFmpeg incluya,
    aunque Windows no haya informado el nombre de la tarjeta (CIM puede
    fallar o devolver sólo el adaptador básico): la prueba real decide.
    Los encoders GPU que funcionan van siempre primero.
    """
    gpu_names = detect_gpus()
    named = list(dict.fromkeys(vendor(n) for n in gpu_names if vendor(n)))
    order = named + [v for v in GPU_VENDORS if v not in named]
    results = []
    for ffmpeg in ffmpeg_candidates():
        encoders = available_encoders(ffmpeg)
        for v in order + ['CPU']:
            name = CODEC_ENCODERS[codec].get(v)
            if not name or name not in encoders:
                continue
            option = {'ffmpeg': ffmpeg, 'vendor': v, 'encoder': name}
            if v != 'CPU' and verify:
                caps = gpu_capabilities(ffmpeg, name, codec)
                if caps is None:
                    continue
                option.update(caps)
            results.append(option)
    # GPU real antes que software; entre GPUs, la que Windows nombró primero.
    results.sort(key=lambda r: (r['vendor'] == 'CPU', order.index(r['vendor']) if r['vendor'] in order else 99))
    # Un mismo encoder GPU en dos FFmpeg: quedarse con el primero.
    unique, seen = [], set()
    for option in results:
        key = (option['vendor'], option['encoder'])
        if key not in seen:
            seen.add(key)
            unique.append(option)
    return {'gpus': gpu_names, 'options': unique}


def gpu_option(discovery):
    return next((o for o in discovery.get('options', []) if o['vendor'] != 'CPU'), None)


def cpu_option(discovery):
    return next((o for o in discovery.get('options', []) if o['vendor'] == 'CPU'), None)


def select_encoder(codec, mode='auto', discovery=None):
    discovery = discovery if discovery is not None else discover(codec)
    options = discovery['options']
    if mode == 'auto':
        if options: return options[0]
    else:
        matches = [o for o in options if o['vendor'] == mode]
        if matches: return matches[0]
    raise RuntimeError(f'No hay un codificador compatible con {codec} y {mode}. '
                       'Instala FFmpeg o selecciona otro formato.')
