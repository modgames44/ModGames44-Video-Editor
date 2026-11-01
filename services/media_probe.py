"""Metadatos de medios sin depender de extensiones o de ffprobe externo."""
import re
import subprocess
from pathlib import Path
def executable():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

_CACHE = {}

def probe(path):
    path = str(Path(path).resolve())
    if path in _CACHE:
        return dict(_CACHE[path])
    result = {'has_video': False, 'has_audio': False, 'duration_ms': 0}
    if not Path(path).is_file():
        return result
    try:
        proc = subprocess.run([executable(), '-hide_banner', '-i', path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        info = proc.stderr.decode('utf-8', errors='replace')
        result['has_video'] = bool(re.search(r'Stream #.*: Video:', info))
        result['has_audio'] = bool(re.search(r'Stream #.*: Audio:', info))
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', info)
        if match:
            hours, minutes, seconds = match.groups()
            result['duration_ms'] = round((int(hours)*3600 + int(minutes)*60 + float(seconds))*1000)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    _CACHE[path] = result
    return dict(result)
