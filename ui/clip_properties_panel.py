"""Inspector visual de solo lectura, enlazado al clip seleccionado.

Los datos se editan en los paneles funcionales de Video / Audio, evitando
controles decorativos que aparentan aplicar cambios pero no lo hacen.
"""
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFrame, QLabel,
                               QPushButton, QFormLayout, QScrollArea, QGroupBox)
from effects.model import merged_effects
from effects.audio import validated_audio_effects


class ClipPropertiesPanel(QWidget):
    editRequested = Signal(str)
    removeCensorRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ClipPropertiesPanel')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 10, 9, 8)
        outer.setSpacing(7)
        self.info = QLabel('Selecciona un clip en la Timeline')
        self.info.setObjectName('SectionOverline')
        self.info.setWordWrap(True)
        outer.addWidget(self.info)
        # Atajo contextual accesible incluso con la pestaña Efectos cerrada.
        self.remove_censor = QPushButton('✕  Quitar desenfoque / mosaico')
        self.remove_censor.setObjectName('RemoveCensorButton')
        self.remove_censor.setToolTip('Retira la censura del clip seleccionado (deshacer: Ctrl+Z)')
        self.remove_censor.clicked.connect(self.removeCensorRequested.emit)
        outer.addWidget(self.remove_censor)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(area, 1)
        self.content = QWidget()
        area.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        self.fields = {}
        source = QGroupBox('Información del clip')
        form = QFormLayout(source)
        for key, label in (('kind', 'Tipo'), ('track', 'Pista'),
                           ('start', 'Inicio'), ('duration', 'Duración'),
                           ('speed', 'Velocidad'), ('source', 'Archivo')):
            lab = QLabel('—')
            lab.setObjectName('PropertyValue')
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.fields[key] = lab
            form.addRow(label, lab)
        layout.addWidget(source)
        transform = QGroupBox('Transformar')
        f = QFormLayout(transform)
        for key, label in (('scale', 'Escala'), ('center', 'Centro'),
                           ('censor', 'Censura'), ('color', 'Color')):
            lab = QLabel('—');lab.setObjectName('PropertyValue')
            self.fields[key] = lab
            f.addRow(label, lab)
        layout.addWidget(transform)
        audio = QGroupBox('Audio / voz')
        f = QFormLayout(audio)
        for key, label in (('volume', 'Ganancia'), ('voice', 'Perfil'), ('noise', 'Ruido')):
            lab = QLabel('—'); lab.setObjectName('PropertyValue')
            self.fields[key] = lab
            f.addRow(label, lab)
        layout.addWidget(audio)
        self.edit_video = QPushButton('Editar efectos de video')
        self.edit_audio = QPushButton('Editar audio y voz')
        self.edit_video.clicked.connect(lambda: self.editRequested.emit('video'))
        self.edit_audio.clicked.connect(lambda: self.editRequested.emit('audio'))
        layout.addWidget(self.edit_video)
        layout.addWidget(self.edit_audio)
        hint = QLabel('Ajustes no destructivos: los medios originales permanecen intactos.')
        hint.setObjectName('SecondaryHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.set_selected(None)

    @staticmethod
    def _time(ms):
        ms = max(0, int(ms))
        minutes, seconds = divmod(ms // 1000, 60)
        return f'{minutes:02}:{seconds:02}.{ms % 1000:03}'

    def set_selected(self, clip):
        if not clip:
            self.info.setText('Selecciona un clip en la Timeline')
            for lab in self.fields.values():
                lab.setText('—')
            self.remove_censor.setEnabled(False)
            self.edit_video.setEnabled(False)
            self.edit_audio.setEnabled(False)
            return
        kind = clip.get('kind', 'video')
        self.info.setText(Path(str(clip.get('path', 'Archivo'))).name)
        values = {
            'kind': 'Video' if kind == 'video' else 'Audio',
            'track': str(clip.get('track', '—')),
            'start': self._time(clip.get('start_ms', 0)),
            'duration': self._time(clip.get('duration_ms', 0)),
            'speed': f'{clip.get("speed", 1):g} ×',
            'source': Path(str(clip.get('path', '—'))).suffix.lower() or '—',
        }
        self.remove_censor.setEnabled(
            kind == 'video' and
            bool(merged_effects(clip.get('effects'))['censor']['enabled']))
        if kind == 'video':
            fx = merged_effects(clip.get('effects'))
            values.update({
                'scale': f'{fx["zoom"]["scale"] * 100:.0f} %',
                'center': f'{fx["zoom"]["cx"] * 100:.0f} %  /  {fx["zoom"]["cy"] * 100:.0f} %',
                'censor': 'Activa' if fx['censor']['enabled'] else 'Desactivada',
                'color': 'Personalizado' if fx['color']['enabled'] else 'Sin cambios',
                'volume': 'Ver pista de audio vinculada',
                'voice': '—', 'noise': '—',
            })
        else:
            fx = validated_audio_effects(clip.get('audio_fx'))
            values.update({
                'scale': '—', 'center': '—', 'censor': '—', 'color': '—',
                'volume': f'{fx["volume_db"]:+.1f} dB',
                'voice': str(fx['voice']).capitalize(),
                'noise': f'{fx["noise"] * 100:.0f} %',
            })
        for key, label in self.fields.items():
            label.setText(str(values.get(key, '—')))
        self.edit_video.setEnabled(kind == 'video')
        self.edit_audio.setEnabled(kind == 'audio' or bool(clip.get('link')))
