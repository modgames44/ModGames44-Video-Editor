"""Reproducción de secuencia mediante QMediaPlayer; cortes/gaps y saltos."""
from PySide6.QtCore import QObject,Signal,QTimer,QElapsedTimer,QUrl
from timeline.model import active,source_position,end
from timeline.playback_boundaries import limited_position
from timeline.playback_clock import projected_time

class SequencePlayer(QObject):
    positionChanged=Signal(int)
    def __init__(self,engine,timeline):
        super().__init__();self.engine=engine;self.timeline=timeline
        self.enabled=False;self.running=False;self.position=0;self.current_id=None
        self.stop_at_cuts=True
        self.clock=QElapsedTimer();self.clock_base=0
        self.timer=QTimer(self);self.timer.setInterval(35);self.timer.timeout.connect(self.tick)
        self.engine.player.positionChanged.connect(self.on_position)
    def on_position(self,pos):
        if not self.enabled or not self.running:return
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
        self._sync(self.running)
        self.positionChanged.emit(self.position)
    def _sync(self,play):
        c=active(self.timeline.clips,self.position,'video') or active(self.timeline.clips,self.position,'audio')
        if c is None:
            self.current_id=None;self.engine.player.pause();return
        if (c['id']!=self.current_id or
                self.engine.player.source()!=QUrl.fromLocalFile(c['path'])):
            # Al alternar entre Proyecto y Timeline, current_id puede seguir
            # apuntando al clip previo mientras QMediaPlayer tiene otra fuente.
            self.current_id=c['id']
            self.engine.load(c['path'])
        self.engine.player.setPlaybackRate(float(c.get('speed',1.)))
        self.engine.seek(source_position(c,self.position))
        if play:self.engine.player.play()
        else:self.engine.player.pause()
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
        current=next((c for c in self.timeline.clips if c['id']==self.current_id),None)
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
            self.position=end(c);self.current_id=None
        if c is None or self.current_id is None:
            next_start=min((x['start_ms'] for x in self.timeline.clips if x['start_ms']>=self.position),default=None)
            if next_start is None:self.pause();return
            if next_start>self.position:return
            self._sync(True)

