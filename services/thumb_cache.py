"""Caché persistente para fotogramas de Timeline con límite de tamaño."""
import hashlib
import os
from pathlib import Path

CACHE_VERSION=1
MAX_BYTES=512*1024*1024


def thumb_path(path, ms, width, height, root=None):
    source=Path(path)
    st=source.stat()
    key=f'{source.resolve()}|{st.st_size}|{st.st_mtime_ns}|{int(ms)}|{int(width)}|{int(height)}|{CACHE_VERSION}'
    token=hashlib.sha256(key.encode()).hexdigest()[:40]
    base=Path(root) if root else Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.cache')/'ModGames44'/'VideoEditor'/'frames'
    return base/(token+'.jpg')


def enforce_limit(root,max_bytes=MAX_BYTES):
    files=sorted((f for f in Path(root).glob('*.jpg') if f.is_file()),
                 key=lambda f:f.stat().st_mtime)
    total=sum(f.stat().st_size for f in files)
    for f in files:
        if total <= max_bytes:break
        try:
            size=f.stat().st_size;f.unlink();total-=size
        except OSError:pass
