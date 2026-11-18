"""Regresión de navegación de extremos y recepción DnD sin cambiar tiempos.

Las pruebas geométricas no dependen de PySide6. Las interacciones Qt
necesitan validación adicional en Windows.
"""
import ast
import unittest
from pathlib import Path

from timeline.viewport_math import (
    playhead_scene_x, viewport_scroll_for_time,
    maximum_horizontal_scroll, timeline_scene_width,
)

ROOT=Path(__file__).resolve().parents[1]


def method_source(rel, classname, method):
    src=(ROOT/rel).read_text(encoding='utf-8')
    klass=next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name==classname)
    fn=next(n for n in klass.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==method)
    return ast.get_source_segment(src,fn)


class ScrollExtentTests(unittest.TestCase):
    def test_end_reachable_at_all_zoom_and_viewport_sizes(self):
        for scale in (5, 25, 70, 116, 350, 700):
            for viewport in (400, 768, 1024, 1366, 1920, 2560, 3840):
                for end_ms in (1_000, 60_000, 20 * 60_000, 3 * 3600_000):
                    with self.subTest(scale=scale, viewport=viewport, end=end_ms):
                        scene=timeline_scene_width(end_ms,scale,viewport)
                        target=viewport_scroll_for_time(end_ms,scale,viewport,
                                                        alignment='end')
                        self.assertLessEqual(target,maximum_horizontal_scroll(scene,viewport))
                        self.assertGreaterEqual(target,0)
                        x=playhead_scene_x(end_ms,scale)-target
                        self.assertGreaterEqual(x,75)
                        self.assertLessEqual(x,viewport)

    def test_space_beyond_last_clip_by_time_and_viewport(self):
        for end_ms in (0, 10_000, 300_000):
            for scale in (5, 70, 700):
                for viewport in (480, 1280, 2560):
                    scene=timeline_scene_width(end_ms,scale,viewport)
                    end_x=playhead_scene_x(end_ms,scale)
                    scroll_max=maximum_horizontal_scroll(scene,viewport)
                    # Es posible poner el instante final BIEN a la izquierda,
                    # mostrando la zona en blanco donde se insertará otro clip.
                    if end_ms >= 20_000:
                        self.assertGreater(scroll_max,end_x-80)
                    # Cola temporal con duración mínima de 45 s.
                    self.assertGreaterEqual(scene-end_x,scale*45-1)

    def test_very_high_zoom_does_not_change_clip_duration(self):
        end_ms=420_000
        a=timeline_scene_width(end_ms,5,1024)
        b=timeline_scene_width(end_ms,700,1024)
        self.assertGreater(b,a)
        self.assertEqual(end_ms,420_000)

    def test_width_grows_for_responsive_viewport(self):
        a=timeline_scene_width(100000,5,400)
        b=timeline_scene_width(100000,5,2500)
        self.assertGreater(b,a)

    def test_pure_navigation_does_not_move_playhead(self):
        time=500_000
        scene=timeline_scene_width(600_000,700,1366)
        scroll=viewport_scroll_for_time(time,700,1366,alignment='center')
        self.assertLess(scroll,maximum_horizontal_scroll(scene,1366))
        self.assertEqual(playhead_scene_x(time,700),350076)


class DragDropIntegrationContractTests(unittest.TestCase):
    def test_media_list_starts_explicit_drag(self):
        txt=(ROOT/'ui/project_panel.py').read_text(encoding='utf-8')
        self.assertIn('def mouseMoveEvent(self, event):',txt)
        self.assertIn('QApplication.startDragDistance()',txt)
        self.assertIn('self.startDrag(Qt.DropAction.CopyAction)',txt)
        self.assertIn('application/x-modgames44-media-paths',txt)
        self.assertIn('QUrl.fromLocalFile(path)',txt)

    def test_viewport_accepts_drag_events_before_scene(self):
        txt=(ROOT/'ui/timeline_panel.py').read_text(encoding='utf-8')
        self.assertIn('self.viewport().installEventFilter(self)',txt)
        filt=method_source('ui/timeline_panel.py','TimelineView','eventFilter')
        for name in ('DragEnter','DragMove','Drop'):
            self.assertIn('QEvent.Type.'+name,filt)
        drop=method_source('ui/timeline_panel.py','TimelineView','dropEvent')
        self.assertIn('self.panel.add_clip(path,start_ms=start,track=track,kind=kind)',drop)

    def test_resize_expands_scroll_without_regenerating_clips(self):
        txt=(ROOT/'ui/timeline_panel.py').read_text(encoding='utf-8')
        self.assertIn('self.panel.ensure_scroll_extent',txt)
        ensure=method_source('ui/timeline_panel.py','TimelinePanel','ensure_scroll_extent')
        self.assertIn('timeline_scene_width(',ensure)
        self.assertIn('self._extend_scene_to(width)',ensure)
        extension=method_source('ui/timeline_panel.py','TimelinePanel','_extend_scene_to')
        self.assertIn('self.scene.setSceneRect(',extension)
        self.assertIn('self.view.setSceneRect(',extension)
        self.assertNotIn('self.refresh()',extension)

    def test_jump_to_end_updates_scroll_view(self):
        txt=(ROOT/'ui/main_window.py').read_text(encoding='utf-8')
        self.assertIn("self.timeline.reveal_playhead(destination, alignment='end')",txt)
        self.assertIn("self.timeline.reveal_playhead(0, alignment='start')",txt)

if __name__=='__main__':
    unittest.main()
