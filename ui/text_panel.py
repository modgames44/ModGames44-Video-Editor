"""Panel compacto de títulos y subtítulos locales; transcripción en QThread."""
from PySide6.QtCore import Signal,QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QLabel,QTextEdit,QPushButton,
    QComboBox,QSpinBox,QFormLayout,QTabWidget,QHBoxLayout,QFontComboBox)
from services.captioning import transcribe_file
from effects.title_overlay import default_style

class CaptionWorker(QThread):
    completed=Signal(object)
    failed=Signal(str)
    def __init__(self,path,language,model,parent=None):
        super().__init__(parent);self.path=path;self.language=language;self.model=model
    def run(self):
        try:self.completed.emit(transcribe_file(self.path,language=self.language,model=self.model))
        except Exception as exc:self.failed.emit(str(exc))

class TextPanel(QWidget):
    addTitle=Signal(str,object)
    addSubtitle=Signal(str)
    updateTitle=Signal(str,str,object)
    requestTranscript=Signal(str,str)
    exportSrt=Signal()
    addImage=Signal()
    def __init__(self):
        super().__init__()
        self.selected_id=None
        root=QVBoxLayout(self);root.setContentsMargins(7,7,7,7)
        self.tabs=QTabWidget();root.addWidget(self.tabs)
        titles=QWidget();form=QVBoxLayout(titles)
        form.addWidget(QLabel('Título o texto sobre el video'))
        self.title_text=QTextEdit();self.title_text.setPlaceholderText('Escribe un título…')
        self.title_text.setMaximumHeight(90);form.addWidget(self.title_text)
        controls=QFormLayout()
        self.title_size=QSpinBox();self.title_size.setRange(12,180);self.title_size.setValue(58)
        controls.addRow('Tamaño',self.title_size)
        self.title_font=QFontComboBox();self.title_font.setCurrentFont(QFont('Arial'))
        self.title_font.setToolTip('Fuente del título; se usa también al exportar')
        controls.addRow('Fuente',self.title_font)
        self.title_position=QComboBox()
        for name,value in [('Centro','center'),('Arriba','top'),('Abajo','bottom')]:self.title_position.addItem(name,value)
        controls.addRow('Ubicación',self.title_position)
        self.title_animation=QComboBox()
        for name,value in [('Sin animación','estatico'),('Aparecer','aparecer'),('Subir','subir'),('Deslizar','deslizar')]:self.title_animation.addItem(name,value)
        controls.addRow('Entrada',self.title_animation);form.addLayout(controls)
        buttons=QHBoxLayout()
        b=QPushButton('Añadir título');b.clicked.connect(self._add_title);buttons.addWidget(b)
        self.update_button=QPushButton('Actualizar');self.update_button.clicked.connect(self._update_title)
        buttons.addWidget(self.update_button);form.addLayout(buttons)
        form.addWidget(QLabel('Selecciona el texto sobre el monitor para arrastrarlo.'))
        form.addWidget(QLabel('Usa las esquinas para cambiar su tamaño.'))
        form.addStretch();self.tabs.addTab(titles,'Títulos')
        captions=QWidget();v=QVBoxLayout(captions)
        v.addWidget(QLabel('Subtítulos automáticos sin conexión'))
        self.language=QComboBox()
        for name,value in [('Español','es'),('Inglés','en'),('Detectar idioma','auto')]:self.language.addItem(name,value)
        self.model=QComboBox()
        for name in ('tiny','base','small','medium'):self.model.addItem(name)
        self.model.setCurrentText('small')
        f=QFormLayout();f.addRow('Idioma',self.language);f.addRow('Modelo',self.model);v.addLayout(f)
        v.addWidget(QLabel('Selecciona un video en la Timeline. El modelo se descarga la primera vez.'))
        self.transcribe_btn=QPushButton('Generar subtítulos del video seleccionado')
        self.transcribe_btn.clicked.connect(lambda:self.requestTranscript.emit(self.language.currentData(),self.model.currentText()))
        v.addWidget(self.transcribe_btn)
        self.subtitle_text=QTextEdit();self.subtitle_text.setPlaceholderText('O añade un subtítulo manual…')
        self.subtitle_text.setMaximumHeight(78);v.addWidget(self.subtitle_text)
        b=QPushButton('Añadir subtítulo manual');b.clicked.connect(lambda:self.addSubtitle.emit(self.subtitle_text.toPlainText()))
        v.addWidget(b)
        export_btn=QPushButton('Exportar subtítulos .srt')
        export_btn.clicked.connect(self.exportSrt.emit)
        v.addWidget(export_btn);v.addStretch();self.tabs.addTab(captions,'Subtítulos')
        images=QWidget();iv=QVBoxLayout(images)
        info=QLabel('Añade una imagen PNG o JPG como capa independiente en V3.\n'
                    'Arrástrala sobre el monitor para moverla y utiliza las esquinas para escalarla.\n'
                    'Se conserva la transparencia de los PNG.')
        info.setWordWrap(True);iv.addWidget(info)
        add_img=QPushButton('Insertar imagen…')
        add_img.clicked.connect(self.addImage.emit)
        iv.addWidget(add_img);iv.addStretch()
        self.tabs.addTab(images,'Imágenes')
        self.update_button.setEnabled(False)

    def _style(self):
        return dict(size=self.title_size.value(),position=self.title_position.currentData(),
                    animation=self.title_animation.currentData(),color='#ffffff',bold=True,
                    font_family=self.title_font.currentFont().family())
    def _add_title(self):
        if self.title_text.toPlainText().strip():self.addTitle.emit(self.title_text.toPlainText(),self._style())
    def _update_title(self):
        if self.selected_id and self.title_text.toPlainText().strip():
            self.updateTitle.emit(self.selected_id,self.title_text.toPlainText(),self._style())
    def set_selected(self,clip):
        text_clip=bool(clip and clip.get('kind') in ('title','subtitle'))
        self.selected_id=clip['id'] if text_clip else None
        self.update_button.setEnabled(text_clip)
        if text_clip:
            self.title_text.setPlainText(clip.get('text',''))
            s=default_style(clip)
            self.title_size.setValue(s['size'])
            self.title_font.setCurrentFont(QFont(s.get('font_family','Arial')))
            for box,value in ((self.title_position,s['position']),
                              (self.title_animation,s['animation'])):
                idx=box.findData(value)
                if idx>=0:box.setCurrentIndex(idx)

    def busy(self,value):
        self.transcribe_btn.setEnabled(not value)
        self.transcribe_btn.setText('Transcribiendo…' if value else 'Generar subtítulos del video seleccionado')
