"""Lectura/escritura del proyecto `.mg44` (JSON, escritura atómica).

Además de la ruta absoluta, cada medio guarda su ruta RELATIVA a la carpeta
del proyecto (`path_rel` / `media_rel`). Si se mueve o copia la carpeta del
proyecto junto con sus videos a otro disco o PC, al abrirlo se resuelven las
rutas relativas. Los proyectos antiguos sin esos campos siguen funcionando.
"""
import copy
import json
import os
from pathlib import Path


def empty_project():
    return {'version': 1, 'media': [], 'clips': [], 'fps': 30}


def _relative(path, base):
    if not path or base is None:
        return None
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()
    except (OSError, ValueError):  # otra unidad en Windows (C: vs D:)
        return None


def save_project(path, data, *, relative_paths=False):
    target = Path(path)
    payload = data
    if relative_paths:
        base = target.parent
        payload = copy.deepcopy(data)
        payload['media_rel'] = [_relative(m, base) for m in payload.get('media', [])]
        for clip in payload.get('clips', []):
            if clip.get('path'):
                rel = _relative(clip['path'], base)
                if rel:
                    clip['path_rel'] = rel
                else:
                    clip.pop('path_rel', None)
    temp = target.with_suffix(target.suffix + '.tmp')
    with open(temp, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        handle.flush()
        os.fsync(handle.fileno())  # que un corte de luz no deje un JSON vacío
    temp.replace(target)


def _resolve(original, rel, base):
    if original and Path(original).exists():
        return original
    if rel and base is not None:
        candidate = (Path(base) / rel).resolve()
        if candidate.exists():
            return str(candidate)
    return original


def load_project(path, *, resolve_relative=False):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('media'), list) or not isinstance(data.get('clips'), list):
        raise ValueError('Formato de proyecto incompatible')
    if resolve_relative:
        base = Path(path).parent
        rels = data.get('media_rel') or []
        data['media'] = [_resolve(m, rels[i] if i < len(rels) else None, base)
                         for i, m in enumerate(data['media'])]
        for clip in data['clips']:
            if isinstance(clip, dict) and clip.get('path'):
                clip['path'] = _resolve(clip['path'], clip.get('path_rel'), base)
    data.pop('media_rel', None)
    for clip in data['clips']:
        if isinstance(clip, dict):
            clip.pop('path_rel', None)
    return data


def missing_media(project):
    """Rutas usadas por el proyecto que no existen en disco (sin títulos)."""
    paths = list(project.get('media', []))
    paths += [c['path'] for c in project.get('clips', [])
              if isinstance(c, dict) and c.get('path') and c.get('kind') not in ('title', 'subtitle')]
    return sorted({p for p in paths if p and not Path(p).exists()})


def relink_media(project, folder):
    """Busca por nombre de archivo en `folder` (recursivo). Devuelve nº enlazados."""
    wanted = {Path(p).name.casefold(): p for p in missing_media(project)}
    if not wanted:
        return 0
    found = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            key = name.casefold()
            if key in wanted and key not in found:
                found[key] = str(Path(root) / name)
        if len(found) == len(wanted):
            break
    mapping = {wanted[k]: v for k, v in found.items()}
    project['media'] = [mapping.get(p, p) for p in project.get('media', [])]
    for clip in project.get('clips', []):
        if isinstance(clip, dict) and clip.get('path') in mapping:
            clip['path'] = mapping[clip['path']]
    return len(mapping)
