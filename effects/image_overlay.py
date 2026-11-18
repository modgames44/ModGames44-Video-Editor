"""Imágenes superpuestas no destructivas, independientes de las pistas de vídeo.

Se cachea una copia RGBA para el monitor y para exportar, conservando
proporciones y canal alfa; el original del usuario nunca se modifica.
"""
import hashlib
import json
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'})


def image_clip(path, start_ms, duration_ms=5000):
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError('Selecciona una imagen PNG, JPG, BMP, WEBP o TIFF válida.')
    with Image.open(source) as image:
        image.verify()
    return dict(id=uuid.uuid4().hex, kind='image', path=str(source),
                start_ms=max(0, int(start_ms)), in_ms=0,
                duration_ms=max(100, int(duration_ms)), track=2, link=None,
                title_style={'position': 'center', 'animation': 'estatico'},
                transform_keys=[], fade_in_ms=0, fade_out_ms=0)


def render_image_png(clip, width=960, height=540, *, cache_root=None):
    """Devuelve PNG transparente ajustado al lienzo, con caché invalidada al cambiar el archivo."""
    source = Path(clip['path'])
    if not source.is_file():
        raise FileNotFoundError(str(source))
    stat = source.stat()
    key = [str(source.resolve()), stat.st_size, stat.st_mtime_ns, width, height]
    fingerprint = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:32]
    root = (Path(cache_root) if cache_root is not None else
            Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.cache') /
            'ModGames44' / 'VideoEditor' / 'images')
    target = root / (fingerprint + '.png')
    if target.is_file():
        with Image.open(target) as cached:
            return target, cached.size
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGBA')
    # El tamaño base es el 40 % del lienzo y la altura máxima el 70 %.
    ratio = min(1., width * .40 / max(1, image.width), height * .70 / max(1, image.height))
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    image = image.resize(size, Image.Resampling.LANCZOS)
    root.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp.png')
    image.save(temp)
    temp.replace(target)
    return target, image.size
