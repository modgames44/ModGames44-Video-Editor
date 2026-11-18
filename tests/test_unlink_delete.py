"""Desvincular audio/vídeo y borrar sólo el que el usuario elige."""
import ast
import unittest
from pathlib import Path

from timeline.editing import unlink, remove_linked, split_at
from timeline.model import make_clip
from timeline.ripple import ripple_remove

ROOT = Path(__file__).resolve().parents[1]


def pair():
    video = make_clip('a.mp4', 5000, link='L')
    audio = make_clip('a.mp4', 5000, kind='audio', link='L')
    return video, audio


class UnlinkDeleteTests(unittest.TestCase):
    def test_linked_pair_is_deleted_together(self):
        video, audio = pair()
        clips = [video, audio]
        remove_linked(clips, {audio['id']})
        self.assertEqual(clips, [])

    def test_after_unlink_only_chosen_clip_is_deleted(self):
        for remover in (remove_linked, ripple_remove):
            for keep in ('video', 'audio'):
                video, audio = pair()
                clips = [video, audio]
                unlink(clips, {video['id']})
                target = audio if keep == 'video' else video
                remover(clips, {target['id']})
                self.assertEqual([c['kind'] for c in clips], [keep], remover.__name__)

    def test_unlinked_clips_stay_unlinked_after_cutting(self):
        video, audio = pair()
        clips = [video, audio]
        unlink(clips, {audio['id']})
        split_at(clips, video['id'], 2000)
        right_video = next(c for c in clips if c['kind'] == 'video' and c['start_ms'] == 2000)
        remove_linked(clips, {right_video['id']})
        self.assertEqual(sorted(c['kind'] for c in clips), ['audio', 'video'])


class RightClickSelectionTests(unittest.TestCase):
    def test_right_click_selects_clip_under_pointer(self):
        tree = ast.parse((ROOT / 'ui' / 'timeline_panel.py').read_text(encoding='utf-8'))
        view = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TimelineView')
        method = next(n for n in view.body if isinstance(n, ast.FunctionDef) and n.name == 'contextMenuEvent')
        source = ast.unparse(method)
        self.assertIn('_clip_under_pointer', source)
        self.assertIn('setSelected(True)', source)
        self.assertIn('clearSelection()', source)
        self.assertIn('super().contextMenuEvent(event)', source)


if __name__ == '__main__':
    unittest.main()
