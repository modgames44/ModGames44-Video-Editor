"""Monitor escalable. Solo Play inicia reproducción; previsualizar no reproduce."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLabel, QSlider, QToolButton, QSizePolicy, QComboBox)
from ui.effect_video_view import EffectVideoView


class ProgramMonitor(QWidget):
    toggle = Signal()
    seek_requested = Signal(int)
    start_requested = Signal()
    end_requested = Signal()
    frame_step = Signal(int)
    volume_changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setObjectName('ProgramMonitor')
        self.duration = 0
        self.compact = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 7)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.title = QLabel('PROGRAMA  /  MONITOR')
        self.title.setObjectName('SectionOverline')
        top.addWidget(self.title)
        self.fx_indicator = QLabel('FX · Listos para reproducir')
        self.fx_indicator.setObjectName('PreviewFxIndicator')
        self.fx_indicator.setToolTip('Los efectos de video y audio se previsualizan en la Timeline')
        self.fx_indicator.hide()
        top.addWidget(self.fx_indicator)
        top.addStretch()
        self.quality = QComboBox()
        self.quality.setObjectName('MonitorQuality')
        self.quality.addItems(['Ajustar', '1/2', '1/4'])
        self.quality.setToolTip('Escala de visualización (no afecta a la exportación)')
        # No se conecta a la calidad de Qt Multimedia: es indicador reservado
        # hasta que el monitor soporte render por escalas reales.
        self.quality.hide()
        top.addWidget(self.quality)
        layout.addLayout(top)
        self.video = EffectVideoView()
        self.video.setMinimumSize(280, 160)
        self.video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video, 1)
        row_time = QHBoxLayout()
        self.elapsed = QLabel('00:00:00.000')
        self.elapsed.setObjectName('ActiveTimecode')
        row_time.addWidget(self.elapsed)
        row_time.addStretch()
        self.time = QLabel('00:00:00.000 / 00:00:00.000')
        self.time.setObjectName('MonitorTimecode')
        row_time.addWidget(self.time)
        layout.addLayout(row_time)
        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setObjectName('MonitorScrubber')
        self.scrubber.sliderMoved.connect(self.seek_requested.emit)
        layout.addWidget(self.scrubber)
        controls = QHBoxLayout()
        controls.setSpacing(4)
        controls.addStretch()
        data = [
            ('⏮', 'Ir al inicio', self.start_requested, None),
            ('❮', 'Fotograma anterior', self.frame_step, -1),
            ('▶ / ❚❚', 'Reproducir / Pausar', self.toggle, None),
            ('❯', 'Fotograma siguiente', self.frame_step, 1),
            ('⏭', 'Ir al final', self.end_requested, None),
        ]
        self.transport = []
        for icon, tip, signal, value in data:
            button = QToolButton(self)
            button.setText(icon)
            button.setObjectName('TransportPrimary' if tip == 'Reproducir / Pausar' else 'TransportButton')
            button.setToolTip(tip)
            button.setMinimumSize(30, 30)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if value is None:
                button.clicked.connect(signal.emit)
            else:
                button.clicked.connect(lambda checked=False, s=signal, v=value: s.emit(v))
            controls.addWidget(button)
            self.transport.append(button)
        controls.addStretch()
        self.volume_icon = QLabel('◖))')
        self.volume_icon.setObjectName('SecondaryHint')
        controls.addWidget(self.volume_icon)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName('VolumeSlider')
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setFixedWidth(85)
        self.volume.setToolTip('Volumen de la previsualización')
        self.volume.valueChanged.connect(lambda value: self.volume_changed.emit(value / 100))
        controls.addWidget(self.volume)
        layout.addLayout(controls)

    def set_fx_state(self, text=None):
        self.fx_indicator.setVisible(bool(text))
        if text and self.fx_indicator.text()!=text:
            self.fx_indicator.setText(text)

    def set_compact(self, enabled):
        self.compact = bool(enabled)
        self.volume_icon.setVisible(not enabled)
        self.volume.setFixedWidth(58 if enabled else 85)
        self.time.setVisible(not enabled)
        self.title.setText('PROGRAMA' if enabled else 'PROGRAMA  /  MONITOR')

    @staticmethod
    def format_ms(ms):
        ms = max(0, int(ms))
        h, rest = divmod(ms, 3600000)
        m, rest = divmod(rest, 60000)
        s, milli = divmod(rest, 1000)
        return f'{h:02}:{m:02}:{s:02}.{milli:03}'

    def update_position(self, position):
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(position)
        self.elapsed.setText(self.format_ms(position))
        self.time.setText(f'{self.format_ms(position)} / {self.format_ms(self.duration)}')

    def update_duration(self, duration):
        self.duration = max(0, int(duration))
        self.scrubber.setRange(0, self.duration)
        self.time.setText(f'{self.format_ms(self.scrubber.value())} / {self.format_ms(self.duration)}')
