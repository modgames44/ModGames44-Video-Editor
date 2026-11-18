"""Reproducción de secuencia mediante QMediaPlayer; cortes/gaps y saltos."""
import time
from PySide6.QtCore import QObject,Signal,QTimer,QElapsedTimer,QUrl
from timeline.model import active,source_position,end
from timeline.playback_boundaries import limited_position
from timeline.playback_clock import projected_time

# Por encima de esta velocidad QMediaPlayer tendría que decodificar 5, 16 o
# 100 veces más fotogramas por segundo: la interfaz se colgaba. En su lugar
# el reproductor queda en pausa y el monitor salta a la posición correcta
# STEP_INTERVAL_S veces por segundo (vista tipo timelapse, carga constante).
PLAYER_MAX_RATE=4.0
STEP_INTERVAL_S=0.12


def uses_step_preview(clip):
    return clip is not None and float(clip.get('speed',1.))>PLAYER_MAX_RATE


class SequencePlayer(QObject):
    positionChanged=Signal(int)
    def __init__(self,engine,timeline):
        super().__init__();self.engine=engine;self.timeline=timeline
        self.enabled=False;self.running=False;self.position=0;self.current_id=None
        self.stop_at_cuts=True;self.use_proxies=False
        self.clock=QElapsedTimer();self.clock_base=0
        self.stepping=False;self._last_step=-1e9
        self.timer=QTimer(self);self.timer.setInterval(35);self.timer.timeout.connect(self.tick)
        self.engine.player.positionChanged.connect(self.on_position)
    def on_position(self,pos):
        if not self.enabled or not self.running:return
        # En modo por pasos las posiciones vienen de seeks, no de reproducción.
        if self.stepping:return
        c=next((c for c in self.timeline.clips if c['id']==self.current_id),None)
        if c and abs(c['start_ms']+(pos-c['in_ms'])/float(c.get('speed',1.))-self.position)<250:
            candidate=c['start_ms']+(pos-c['in_ms'])/float(c.get('speed',1.))
            self.position, reached=limited_position(
                self.timeline.clips,self.current_id,candidate,self.stop_at_cuts)
            if reached:
                self.pause()
            else:
                self.clock_base=self.position;self.clock.restart()
            self.positionChanged.emit(self.position)
    def duration(self):return max([end(c) for c in self.timeline.clips]+[0])
    def seek(self,ms):
        self.enabled=True
        self.position=max(0,min(int(ms),self.duration()))
        # Si se busca mientras reproduce, no permitir que el temporizador
        # devuelva el cabezal a la posición anterior en el siguiente tick.
        if self.running:
            self.clock_base=self.position
            self.clock.restart()
        self._sync(self.running,force_seek=True)
        self.positionChanged.emit(self.position)
    def _sync(self,play,seamless=False,force_seek=False):
        c=active(self.timeline.clips,self.position,'video') or active(self.timeline.clips,self.position,'audio')
        if c is None:
            self.current_id=None;self.engine.player.pause();return
        source_path=c['path']
        if self.use_proxies and c.get('kind')=='video':
            from services.proxy_manager import proxy_path
            try:
                candidate=proxy_path(c['path'])
                if candidate.is_file():source_path=str(candidate)
            except OSError:pass
        # Dos fragmentos del mismo archivo después de Quitar silencios no
        # deben recargar QMediaPlayer: engine.load() hace stop() y provoca
        # un parón visible incluso sin la pausa explícita de la cuchilla.
        source_changed=self.engine.player.source()!=QUrl.fromLocalFile(source_path)
        self.current_id=c['id']
        if source_changed:
            self.engine.load(source_path)
        self.stepping=uses_step_preview(c)
        self.engine.player.setPlaybackRate(1.0 if self.stepping else float(c.get('speed',1.)))
        wanted=round(source_position(c,self.position))
        # Si las posiciones de origen son consecutivas, mantener el decodificador
        # corriendo sin un seek redundante. Si se eliminó un silencio de origen,
        # saltar al in_ms del siguiente fragmento.
        # Al pulsar Play tras Pause NO rebuscar el mismo frame si ya está
        # cargado: un setPosition redundante provoca buffering adicional.
        # Los seek solicitados por el usuario siguen siendo exactos.
        tolerance=120 if seamless else 50
        if (source_changed or force_seek or
                abs(self.engine.player.position()-wanted)>tolerance):
            self.engine.seek(wanted)
        if play and not self.stepping:self.engine.player.play()
        else:self.engine.player.pause()
        if self.stepping:self._last_step=time.monotonic()
    def play(self):
        self.enabled=True
        if self.position>=self.duration():self.position=0
        self.running=True;self.clock_base=self.position;self.clock.start();self._sync(True);self.timer.start()
    def pause(self):
        self.running=False;self.timer.stop();self.engine.player.pause()
    def toggle(self):
        if self.running:self.pause()
        else:self.play()
    def tick(self):
        if not self.running:return
        # La velocidad ya se refleja en la duración del clip en la Timeline.
        # El reloj global debe avanzar a tiempo real (1 ms por ms), aunque
        # el archivo fuente se reproduzca a 0.5x, 2x o 4x.
        # Multiplicar otra vez por speed adelantaba el cabezal y desincronizaba
        # los efectos de audio con el video.
        candidate=projected_time(self.clock_base,self.clock.elapsed(),1.0,self.duration())
        self.position,reached=limited_position(
            self.timeline.clips,self.current_id,candidate,self.stop_at_cuts)
        if reached:
            # Detenerse EXACTAMENTE en el borde del segmento, sin dibujar
            # primero un fotograma de la continuación ni saltar la cuchilla.
            self.pause()
            self.positionChanged.emit(self.position)
            return
        self.positionChanged.emit(self.position)
        if self.position>=self.duration():self.pause();return
        c=next((c for c in self.timeline.clips if c['id']==self.current_id),None)
        if c and self.position>=end(c):
            # No rebobinar al borde: el tiempo global ya avanzó al clip
            # siguiente. Así el cabezal no pierde 1 tick en cada corte.
            self._sync(True,seamless=True)
        elif c and self.stepping:
            now=time.monotonic()
            if now-self._last_step>=STEP_INTERVAL_S:
                self._last_step=now
                self.engine.seek(round(source_position(c,self.position)))
        if c is None or self.current_id is None:
            # La secuencia puede contener títulos/subtítulos sobre un fondo
            # negro. El reloj debe continuar aunque no haya un archivo AV.
            next_start=min((x['start_ms'] for x in self.timeline.clips
                            if x.get('kind') in ('video','audio')
                            and x['start_ms']>=self.position),default=None)
            if next_start is None or next_start>self.position:return
            self._sync(True)

