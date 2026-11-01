"""Interfaz opcional para propuestas de edición con validación humana."""
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QCheckBox, QLineEdit, QGroupBox, QMessageBox,
)


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class TaskWorker(QRunnable):
    def __init__(self, func):
        super().__init__()
        self.func = func
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.func())
        except Exception as exc:
            self.signals.error.emit(str(exc))


class AIAssistantPanel(QWidget):
    proposeRequested = Signal(str, bool, str)
    silenceRequested = Signal()
    applyRequested = Signal()

    def __init__(self):
        super().__init__()
        self.pending = None
        self.busy = False
        self.worker = None
        self.pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        title = QLabel('ModGames44 AI Assistant')
        title.setStyleSheet('font-weight: bold; font-size: 14px;')
        root.addWidget(title)
        self.description = QLabel('Propone cambios en la Timeline. Revisa el plan antes de aplicarlo.')
        self.description.setWordWrap(True)
        root.addWidget(self.description)
        root.addWidget(QLabel('Escribe una instrucción:'))
        self.query = QPlainTextEdit()
        self.query.setPlaceholderText('Corta en 00:05\nElimina desde 00:10 hasta 00:15\nMueve el clip a 00:20')
        self.query.setMaximumHeight(92)
        root.addWidget(self.query)
        self.cloud = QCheckBox('Usar API de OpenAI (opcional)')
        self.cloud.setToolTip('Envía tu instrucción y metadatos de la Timeline. Nunca envía el video completo.')
        root.addWidget(self.cloud)
        self.model = QLineEdit('gpt-4.1-mini')
        self.model.setToolTip('Nombre del modelo disponible en tu cuenta de API')
        self.model.setEnabled(False)
        self.cloud.toggled.connect(self.model.setEnabled)
        root.addWidget(self.model)
        buttons = QHBoxLayout()
        self.propose = QPushButton('Analizar instrucción')
        self.propose.clicked.connect(self._request)
        self.silence = QPushButton('Autoedición: quitar silencios')
        self.silence.setToolTip('Analiza localmente el audio del clip seleccionado con FFmpeg')
        self.silence.clicked.connect(self.silenceRequested.emit)
        buttons.addWidget(self.propose)
        buttons.addWidget(self.silence)
        root.addLayout(buttons)
        root.addWidget(QLabel('Vista previa de operaciones:'))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('Ninguna operación propuesta.\nEl material original nunca se modifica.')
        root.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        self.apply = QPushButton('Aplicar cambios')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.applyRequested.emit)
        self.discard = QPushButton('Descartar')
        self.discard.clicked.connect(self.clear_plan)
        actions.addWidget(self.apply)
        actions.addWidget(self.discard)
        root.addLayout(actions)
        self.status = QLabel('Modo local: no requiere conexión. Para la API, configura OPENAI_API_KEY.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def _request(self):
        query = self.query.toPlainText().strip()
        if not query:
            self.status.setText('Escribe primero una instrucción.')
            return
        self.proposeRequested.emit(query, self.cloud.isChecked(), self.model.text().strip())

    def start_task(self, callback, on_success):
        if self.busy:
            self.status.setText('Ya existe una operación en curso.')
            return
        self.clear_plan()
        self.busy = True
        self.propose.setEnabled(False)
        self.silence.setEnabled(False)
        self.status.setText('Analizando…')
        worker = TaskWorker(callback)
        self.worker = worker
        def success(result):
            self._finish()
            on_success(result)
        def fail(message):
            self._finish()
            self.status.setText('Error: ' + message)
        worker.signals.result.connect(success)
        worker.signals.error.connect(fail)
        self.pool.start(worker)

    def _finish(self):
        self.busy = False
        self.propose.setEnabled(True)
        self.silence.setEnabled(True)
        self.worker = None

    def display_plan(self, plan, signature):
        self.pending = (plan, signature)
        lines = []
        if plan['explanation']:
            lines.extend([plan['explanation'], ''])
        lines.extend(f'{index}. {msg}' for index, msg in enumerate(plan['messages'], 1))
        self.preview.setPlainText('\n'.join(lines))
        self.apply.setEnabled(bool(plan['operations']))
        self.status.setText(f'{len(plan["operations"])} operación(es) propuestas. No se han aplicado cambios.')

    def message(self, text):
        self.clear_plan()
        self.preview.setPlainText(text)
        self.status.setText(text)

    def clear_plan(self):
        self.pending = None
        self.apply.setEnabled(False)
        self.preview.clear()

    def invalidated(self):
        if self.pending is not None:
            self.clear_plan()
            self.status.setText('La Timeline cambió. Vuelve a generar el plan.')
