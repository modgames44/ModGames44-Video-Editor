"""Exportar secuencia con progreso, cancelación y detección GPU/FFmpeg asíncrona."""
from pathlib import Path
import subprocess
import os
import uuid
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLabel,
    QPushButton, QHBoxLayout, QLineEdit, QFileDialog, QProgressBar, QMessageBox)
from exporter.hardware import discover, gpu_option, CREATE_NO_WINDOW
from exporter.render import PROFILES, export_attempts, encoder_label

class Detector(QThread):
    ready = Signal(object)
    def run(self):
        self.ready.emit({codec:discover(codec) for codec in ('h264','hevc','av1','prores','vp9')})

class ExportWorker(QThread):
    """Ejecuta los intentos en orden hasta que uno funcione.

    `attempts`: [(etiqueta, argv)]. Normalmente basta el primero (GPU). Si
    NVENC falla al iniciar (driver, sesión ocupada por OBS…), se reintenta
    en modo compatible y, por último, con la CPU.
    """
    progressChanged = Signal(int)
    statusChanged = Signal(str)
    finishedResult = Signal(bool, str)
    def __init__(self, attempts, total_ms, output, temporary_output):
        super().__init__()
        self.attempts=[(label,list(argv)) for label,argv in attempts]
        self.total_ms=max(1,total_ms)
        self.output=Path(output)
        self.temporary_output=Path(temporary_output)
        self.process=None
        self.cancelled=False

    def cancel(self):
        self.cancelled=True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def _run_once(self, argv):
        """Devuelve (ok, errores)."""
        self.process=subprocess.Popen(argv, stdout=subprocess.PIPE,
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
        ok=(self.process.returncode == 0 and self.temporary_output.exists()
            and self.temporary_output.stat().st_size>0)
        return ok, errors or ''

    def run(self):
        failures=[]
        try:
            for index,(label,argv) in enumerate(self.attempts):
                if self.cancelled:break
                self.temporary_output.unlink(missing_ok=True)
                self.progressChanged.emit(0)
                self.statusChanged.emit(('Exportando con ' if index==0 else 'Reintentando con ')+label+'…')
                ok,errors=self._run_once(argv)
                if self.cancelled:break
                if ok:
                    os.replace(self.temporary_output,self.output)
                    self.progressChanged.emit(100)
                    message='Video exportado: '+str(self.output)+'\nCodificador: '+label
                    if failures:
                        message+=('\n\nAviso: '+failures[0][0]+' falló y se usó '+label+'.\n'
                                  'Detalle: '+failures[0][1][-600:])
                    self.finishedResult.emit(True,message)
                    return
                failures.append((label,errors))
            self.temporary_output.unlink(missing_ok=True)
            if self.cancelled:
                self.finishedResult.emit(False,'Exportación cancelada')
            else:
                detail='\n\n'.join(f'{label}:\n{errors[-1500:]}' for label,errors in failures)
                self.finishedResult.emit(False,'FFmpeg falló:\n'+detail[-3500:])
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
              'Los keyframes animados de máscara y zoom se exportan con FFmpeg; puede requerir más tiempo.')
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
            self.mode.addItem('Automático (GPU si está disponible)', 'auto')
            for option in options:
                self.mode.addItem(option['vendor']+' · '+option['encoder'],option['vendor'])
            self.start.setEnabled(True)
        else:
            self.mode.addItem('Sin encoder compatible','none')
            self.start.setEnabled(False)
        self._show_hardware(profile, result)

    def _show_hardware(self, profile, result):
        if not result:
            return
        names=', '.join(result['gpus']) or 'Windows no informó el nombre de la tarjeta'
        gpu=gpu_option(result)
        if gpu is not None:
            used='Se usará la GPU: '+encoder_label(gpu)
            if profile.ten_bit and gpu.get('ten_bit') is False:
                used+=' · 10 bits no disponible, se exportará en 8 bits'
        elif profile.codec in ('prores','vp9'):
            used='Este formato sólo se codifica con la CPU (las GPU no lo soportan).'
        else:
            used='No se encontró un codificador GPU que funcione: se usará la CPU.'
        self.gpu_label.setText(names+'\n'+used)

    def _detected(self, data):
        self.discoveries=data
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
            temporary_path=path.parent / ('.mg44-rendering-'+uuid.uuid4().hex+'.'+profile.extension)
            attempts=export_attempts(self.clips,profile,temporary_path,
                                     self.discoveries[profile.codec],self.mode.currentData())
            warnings=attempts[0][2]
        except (OSError,RuntimeError,ValueError,KeyError) as exc:
            QMessageBox.critical(self,'Exportación',str(exc));return
        if warnings:
            answer=QMessageBox.warning(self,'Funciones aún no exportables',
                '\n'.join(warnings)+'\n\n¿Exportar con las limitaciones indicadas?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        total=max(c['start_ms']+c['duration_ms'] for c in self.clips)
        self.worker=ExportWorker([(label,argv) for label,argv,_ in attempts],total,path,temporary_path)
        self.worker.progressChanged.connect(self.progress.setValue)
        self.worker.statusChanged.connect(self.warnings.setText)
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
