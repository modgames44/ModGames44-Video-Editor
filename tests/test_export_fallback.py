"""El worker de exportación reintenta con el siguiente codificador si uno falla."""
import importlib.util
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from exporter.render import ExportProfile, export_attempts
from timeline.model import make_clip

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which('ffmpeg')


class _Signal:
    def __init__(self, *a):
        self.calls = []

    def connect(self, fn):
        pass

    def emit(self, *args):
        self.calls.append(args)


def _load_worker():
    qtcore = types.ModuleType('PySide6.QtCore')
    qtcore.QThread = type('QThread', (), {'__init__': lambda self, *a: None})
    qtcore.Signal = _Signal
    qtwidgets = types.ModuleType('PySide6.QtWidgets')
    for name in ('QDialog', 'QVBoxLayout', 'QFormLayout', 'QComboBox', 'QLabel', 'QPushButton',
                 'QHBoxLayout', 'QLineEdit', 'QFileDialog', 'QProgressBar', 'QMessageBox'):
        setattr(qtwidgets, name, type(name, (), {}))
    spec = importlib.util.spec_from_file_location('_export_dialog_test', ROOT / 'ui' / 'export_dialog.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'PySide6': types.ModuleType('PySide6'), 'PySide6.QtCore': qtcore,
                                  'PySide6.QtWidgets': qtwidgets}):
        spec.loader.exec_module(module)
    return module.ExportWorker


@unittest.skipIf(FFMPEG is None, 'FFmpeg no disponible')
class ExportFallbackTests(unittest.TestCase):
    def test_failed_gpu_falls_back_and_reports_encoder(self):
        Worker = _load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src.mp4'
            import subprocess
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=1',
                            '-f', 'lavfi', '-i', 'sine=d=1', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-c:a', 'aac', '-shortest', str(src)], check=True)
            clip = make_clip(src, 1000)
            profile = ExportProfile('t', 'h264', 'mp4', 320, 180, 30, '2M')
            out, temp = Path(tmp) / 'out.mp4', Path(tmp) / '.tmp.mp4'
            # En este equipo no hay GPU NVIDIA: NVENC falla igual que si
            # estuviera ocupado o el driver lo rechazara.
            discovery = {'options': [{'ffmpeg': FFMPEG, 'vendor': 'NVIDIA', 'encoder': 'h264_nvenc',
                                      'tuned': 'full', 'ten_bit': False},
                                     {'ffmpeg': FFMPEG, 'vendor': 'CPU', 'encoder': 'libx264'}]}
            attempts = export_attempts([clip], profile, temp, discovery)
            worker = Worker([(label, argv) for label, argv, _ in attempts], 1000, out, temp)
            worker.run()
            ok, message = worker.finishedResult.calls[-1]
            self.assertTrue(ok, message)
            self.assertTrue(out.is_file())
            self.assertIn('Codificador: CPU · libx264', message)
            self.assertIn('falló', message)
            statuses = [c[0] for c in worker.statusChanged.calls]
            self.assertEqual(len(statuses), 4)
            self.assertTrue(statuses[0].startswith('Exportando con NVIDIA'))


if __name__ == '__main__':
    unittest.main()
