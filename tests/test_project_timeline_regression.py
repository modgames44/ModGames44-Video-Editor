"""Regresiones del fallo v0.4.7: importación desde Proyecto y fondo amarillo."""
import ast
import tempfile
import unittest
from pathlib import Path

from services.media_drop import existing_media_paths
from services.media_probe import probe
from timeline.thumbnail_math import thumbnail_source_time

ROOT = Path(__file__).resolve().parents[1]


def method_source(relpath, class_name, method):
    src = (ROOT / relpath).read_text(encoding='utf-8')
    tree = ast.parse(src)
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    func = next(n for n in klass.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method)
    return ast.get_source_segment(src, func)


class ProjectToTimelineTests(unittest.TestCase):
    def test_real_paths_are_filtered_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp)/'clip con espacios.mp4'
            f.write_bytes(b'not real media for path testing')
            self.assertEqual(existing_media_paths([str(f), str(f), str(f)+'\r', str(f.parent/'missing.mp4')]), [str(f.resolve())])

    def test_double_click_and_context_action_emit_insert(self):
        src = (ROOT/'ui'/'project_panel.py').read_text(encoding='utf-8')
        self.assertIn('itemDoubleClicked.connect(self._insert_item)', src)
        self.assertIn('self.insert_files.emit([str(path)])', src)
        self.assertIn("menu.addAction('Añadir a la Timeline', self.insert_selected)", src)
        main = (ROOT/'ui'/'main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.project_panel.insert_files.connect(self.insert_project_media)',main)
        self.assertIn('self.timeline.add_clip(str(path),start_ms=start,track=0,kind=kind)',main)

    def test_drag_paths_are_wired_into_graphics_view(self):
        src = (ROOT/'ui'/'timeline_panel.py').read_text(encoding='utf-8')
        self.assertIn('self.viewport().setAcceptDrops(True)',src)
        self.assertIn('existing_media_paths(raw)',src)
        self.assertIn('self.panel.add_clip(path,start_ms=start,track=track,kind=kind)',src)

    def test_painter_owns_background_and_scopes_yellow_brush(self):
        src = method_source('ui/timeline_panel.py','ClipItem','paint')
        self.assertNotIn('super().paint(painter,option,widget)',src)
        self.assertIn("painter.fillRect(r, QColor('#075a87' if self.kind=='video' else '#075a57'))",src)
        fades = method_source('ui/timeline_panel.py','ClipItem','_draw_fades')
        self.assertIn('painter.save()',fades)
        self.assertIn('painter.restore()',fades)
        self.assertIn("painter.setBrush(QColor('#ffd477'))", fades)

    def test_video_filmstrip_uses_different_source_times(self):
        clip={'start_ms':0,'in_ms':1000,'duration_ms':24000,'speed':1}
        offsets=[thumbnail_source_time(clip,i*150,150,70) for i in range(6)]
        self.assertEqual(len(set(offsets)),6)

    def test_probe_real_mp4_when_available(self):
        sample=Path('/mnt/data/2026-10-28 08-12-03.mp4')
        if not sample.is_file():
            self.skipTest('El video de ejemplo no se incluye con el proyecto')
        meta=probe(sample)
        self.assertTrue(meta['has_video'])
        self.assertTrue(meta['has_audio'])
        self.assertGreater(meta['duration_ms'],1000)


if __name__ == '__main__':
    unittest.main()
