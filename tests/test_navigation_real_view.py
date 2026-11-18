"""Regresiones geométricas del salto a Final y scroll en clips largos.

El cálculo se comprueba independientemente de Qt. La prueba de la GUI requiere
el QGraphicsView real y se realiza en Windows.
"""
import ast
import unittest
from pathlib import Path
from timeline.viewport_math import (
    scroll_correction, minimum_scene_width_for_scroll, timeline_scene_width,
    viewport_scroll_for_time, playhead_scene_x, maximum_horizontal_scroll,
)

ROOT=Path(__file__).resolve().parents[1]

class NavigationRealViewTests(unittest.TestCase):
    def test_reach_clip_end_10min20s_with_zoom(self):
        end_ms=620_120
        for scale in (5,25,70,116,350,700):
            for viewport in (600,1100,1400,2000):
                target=viewport_scroll_for_time(end_ms,scale,viewport,alignment='end')
                scene=timeline_scene_width(end_ms,scale,viewport)
                self.assertLessEqual(target,maximum_horizontal_scroll(scene,viewport))
                self.assertGreaterEqual(playhead_scene_x(end_ms,scale)-target,76)
                # Must be able to move a full viewport after the end of the video.
                self.assertGreaterEqual(scene-playhead_scene_x(end_ms,scale), viewport)

    def test_scroll_correction_uses_actual_qt_projection(self):
        # Qt can clamp or align the view differently from theoretical scroll.
        self.assertEqual(scroll_correction(930, 820, 500), 610)
        self.assertEqual(scroll_correction(600, 820, 500), 280)
        self.assertEqual(scroll_correction(20, 820, 500), 0)
        self.assertEqual(minimum_scene_width_for_scroll(5000, 1400), 6464)

    def test_scroll_correction_converges_from_stale_range(self):
        viewport=1350
        end_ms=620120
        scale=700
        head=playhead_scene_x(end_ms,scale)
        desired=76+(viewport-76)*.88
        # Qt had an obsolete maximum corresponding to the first 3 minutes.
        scroll=125000
        actual=head-scroll
        corrected=scroll_correction(actual,desired,scroll)
        width=minimum_scene_width_for_scroll(corrected,viewport)
        self.assertGreater(width,corrected+viewport)
        self.assertAlmostEqual(head-corrected,desired,delta=1)

    def test_runtime_methods_explicitly_sync_view_scene_rect(self):
        src=(ROOT/'ui/timeline_panel.py').read_text(encoding='utf-8')
        tree=ast.parse(src)
        klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TimelinePanel')
        methods={node.name:ast.get_source_segment(src,node) for node in klass.body
                 if isinstance(node,ast.FunctionDef)}
        self.assertIn('self.view.setSceneRect(',methods['_extend_scene_to'])
        self.assertIn('self.view.setSceneRect(',methods['refresh'])
        self.assertIn('self.ensure_scroll_extent(at_least_ms=self.playhead)',methods['_adjust_horizontal_to_time'])
        self.assertIn('view.mapFromScene(',methods['_adjust_horizontal_to_time'])
        self.assertIn('QTimer.singleShot(0,finish)',methods['reveal_playhead'])

if __name__=='__main__':
    unittest.main()
