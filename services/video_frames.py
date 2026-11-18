"""Decodificación auxiliar para composición multipista.

OpenCV acelera lectura de imágenes durante Play; si no está instalado,
FFmpeg permite obtener fotogramas de manera más lenta. En ambos casos la
operación está pensada para hilo trabajador, nunca el hilo gráfico de Qt.
"""
from pathlib import Path
from io import BytesIO
import subprocess
from collections import OrderedDict
from services.preview_performance import timeline_frame_cache_key
from PIL import Image
from exporter.hardware import ffmpeg_candidates

IMAGE_SUFFIXES={'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}
try:
    import cv2
except ImportError:
    cv2=None

class FrameReader:
    def __init__(self):
        self._captures={}
        self._last={}
        self._fps={}
        self._recent=OrderedDict()  # Copias reducidas, no frames 4K sin límite.
        self._cache_limit=14
        self._capture_limit=4
        self.use_proxies=False

    def close(self):
        for cap in self._captures.values():
            cap.release()
        self._captures.clear()
        self._last.clear()
        self._fps.clear()
        self._recent.clear()

    def read(self,path,source_ms,width=960,max_height=None):
        path=str(path)
        width=max(1,int(width))
        max_height=max(1,int(max_height)) if max_height is not None else 16384
        if self.use_proxies and Path(path).suffix.lower() not in IMAGE_SUFFIXES:
            from services.proxy_manager import proxy_path
            try:
                candidate=proxy_path(path)
                if candidate.is_file():path=str(candidate)
            except OSError:pass
        is_image=Path(path).suffix.lower() in IMAGE_SUFFIXES
        # El mismo frame puede solicitarse más de una vez cuando el monitor
        # trabaja a 30 fps y el reloj/tick no coincide exactamente con ese FPS.
        fps=self._fps.get(path,30.0)
        frame_index=0 if is_image else max(0,int(round(float(source_ms)*fps/1000)))
        key=timeline_frame_cache_key(path,frame_index,width,max_height)
        cached=self._recent.get(key)
        if cached is not None:
            self._recent.move_to_end(key)
            return cached.copy()
        if is_image:
            with Image.open(path) as input_image:
                image=input_image.convert('RGB')
        else:
            image=self._video(path,source_ms)
        if image is None:
            return None
        if image.width>width or image.height>max_height:
            image.thumbnail((width,max_height),Image.Resampling.BILINEAR)
        # La identidad FPS podría cambiar tras abrir VideoCapture por primera
        # vez (ej. archivo de 60 fps). Guardar usando el índice real.
        fps=self._fps.get(path,30.0)
        frame_index=0 if is_image else max(0,int(round(float(source_ms)*fps/1000)))
        key=timeline_frame_cache_key(path,frame_index,width,max_height)
        self._recent[key]=image
        self._recent.move_to_end(key)
        while len(self._recent)>self._cache_limit:
            self._recent.popitem(last=False)
        return image.copy()

    def _video(self,path,source_ms):
        if cv2 is not None:
            cap=self._captures.get(path)
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                # No conservar decodificadores abiertos indefinidamente.
                while len(self._captures)>=self._capture_limit:
                    stale_path,stale_cap=next(iter(self._captures.items()))
                    stale_cap.release()
                    self._captures.pop(stale_path,None)
                    self._last.pop(stale_path,None)
                    self._fps.pop(stale_path,None)
                cap=cv2.VideoCapture(path)
                if not cap.isOpened():
                    raise RuntimeError('No se pudo decodificar video: '+path)
                self._captures[path]=cap
                fps=cap.get(cv2.CAP_PROP_FPS) or 30
                self._fps[path]=float(fps) if fps>0 else 30.0
            else:
                # Mantener orden de uso para expulsar el más antiguo.
                self._captures.pop(path)
                self._captures[path]=cap
            fps=self._fps.get(path,30.0)
            target=max(0,int(round(float(source_ms)*fps/1000)))
            last=self._last.get(path)
            # La repetición exacta la resuelve el caché de read().
            # Saltear 1-8 frames con grab() es mucho más barato que hacer
            # set(CAP_PROP_POS_FRAMES) a cada tick, sobre todo con 60fps.
            if last is not None and target>last and target-last<=9:
                ok=True
                for _ in range(target-last-1):
                    if not cap.grab():
                        ok=False
                        break
                if not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,target)
            elif last is None or target != last+1:
                cap.set(cv2.CAP_PROP_POS_FRAMES,target)
            ret,frame=cap.read()
            if ret:
                self._last[path]=target
                return Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        ffmpeg=next(iter(ffmpeg_candidates()),'ffmpeg')
        cmd=[ffmpeg,'-hide_banner','-loglevel','error','-ss',
             f'{max(0,float(source_ms))/1000:.4f}','-i',path,
             '-frames:v','1','-f','image2pipe','-vcodec','mjpeg','pipe:1']
        result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not result.stdout:
            return None
        return Image.open(BytesIO(result.stdout)).convert('RGB')
