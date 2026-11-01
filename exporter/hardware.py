"""Detección conservadora de GPU y validación real del encoder FFmpeg."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from functools import lru_cache


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


def encoder_smoke_test(ffmpeg, encoder, codec='h264'):
    """Codifica dos frames en una salida nula para validar acceso a GPU/driver."""
    args = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=size=128x128:rate=25',
            '-frames:v', '2', '-pix_fmt', 'yuv420p', '-c:v', encoder]
    if encoder.endswith('_qsv'):
        args += ['-global_quality', '25']
    args += ['-f', 'null', '-']
    try:
        p = subprocess.run(args, capture_output=True, timeout=12,
                           creationflags=CREATE_NO_WINDOW)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def discover(codec='h264', verify=True):
    """Devuelve FFmpeg seleccionado, GPUs reconocidas y encoders utilizables.

    verify=True prueba realmente cada encoder GPU, nunca confía solo en el nombre.
    """
    gpu_names = detect_gpus()
    vendors = list(dict.fromkeys(vendor(n) for n in gpu_names if vendor(n)))
    results = []
    for ffmpeg in ffmpeg_candidates():
        encoders = available_encoders(ffmpeg)
        for v in vendors + ['CPU']:
            name = CODEC_ENCODERS[codec].get(v)
            if not name or name not in encoders:
                continue
            if v != 'CPU' and verify and not encoder_smoke_test(ffmpeg, name, codec):
                continue
            results.append({'ffmpeg': ffmpeg, 'vendor': v, 'encoder': name})
    # Preferir GPU real sobre software, aunque pertenezca al segundo FFmpeg.
    results.sort(key=lambda r:(r['vendor'] == 'CPU', vendors.index(r['vendor']) if r['vendor'] in vendors else 99))
    return {'gpus': gpu_names, 'options': results}


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
