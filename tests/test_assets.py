"""Verifica que el empaquetado incluya todos los iconos originales de herramientas."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
NAMES=('select','razor','trim_start','trim_end','delete','close_gaps','undo','redo','unlink','snap')


class ToolbarAssetsTest(unittest.TestCase):
    def test_svg_and_png_icons_exist(self):
        for name in NAMES:
            with self.subTest(name=name):
                svg=ROOT/'assets'/'icons'/f'{name}.svg'
                png=ROOT/'assets'/'icons'/f'{name}.png'
                self.assertTrue(svg.is_file())
                self.assertTrue(png.is_file())
                self.assertEqual(png.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
                root=ET.fromstring(svg.read_text(encoding='utf-8'))
                self.assertIn('svg',root.tag)


if __name__=='__main__':unittest.main()
