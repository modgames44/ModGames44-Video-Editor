"""Panel de efectos más utilizados, controles simples y confirmación de cambios."""
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QDoubleSpinBox,QSpinBox,QCheckBox,QComboBox,QGroupBox,QScrollArea,QFormLayout,QFrame)
from effects.model import merged_effects


class EffectsPanel(QWidget):
    applyRequested=Signal(str,object)       # clip_id, cambios
    keyframeRequested=Signal(str)           # 'zoom' o 'censor'
    editMaskChanged=Signal(bool)
    clearRequested=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self._selected=None
        outer=QVBoxLayout(self);outer.setContentsMargins(6,6,6,6)
        self.head=QLabel('Selecciona un clip de video en la Timeline')
        self.head.setWordWrap(True);outer.addWidget(self.head)
        # Acceso permanente: la sección de censura puede quedar fuera de pantalla
        # cuando el panel se redimensiona en Cyber Studio.
        self.remove_censor = QPushButton('✕  Quitar desenfoque / mosaico')
        self.remove_censor.setObjectName('RemoveCensorButton')
        self.remove_censor.setToolTip('Elimina la censura y sus fotogramas clave del clip seleccionado. Ctrl+Z para deshacer.')
        self.remove_censor.clicked.connect(self._request_clear_censor)
        outer.addWidget(self.remove_censor)
        scroller=QScrollArea();self.scroller=scroller;scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroller)
        body=QWidget();layout=QVBoxLayout(body);layout.setSpacing(7)
        scroller.setWidget(body)

        speed=QGroupBox('Velocidad · cámara lenta y rápida');self.speed_group=speed
        f=QFormLayout(speed)
        self.speed=QDoubleSpinBox();self.speed.setRange(0.25,4);self.speed.setSingleStep(.25)
        self.speed.setValue(1);self.speed.setDecimals(2);self.speed.setSuffix(' ×')
        f.addRow('Factor',self.speed)
        speed_presets=QHBoxLayout()
        for label,value in [('0.5×',.5),('1×',1.),('2×',2.),('4×',4.)]:
            b=QPushButton(label);b.clicked.connect(lambda _,n=value:self.speed.setValue(n))
            speed_presets.addWidget(b)
        f.addRow(speed_presets)
        b=QPushButton('Aplicar velocidad');b.clicked.connect(self._apply_speed);f.addRow(b)
        layout.addWidget(speed)

        zoom=QGroupBox('Zoom · acercamiento / alejamiento');self.zoom_group=zoom
        f=QFormLayout(zoom)
        self.zoom=QDoubleSpinBox();self.zoom.setRange(100,600);self.zoom.setValue(100);self.zoom.setSuffix(' %')
        self.zoom.setSingleStep(25);f.addRow('Escala',self.zoom)
        self.zoom_x=QDoubleSpinBox();self.zoom_x.setRange(0,100);self.zoom_x.setValue(50);self.zoom_x.setSuffix(' %')
        self.zoom_y=QDoubleSpinBox();self.zoom_y.setRange(0,100);self.zoom_y.setValue(50);self.zoom_y.setSuffix(' %')
        f.addRow('Centro X',self.zoom_x);f.addRow('Centro Y',self.zoom_y)
        b=QPushButton('Aplicar zoom');b.clicked.connect(self._apply_zoom);f.addRow(b)
        b=QPushButton('◇ Fotograma clave de zoom');b.clicked.connect(lambda:self.keyframeRequested.emit('zoom'))
        f.addRow(b);layout.addWidget(zoom)

        censor=QGroupBox('Censura · región rectangular');self.censor_group=censor
        f=QFormLayout(censor)
        self.mode=QComboBox();self.mode.addItem('Desenfoque gaussiano','blur')
        self.mode.addItem('Mosaico de píxeles','mosaic');f.addRow('Efecto',self.mode)
        self.strength=QSpinBox();self.strength.setRange(1,80);self.strength.setValue(18)
        f.addRow('Intensidad',self.strength)
        self.feather=QDoubleSpinBox();self.feather.setRange(0,10);self.feather.setDecimals(1)
        self.feather.setValue(1.5);self.feather.setSuffix(' %');f.addRow('Borde suave',self.feather)
        b=QPushButton('Aplicar censura a una zona');b.clicked.connect(self._apply_censor);f.addRow(b)
        self.edit_mask=QCheckBox('Editar recuadro con el mouse')
        self.edit_mask.toggled.connect(self.editMaskChanged.emit);f.addRow(self.edit_mask)
        b=QPushButton('◇ Fotograma clave de máscara');b.clicked.connect(lambda:self.keyframeRequested.emit('censor'))
        f.addRow(b)
        b=QPushButton('Quitar censura');b.clicked.connect(self._request_clear_censor);f.addRow(b)
        f.addRow(QLabel('Arrastra el centro para mover; las esquinas para cambiar tamaño.'))
        layout.addWidget(censor)

        color=QGroupBox('Color · ajustes rápidos');self.color_group=color
        f=QFormLayout(color)
        self.brightness=QSpinBox();self.brightness.setRange(-90,200)
        f.addRow('Brillo',self.brightness)
        self.contrast=QDoubleSpinBox();self.contrast.setRange(0,3);self.contrast.setSingleStep(.1)
        self.contrast.setValue(1);f.addRow('Contraste',self.contrast)
        self.saturation=QDoubleSpinBox();self.saturation.setRange(0,3);self.saturation.setSingleStep(.1)
        self.saturation.setValue(1);f.addRow('Saturación',self.saturation)
        self.grayscale=QCheckBox('Blanco y negro');f.addRow(self.grayscale)
        self.mirror=QCheckBox('Espejo horizontal');f.addRow(self.mirror)
        b=QPushButton('Aplicar color');b.clicked.connect(self._apply_color);f.addRow(b)
        layout.addWidget(color)

        reset=QPushButton('Restaurar todos los efectos del clip')
        reset.clicked.connect(lambda:self.clearRequested.emit('all'))
        layout.addWidget(reset)
        layout.addStretch()
        self.set_selected(None)

    def set_selected(self,clip):
        self._selected=clip['id'] if clip and clip.get('kind')=='video' else None
        is_video=self._selected is not None
        self.head.setText(('Clip: '+Path(clip['path']).name) if is_video else
                          'Selecciona un clip de video en la Timeline')
        for group in self.findChildren(QGroupBox):group.setEnabled(is_video)
        self.edit_mask.setEnabled(is_video)
        self.remove_censor.setEnabled(False)
        if not is_video:
            self.stop_mask_editing()
            return
        fx=merged_effects(clip.get('effects'))
        self.speed.setValue(clip.get('speed',1))
        self.zoom.setValue(fx['zoom']['scale']*100)
        self.zoom_x.setValue(fx['zoom']['cx']*100);self.zoom_y.setValue(fx['zoom']['cy']*100)
        self.strength.setValue(fx['censor']['strength'])
        self.feather.setValue(fx['censor']['feather']*100)
        self.mode.setCurrentIndex(0 if fx['censor']['mode']=='blur' else 1)
        self.brightness.setValue(fx['color']['brightness'])
        self.contrast.setValue(fx['color']['contrast']);self.saturation.setValue(fx['color']['saturation'])
        self.grayscale.setChecked(bool(fx['color']['grayscale']))
        self.mirror.setChecked(bool(fx['color']['mirror']))
        self.remove_censor.setEnabled(bool(fx['censor']['enabled']))
        if not fx['censor']['enabled']:
            self.stop_mask_editing()

    def stop_mask_editing(self):
        # La señal toggled desactiva el cursor interactivo del monitor.
        if self.edit_mask.isChecked():
            self.edit_mask.setChecked(False)

    def _request_clear_censor(self):
        if not self._selected or not self.remove_censor.isEnabled():
            return
        # Es crucial abandonar el modo de máscara antes de retirar el efecto.
        self.stop_mask_editing()
        self.clearRequested.emit('censor')

    def _emit(self,changes):
        if self._selected:self.applyRequested.emit(self._selected,changes)

    def _apply_speed(self):self._emit({'speed':self.speed.value()})
    def _apply_zoom(self):
        self._emit({'zoom':{'enabled':True,'scale':self.zoom.value()/100,
                            'cx':self.zoom_x.value()/100,'cy':self.zoom_y.value()/100}})
    def _apply_censor(self):
        self._emit({'censor':{'enabled':True,'mode':self.mode.currentData(),
                              'strength':self.strength.value(),
                              'feather':self.feather.value()/100}})
        self.edit_mask.setChecked(True)
    def _apply_color(self):
        self._emit({'color':{'enabled':True,'brightness':self.brightness.value(),
                              'contrast':self.contrast.value(),
                              'saturation':self.saturation.value(),
                              'grayscale':self.grayscale.isChecked(),
                              'mirror':self.mirror.isChecked()}})

    def focus_section(self, name):
        """Desplaza los controles reales hacia el efecto elegido del catálogo."""
        widget = {'speed': self.speed_group, 'zoom': self.zoom_group,
                  'censor': self.censor_group, 'color': self.color_group}.get(name)
        if widget is not None:
            self.scroller.ensureWidgetVisible(widget)
