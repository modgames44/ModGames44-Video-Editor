import tempfile
import unittest
from pathlib import Path
from core.project_manager import empty_project, load_project, save_project


class ProjectTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'test.mg44'
            project = empty_project()
            project['media'].append('video.mp4')
            save_project(path, project)
            self.assertEqual(load_project(path), project)


if __name__ == '__main__':
    unittest.main()
