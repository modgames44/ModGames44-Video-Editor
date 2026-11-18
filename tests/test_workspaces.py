"""Contrato de las distribuciones; no requiere PySide6."""
import unittest
from core.workspaces import WORKSPACES, WORKSPACE_STATE_VERSION, normalized_workspace


class WorkspaceSpecsTests(unittest.TestCase):
    def test_two_stable_names(self):
        self.assertEqual(set(WORKSPACES), {'neon', 'studio'})
        self.assertEqual(WORKSPACES['neon'].label, 'Cyber Neon')
        self.assertEqual(WORKSPACES['studio'].label, 'Cyber Studio')

    def test_all_docks_referenced_are_unique(self):
        for space in WORKSPACES.values():
            active = (space.left_top, space.left_bottom, space.right_top,
                      space.right_bottom, space.bottom_left, space.bottom_main, space.right_extra)
            nonempty = [key for key in active if key]
            self.assertEqual(len(nonempty), len(set(nonempty)))
            self.assertIn('Timeline', nonempty)
            self.assertIn('Proyecto', nonempty)
            self.assertIn('Efectos (futuro)', nonempty)
            self.assertIn('Audio Meter', nonempty)
            self.assertIn('Herramientas', nonempty)
            self.assertTrue(all(key not in nonempty for key in space.hidden))

    def test_different_structures(self):
        self.assertEqual(WORKSPACES['neon'].left_top,'Proyecto')
        self.assertEqual(WORKSPACES['studio'].left_top,'Efectos (futuro)')
        self.assertEqual(WORKSPACES['studio'].right_top,'Propiedades')
        self.assertEqual(WORKSPACES['studio'].bottom_left,'Herramientas')
        self.assertEqual(WORKSPACES['neon'].right_top,'Efectos (futuro)')

    def test_invalid_workspace_falls_back_to_studio(self):
        for value in ('', None, 'other'):
            self.assertEqual(normalized_workspace(value),'studio')
        self.assertGreater(WORKSPACE_STATE_VERSION,0)


if __name__ == '__main__':
    unittest.main()
