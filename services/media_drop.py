"""Normalización segura y comprobable de rutas recibidas por Drag & Drop."""
from pathlib import Path


def existing_media_paths(paths):
    """Deduplica rutas reales; acepta texto con espacios y saltos de línea."""
    seen = set()
    valid = []
    for value in paths:
        raw = str(value).strip().strip('\"')
        if not raw:
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        resolved = str(path.resolve())
        key = resolved.casefold()
        if key not in seen:
            valid.append(resolved)
            seen.add(key)
    return valid
