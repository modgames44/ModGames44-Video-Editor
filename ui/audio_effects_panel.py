"""Controles no destructivos de audio; disponibles también al reproducir."""
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout,
                               QDoubleSpinBox, QComboBox, QPushButton, QCheckBox,
                               QSlider, QHBoxLayout)
from PySide6.QtCore import Qt
from effects.audio import validated_audio_effects

class AudioEffectsPanel(QWidget):
    applyRequested = Signal(str, object)

    def __init__(self):
        super().__init__()
        self._selected = None
        outer = QVBoxLayout(self)
        self.heading = QLabel('Selecciona un clip con audio en la Timeline')
        self.heading.setWordWrap(True)
        outer.addWidget(self.heading)
        group = QGroupBox('Mejorar audio y voz')
        form = QFormLayout(group)
        self.volume = QDoubleSpinBox()
        self.volume.setRange(-36, 24); self.volume.setDecimals(1)
        self.volume.setSuffix(' dB');self.volume.setSingleStep(1)
        form.addRow('Ganancia de clip', self.volume)
        self.noise = QSlider(Qt.Orientation.Horizontal)
        self.noise.setRange(0,100);self.noise.setValue(0)
        self.noise_value = QLabel('0 %')
        line = QHBoxLayout();line.addWidget(self.noise);line.addWidget(self.noise_value)
        self.noise.valueChanged.connect(lambda v:self.noise_value.setText(f'{v} %'))
        form.addRow('Reducir ruido',line)
        self.voice = QComboBox()
        for name, value in [ ('Sin perfil', 'none'), ('Voz podcast (ModGames44)', 'podcast'),
                             ('Voz equilibrada · tono alto', 'high'), ('Voz equilibrada · tono bajo', 'low') ]:
            self.voice.addItem(name, value)
        form.addRow('Perfil de voz',self.voice)
        self.normalize = QCheckBox('Normalizar voz a -16 LUFS (aproximado)')
        form.addRow(self.normalize)
        btn = QPushButton('Aplicar ajustes al clip')
        btn.clicked.connect(self._apply)
        form.addRow(btn)
        outer.addWidget(group)
        self.note = QLabel('Los cambios se escuchan al presionar Play en la Timeline y se exportan.\n'
            'FFmpeg prepara audio por tramos en segundo plano; espera a que esté listo.')
        self.note.setWordWrap(True)
        outer.addWidget(self.note)
        outer.addStretch(1)
        self.set_selected(None)

    def set_selected(self, clip):
        self._selected=clip['id'] if clip and clip.get('kind') == 'audio' else None
        self.heading.setText('Audio: '+Path(clip['path']).name if self._selected else
                             'Selecciona un clip con audio en la Timeline')
        for group in self.findChildren(QGroupBox):
            group.setEnabled(bool(self._selected))
        if not self._selected:
            return
        fx=validated_audio_effects(clip.get('audio_fx'))
        self.volume.setValue(fx['volume_db'])
        self.noise.setValue(round(fx['noise']*100))
        pos=self.voice.findData(fx['voice'])
        self.voice.setCurrentIndex(max(0,pos))
        self.normalize.setChecked(fx['normalize'])

    def _apply(self):
        if self._selected:
            self.applyRequested.emit(self._selected, validated_audio_effects({
                'volume_db':self.volume.value(), 'noise':self.noise.value()/100,
                'voice':self.voice.currentData(), 'normalize':self.normalize.isChecked()}))
