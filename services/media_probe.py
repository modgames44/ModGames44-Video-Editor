"""Metadatos de medios sin depender de extensiones o de ffprobe externo.

- Las carátulas de MP3/M4A (``attached pic``) no cuentan como video.
- Se informan las dimensiones visibles (rotación de móviles aplicada), que la
  exportación usa para situar zoom y censura igual que el monitor.
- La caché se invalida si el archivo cambia (tamaño/mtime) y nunca guarda
  fallos transitorios (timeout, disco de red no disponible, etc.).
"""
import re
import subprocess
import threading
from pathlib import Path


def executable():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


_CACHE = {}
_LOCK = threading.Lock()
_STREAM = re.compile(r'Stream #\d+:\d+.*?: (Video|Audio):(.*)')
_SIZE = re.compile(r'\b(\d{2,5})x(\d{2,5})\b')
_ROTATION = re.compile(r'rotat(?:e|ion of)\s*[:=]?\s*(-?\d+(?:\.\d+)?)')
_FPS = re.compile(r'(\d+(?:\.\d+)?) (?:fps|tbr)\b')
_DURATION = re.compile(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)')


def _empty():
    return {'has_video': False, 'has_audio': False, 'duration_ms': 0,
            'width': 0, 'height': 0, 'fps': 0.0}


def parse_probe_output(info):
    """Interpreta la salida de ``ffmpeg -i``. Separado para poder probarlo."""
    result = _empty()
    lines = info.splitlines()
    for index, line in enumerate(lines):
        match = _STREAM.search(line)
        if not match:
            continue
        kind, rest = match.groups()
        if kind == 'Audio':
            result['has_audio'] = True
            continue
        if 'attached pic' in rest:
            continue  # portada de un archivo de audio
        if result['has_video']:
            continue  # sólo el primer stream de video real
        result['has_video'] = True
        fps = _FPS.search(rest)
        if fps:
            result['fps'] = float(fps.group(1))
        size = _SIZE.search(rest)
        if size:
            width, height = int(size.group(1)), int(size.group(2))
            # La rotación aparece en las líneas de side data siguientes.
            for extra in lines[index + 1:index + 8]:
                if _STREAM.search(extra):
                    break
                rotation = _ROTATION.search(extra)
                if rotation and round(abs(float(rotation.group(1)))) % 180 == 90:
                    width, height = height, width
                    break
            result['width'], result['height'] = width, height
    match = _DURATION.search(info)
    if match:
        hours, minutes, seconds = match.groups()
        result['duration_ms'] = round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    return result


def probe(path):
    path = str(Path(path).resolve())
    try:
        stat = Path(path).stat()
    except OSError:
        return _empty()
    signature = (stat.st_size, stat.st_mtime_ns)
    with _LOCK:
        cached = _CACHE.get(path)
    if cached is not None and cached[0] == signature:
        return dict(cached[1])
    try:
        proc = subprocess.run([executable(), '-hide_banner', '-i', path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=12, check=False,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return _empty()  # fallo transitorio: reintentar la próxima vez
    result = parse_probe_output(proc.stderr.decode('utf-8', errors='replace'))
    with _LOCK:
        _CACHE[path] = (signature, result)
    return dict(result)
