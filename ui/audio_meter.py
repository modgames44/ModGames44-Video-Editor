"""Medidor estéreo vertical dBFS con muestras PCM de Qt Multimedia.

No genera señales falsas: si el audio no está disponible, permanece en silencio.
"""
import math
import struct
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QFont, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy


class StereoMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.levels = [0.0, 0.0]
        self.setMinimumSize(80, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_levels(self, left, right):
        self.levels = [max(0.0, min(1.0, float(left))),
                       max(0.0, min(1.0, float(right)))]
        self.update()

    @staticmethod
    def relative_height(amplitude):
        if amplitude <= 1e-5:
            return 0.0
        db = 20.0 * math.log10(amplitude)
        return max(0.0, min(1.0, (db + 60.0) / 60.0))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = self.rect().adjusted(8, 12, -8, -12)
        scale_width = 26
        chart_w = max(35, bounds.width() - scale_width - 12)
        chart_h = max(20, bounds.height() - 24)
        gap = max(7, chart_w // 12)
        bar_w = max(12, (chart_w - gap) // 2)
        x0 = bounds.left()
        y0 = bounds.top()
        for index, value in enumerate(self.levels):
            x = x0 + index * (bar_w + gap)
            p.fillRect(x, y0, bar_w, chart_h, QColor('#070e19'))
            p.setPen(QPen(QColor('#1f3850'), 1))
            p.drawRect(x, y0, bar_w, chart_h)
            fill_h = int(chart_h * self.relative_height(value))
            if fill_h > 0:
                gradient = QLinearGradient(x, y0 + chart_h, x, y0)
                gradient.setColorAt(0.0, QColor('#00c99e'))
                gradient.setColorAt(0.65, QColor('#6ee84b'))
                gradient.setColorAt(0.88, QColor('#f0e52c'))
                gradient.setColorAt(1.0, QColor('#fa526c'))
                p.fillRect(x + 2, y0 + chart_h - fill_h, max(1, bar_w - 3), fill_h, QBrush(gradient))
            p.setPen(QColor('#c3e4ed'))
            p.drawText(x, y0 + chart_h + 18, bar_w, 17,
                       Qt.AlignmentFlag.AlignHCenter, 'L' if index == 0 else 'R')
        p.setPen(QColor('#89a6be'))
        p.setFont(QFont('Segoe UI', 8))
        for db in (0, -6, -12, -18, -24, -36, -48, -60):
            y = int(y0 + chart_h * (-db / 60))
            p.drawText(x0 + chart_w + 5, y - 6, 28, 12,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(db))
        p.end()


class AudioMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('AudioMeterPanel')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(7, 7, 7, 7)
        label = QLabel('ESTÉREO  /  dBFS')
        label.setObjectName('SectionOverline')
        lay.addWidget(label)
        self.display = StereoMeter(self)
        lay.addWidget(self.display, 1)
        self.source_mode = 'project'
        self._buffers = {}
        self.status = QLabel('Esperando audio PCM')
        self.status.setObjectName('SecondaryHint')
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

    def clear(self):
        self.display.set_levels(0, 0)

    def set_mode(self, mode):
        self.source_mode = mode
        self.clear()
        self.status.setText('Medición PCM procesada' if mode=='timeline' else
                            'Medición PCM del archivo')

    def attach(self, player, mode='project'):
        try:
            from PySide6.QtMultimedia import QAudioBufferOutput
            output = QAudioBufferOutput(self)
            player.setAudioBufferOutput(output)
            output.audioBufferReceived.connect(
                lambda buffer, source=mode: self._incoming(buffer, source))
            self._buffers[mode] = output
            return True
        except (ImportError, AttributeError, TypeError):
            self.status.setText('Medidor PCM no disponible en esta versión de Qt')
            return False

    def _incoming(self, buffer, mode):
        if self.source_mode == mode:
            self.process(buffer)

    def process(self, buffer):
        try:
            if not buffer.isValid():
                self.clear()
                return
            fmt = buffer.format()
            channels = fmt.channelCount()
            raw = bytes(buffer.data())
            sample = fmt.sampleFormat()
            from PySide6.QtMultimedia import QAudioFormat
            if sample == QAudioFormat.SampleFormat.Float:
                size, code, normal = 4, 'f', 1.0
            elif sample == QAudioFormat.SampleFormat.Int16:
                size, code, normal = 2, 'h', 32768.0
            elif sample == QAudioFormat.SampleFormat.Int32:
                size, code, normal = 4, 'i', 2147483648.0
            else:
                return
            count = min(len(raw) // size, 32768)
            values = struct.unpack('<' + str(count) + code, raw[:count * size])
            peak = [0.0, 0.0]
            for i in range(0, len(values) - channels + 1, channels):
                for j in range(min(channels, 2)):
                    peak[j] = max(peak[j], abs(values[i + j]) / normal)
            if channels == 1:
                peak[1] = peak[0]
            self.display.set_levels(*peak)
        except (ValueError, struct.error, RuntimeError):
            self.clear()
