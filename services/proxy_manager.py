"""Proxies H.264 ligeros; origen intacto, exportación siempre usa el original."""
import hashlib
import os
from pathlib import Path
import subprocess
from exporter.hardware import CREATE_NO_WINDOW


def proxy_path(source, root=None):
    p=Path(source)
    st=p.stat()
    key=hashlib.sha256(f'{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|proxy-2'.encode()).hexdigest()[:28]
    base=Path(root) if root else Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.cache')/'ModGames44'/'VideoEditor'/'proxies'
    return base/(key+'.mp4')


def proxy_command(source, output, ffmpeg='ffmpeg', height=540):
    if height not in (360,540,720):raise ValueError('Resolución no admitida')
    return [str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',
            '-i',str(source),'-map','0:v:0','-map','0:a:0?',
            '-vf',f'scale=-2:{height}:force_original_aspect_ratio=decrease',
            '-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','128k','-movflags','+faststart',str(output)]


class ProxyCancelled(RuntimeError):
    pass


def generate_proxy(source, ffmpeg='ffmpeg', *, root=None, height=540, cancel=None):
    """Genera el proxy; `cancel` (threading.Event) detiene FFmpeg de inmediato.

    Sin cancelación, cerrar la aplicación dejaba el proceso vivo hasta que
    FFmpeg terminaba (el ThreadPoolExecutor espera a sus hilos al salir).
    """
    target=proxy_path(source,root)
    if target.exists() and target.stat().st_size>1024:return target
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix('.partial.mp4')
    try:
        proc=subprocess.Popen(proxy_command(source,tmp,ffmpeg,height),
                              stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
        # stderr se lee en otro hilo para que el buffer nunca bloquee a FFmpeg.
        import threading
        errors=[]
        reader=threading.Thread(target=lambda:errors.append(proc.stderr.read()),daemon=True)
        reader.start()
        while proc.poll() is None:
            if cancel is not None and cancel.wait(.25):
                proc.kill()
                proc.wait(timeout=10)
                raise ProxyCancelled('Generación de proxy cancelada')
            if cancel is None:
                try:proc.wait(timeout=.25)
                except subprocess.TimeoutExpired:pass
        reader.join(timeout=5)
        message=(errors[0] if errors else b'').decode(errors='replace')[-1000:]
        if proc.returncode or not tmp.is_file() or tmp.stat().st_size<1024:
            raise RuntimeError('FFmpeg no pudo generar el proxy: '+message)
        tmp.replace(target)
        return target
    finally:tmp.unlink(missing_ok=True)
