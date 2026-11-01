"""Exportar secuencia con progreso, cancelación y detección GPU/FFmpeg asíncrona."""
from pathlib import Path
import subprocess
import os
import uuid
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLabel,
    QPushButton, QHBoxLayout, QLineEdit, QFileDialog, QProgressBar, QMessageBox)
from exporter.hardware import discover, select_encoder, CREATE_NO_WINDOW
from exporter.render import PROFILES, build_export_command

class Detector(QThread):
    ready = Signal(object)
    def run(self):
        self.ready.emit({codec:discover(codec) for codec in ('h264','hevc','av1','prores','vp9')})

class ExportWorker(QThread):
    progressChanged = Signal(int)
    finishedResult = Signal(bool, str)
    def __init__(self, argv, total_ms, output, temporary_output):
        super().__init__()
        self.argv=list(argv)
        self.total_ms=max(1,total_ms)
        self.output=Path(output)
        self.temporary_output=Path(temporary_output)
        self.process=None
        self.cancelled=False

    def cancel(self):
        self.cancelled=True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run(self):
        try:
            self.process=subprocess.Popen(self.argv, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
                creationflags=CREATE_NO_WINDOW)
            # -loglevel error: stderr es pequeño en operaciones normales.
            for line in self.process.stdout:
                if self.cancelled:
                    break
                if line.startswith('out_time='):
                    value=line.strip().partition('=')[2]
                    try:
                        h,m,s=value.split(':')
                        ms=(int(h)*3600+int(m)*60+float(s))*1000
                        self.progressChanged.emit(min(99,max(0,round(ms*100/self.total_ms))))
                    except (ValueError, TypeError):
                        pass
            if self.cancelled and self.process.poll() is None:
                self.process.terminate()
            try:
                _,errors=self.process.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                self.process.kill()
                _,errors=self.process.communicate()
            if self.cancelled:
                self.temporary_output.unlink(missing_ok=True)
                self.finishedResult.emit(False,'Exportación cancelada')
            elif self.process.returncode == 0 and self.temporary_output.exists() and self.temporary_output.stat().st_size>0:
                os.replace(self.temporary_output,self.output)
                self.progressChanged.emit(100)
                self.finishedResult.emit(True,'Video exportado: '+str(self.output))
            else:
                self.temporary_output.unlink(missing_ok=True)
                self.finishedResult.emit(False, 'FFmpeg falló:\n'+errors[-3500:])
        except (OSError, ValueError) as exc:
            self.temporary_output.unlink(missing_ok=True)
            self.finishedResult.emit(False,'No se pudo exportar: '+str(exc))

class ExportDialog(QDialog):
    def __init__(self, clips, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Exportar video · ModGames44')
        self.resize(580,310)
        self.clips=[dict(c) for c in clips]
        self.discoveries={}
        self.worker=None
        self.detector=None
        layout=QVBoxLayout(self)
        form=QFormLayout()
        self.profile=QComboBox()
        for name in PROFILES:self.profile.addItem(name)
        form.addRow('Formato / ajuste:',self.profile)
        self.mode=QComboBox()
        form.addRow('Codificación:',self.mode)
        self.gpu_label=QLabel('Detectando tarjetas y probando codificadores...')
        self.gpu_label.setWordWrap(True)
        form.addRow('Hardware:',self.gpu_label)
        self.dest=QLineEdit()
        self.dest.setText(str(Path.home()/'Videos'/'ModGames44_export.mp4'))
        choose=QPushButton('Examinar...')
        choose.clicked.connect(self._choose)
        row=QHBoxLayout();row.addWidget(self.dest);row.addWidget(choose)
        form.addRow('Guardar como:',row)
        layout.addLayout(form)
        self.warnings=QLabel('Los filtros de audio se aplican en la exportación.\n'
              'Los keyframes animados de máscara y zoom no se renderizan todavía.')
        self.warnings.setWordWrap(True)
        layout.addWidget(self.warnings)
        self.progress=QProgressBar();self.progress.setRange(0,100)
        layout.addWidget(self.progress)
        buttons=QHBoxLayout()
        self.start=QPushButton('Exportar');self.start.setEnabled(False)
        self.start.clicked.connect(self._start)
        self.cancel=QPushButton('Cerrar');self.cancel.clicked.connect(self._cancel)
        buttons.addWidget(self.start);buttons.addWidget(self.cancel)
        layout.addLayout(buttons)
        self.profile.currentIndexChanged.connect(self._codec_changed)
        self.detector=Detector(self);self.detector.ready.connect(self._detected)
        self.detector.start()

    def _codec_changed(self):
        profile=PROFILES[self.profile.currentText()]
        path=Path(self.dest.text())
        self.dest.setText(str(path.with_suffix('.'+profile.extension)))
        self.mode.clear()
        result=self.discoveries.get(profile.codec)
        options=result['options'] if result else []
        if options:
            self.mode.addItem('Automático (preferir GPU)', 'auto')
            for option in options:
                self.mode.addItem(option['vendor']+' · '+option['encoder'],option['vendor'])
            self.start.setEnabled(True)
        else:
            self.mode.addItem('Sin encoder compatible','none')
            self.start.setEnabled(False)

    def _detected(self, data):
        self.discoveries=data
        gpu_names=data['h264']['gpus']
        self.gpu_label.setText(', '.join(gpu_names) if gpu_names else
            'No se identificó una GPU por CIM; CPU disponible si FFmpeg lo admite.')
        self._codec_changed()

    def _choose(self):
        profile=PROFILES[self.profile.currentText()]
        path,_=QFileDialog.getSaveFileName(self,'Destino',self.dest.text(),
                                          f'{profile.extension.upper()} (*.{profile.extension})')
        if path:self.dest.setText(path)

    def _start(self):
        if self.worker and self.worker.isRunning():return
        profile=PROFILES[self.profile.currentText()]
        path=Path(self.dest.text()).expanduser()
        if path.suffix.lower() != '.'+profile.extension:
            QMessageBox.warning(self,'Extensión','Selecciona un archivo .'+profile.extension)
            return
        if not path.parent.is_dir():
            QMessageBox.warning(self,'Ruta','La carpeta de destino no existe')
            return
        if path.exists() and QMessageBox.question(self,'Sobrescribir',
                'El archivo ya existe. ¿Deseas reemplazarlo?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            enc=select_encoder(profile.codec, self.mode.currentData(),
                               self.discoveries[profile.codec])
            temporary_path=path.parent / ('.mg44-rendering-'+uuid.uuid4().hex+'.'+profile.extension)
            argv,warnings=build_export_command(self.clips,profile,temporary_path,enc)
        except (OSError,RuntimeError,ValueError,KeyError) as exc:
            QMessageBox.critical(self,'Exportación',str(exc));return
        if warnings:
            answer=QMessageBox.warning(self,'Funciones aún no exportables',
                '\n'.join(warnings)+'\n\n¿Exportar con las limitaciones indicadas?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        total=max(c['start_ms']+c['duration_ms'] for c in self.clips)
        self.worker=ExportWorker(argv,total,path,temporary_path)
        self.worker.progressChanged.connect(self.progress.setValue)
        self.worker.finishedResult.connect(self._finished)
        self.start.setEnabled(False)
        self.profile.setEnabled(False);self.mode.setEnabled(False)
        self.cancel.setText('Cancelar exportación')
        self.worker.start()

    def _finished(self,ok,message):
        self.cancel.setText('Cerrar')
        self.profile.setEnabled(True);self.mode.setEnabled(True)
        self._codec_changed()
        if ok:QMessageBox.information(self,'Exportación completada',message)
        else:QMessageBox.warning(self,'Exportación',message)

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.cancel.setEnabled(False)
        else:
            self.close()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            event.ignore()
            self._cancel()
        elif self.detector and self.detector.isRunning():
            event.ignore()
            self.detector.finished.connect(self.close)
        else:super().closeEvent(event)
