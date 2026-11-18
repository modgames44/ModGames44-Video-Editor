"""Regresiones de identidad y empaquetado. No requiere PySide6 instalado."""
from pathlib import Path
import importlib.util
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class NuitkaBrandingTests(unittest.TestCase):
    def test_logo_and_icon_valid(self):
        logo = ROOT / 'assets/icons/modgames44_logo.png'
        icon = ROOT / 'assets/icons/modgames44.ico'
        with Image.open(logo) as im:
            self.assertEqual(im.format, 'PNG')
            self.assertEqual(im.size, (400, 400))
        with Image.open(icon) as im:
            self.assertEqual(im.format, 'ICO')
            self.assertGreaterEqual(im.size[0], 128)

    def test_main_window_uses_branding(self):
        source = (ROOT / 'ui/main_window.py').read_text(encoding='utf-8')
        self.assertIn("modgames44_logo.png", source)
        self.assertIn("modgames44.ico", source)
        self.assertIn("brand_layout.addWidget(logo)", source)
        self.assertIn("brand_layout.addWidget(brand)", source)

    def test_build_options_onefile(self):
        spec=importlib.util.spec_from_file_location('modgames_build', ROOT / 'build.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        opts=module.build_command()
        self.assertIn('--mode=onefile', opts)
        self.assertIn('--enable-plugin=pyside6', opts)
        self.assertIn('--include-qt-plugins=multimedia', opts)
        self.assertNotIn('--mode=standalone',opts)
        self.assertNotIn('PyInstaller',' '.join(opts))
        self.assertTrue(any(o.startswith('--windows-icon-from-ico=') for o in opts))
        self.assertTrue(any(o.startswith('--include-data-dir=') for o in opts))
        self.assertTrue(any(o.startswith('--user-package-configuration-file=') for o in opts))

    def test_ffmpeg_exec_rule(self):
        cfg=(ROOT / 'nuitka-package.config.yml').read_text(encoding='utf-8')
        self.assertIn("'imageio_ffmpeg'",cfg)
        self.assertIn('executable:',cfg)
        self.assertIn('ffmpeg-win',cfg)
        self.assertIn("'win32'",cfg)
        # Regresión: Nuitka 4.3.1 rechaza executable al nivel del elemento dlls.
        self.assertIn("        executable: 'yes'", cfg)
        self.assertNotRegex(cfg, r'(?m)^      executable:')
        spec = importlib.util.spec_from_file_location('modgames_build_check', ROOT / 'build.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.verify_package_config()

    def test_app_self_test_checks_resources(self):
        script=(ROOT / 'main.py').read_text(encoding='utf-8')
        for key in ('package_self_test', 'modgames44_logo.png', 'modgames44.ico',
                    'ffmpeg-win*.exe', 'QMediaPlayer'):
            self.assertIn(key, script)

if __name__ == '__main__':
    unittest.main()
