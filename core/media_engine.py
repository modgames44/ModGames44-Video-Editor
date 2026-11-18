from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class MediaEngine:
    def __init__(self, video_output):
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.audio.setVolume(0.75)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(getattr(video_output, "video_sink", video_output))

    def set_internal_audio(self, enabled):
        """Conecta o DESCONECTA el audio interno de QMediaPlayer.

        En la Timeline el sonido lo produce el audio continuo (con efectos).
        Antes sólo se silenciaba: Qt seguía decodificando y adaptando el audio
        del archivo a la velocidad del clip (0.1×, 16×…), con carga inútil.
        """
        if enabled:
            if self.player.audioOutput() is not self.audio:
                self.player.setAudioOutput(self.audio)
            self.audio.setMuted(False)
        else:
            self.audio.setMuted(True)
            if self.player.audioOutput() is not None:
                self.player.setAudioOutput(None)

    def load(self, path):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, ms):
        self.player.setPosition(max(0, min(int(ms), self.player.duration())))
