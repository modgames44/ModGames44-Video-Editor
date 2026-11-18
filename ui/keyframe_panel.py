"""Inspector contextual: fotogramas clave de texto y volumen."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QDoubleSpinBox,QLabel,QPushButton,QHBoxLayout
from effects.title_overlay import transform_at

class KeyframePanel(QWidget):
    saveKey=Signal(str,object)
    deleteKey=Signal(str)
    def __init__(self):
        super().__init__();self.clip=None;self.position=0
        root=QVBoxLayout(self);root.setContentsMargins(8,8,8,8)
        self.help=QLabel('Selecciona texto, imagen o audio para animar sus propiedades.')
        self.help.setWordWrap(True);root.addWidget(self.help)
        form=QFormLayout();self.fields={}
        for name,label,lo,hi,step,default in (
            ('x','Posición X (%)',0,100,1,50),('y','Posición Y (%)',0,100,1,50),
            ('scale','Escala (%)',20,300,5,100),('rotation','Rotación (°)',-180,180,5,0),
            ('opacity','Opacidad (%)',0,100,5,100),('volume','Volumen (%)',0,300,5,100)):
            spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setSingleStep(step);spin.setValue(default)
            form.addRow(label,spin);self.fields[name]=spin
        root.addLayout(form)
        actions=QHBoxLayout()
        self.save=QPushButton('◇ Guardar keyframe');self.save.clicked.connect(self._save)
        self.delete=QPushButton('Quitar keyframe');self.delete.clicked.connect(self._delete)
        actions.addWidget(self.save);actions.addWidget(self.delete);root.addLayout(actions)
        self.note=QLabel('Los keyframes se guardan en el proyecto y se pueden deshacer.')
        self.note.setWordWrap(True);root.addWidget(self.note);root.addStretch()
        self.set_context(None,0)

    def set_context(self,clip,position):
        self.clip=clip
        self.position=int(position)
        kind=clip.get('kind') if clip else None
        is_title=kind in ('title','subtitle','image')
        is_audio=kind=='audio'
        for name,spin in self.fields.items():spin.setVisible(is_title if name!='volume' else is_audio)
        # Las etiquetas se ocultan con la fila completa, no sólo el spinbox.
        form=self.layout().itemAt(1).layout()
        for idx,(name,spin) in enumerate(self.fields.items()):
            label=form.labelForField(spin)
            if label:label.setVisible(is_title if name!='volume' else is_audio)
        self.save.setEnabled(is_title or is_audio);self.delete.setEnabled(is_title or is_audio)
        self.help.setText(('Animando: '+ ('Imagen' if kind=='image' else ('Texto' if is_title else 'Volumen')) +' · cabezal '+str(self.position)+' ms')
                          if (is_title or is_audio) else 'Selecciona texto, imagen o audio.')
        if is_title:
            values=transform_at(clip,position)
            for name in ('x','y','scale','rotation','opacity'):
                self.fields[name].setValue(values[name]*(100 if name in ('x','y','scale','opacity') else 1))
        elif is_audio:
            from effects.keyframe_expressions import sample
            keys=clip.get('volume_keys',[])
            self.fields['volume'].setValue(sample(keys,max(0,position-clip['start_ms']),'volume',1)*100)

    def _save(self):
        if not self.clip:return
        data={name:spin.value()/(100 if name in ('x','y','scale','opacity','volume') else 1)
              for name,spin in self.fields.items() if (name=='volume')==(self.clip.get('kind')=='audio')}
        self.saveKey.emit(self.clip['id'],data)
    def _delete(self):
        if self.clip:self.deleteKey.emit(self.clip['id'])
