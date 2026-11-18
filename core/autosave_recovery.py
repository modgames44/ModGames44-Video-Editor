"""Autoguardado recuperable, incluso antes del primer Guardar como.

Escritura atómica; las copias de recuperación no sustituyen al original.
"""
import hashlib
import os
from pathlib import Path
from core.project_manager import save_project, load_project


def recovery_path(project_path=None, cache_root=None):
    root=Path(cache_root) if cache_root else Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'.cache'))/'ModGames44'/'VideoEditor'/'recovery'
    token=str(Path(project_path).resolve()) if project_path else 'sin_nombre'
    return root/(hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]+'.mg44')


def save_recovery(project, project_path=None, cache_root=None):
    dest=recovery_path(project_path,cache_root)
    dest.parent.mkdir(parents=True,exist_ok=True)
    save_project(dest,project)
    return dest


def load_recovery(project_path=None, cache_root=None):
    dest=recovery_path(project_path,cache_root)
    if not dest.is_file():return None
    return load_project(dest)


def clear_recovery(project_path=None, cache_root=None):
    recovery_path(project_path,cache_root).unlink(missing_ok=True)
