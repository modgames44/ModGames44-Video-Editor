from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class MediaEngine:
    def __init__(self, video_output):
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.audio.setVolume(0.75)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(getattr(video_output, "video_sink", video_output))

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
