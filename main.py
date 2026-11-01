"""ModGames44 Video Editor: entrada normal y comprobación del paquete onefile."""
import sys
from pathlib import Path


def package_self_test():
    """Comprobación local: recursos, FFmpeg incluido y componentes multimedia Qt."""
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    import subprocess
    import imageio_ffmpeg

    root = Path(__file__).resolve().parent
    assets = root / 'assets'
    logo = assets / 'icons' / 'modgames44_logo.png'
    icon = assets / 'icons' / 'modgames44.ico'
    stylesheet = assets / 'styles' / 'cyber_neon.qss'
    for resource in (logo, icon, stylesheet):
        if not resource.is_file():
            raise RuntimeError(f'Recurso del paquete no encontrado: {resource}')

    # No aceptar un FFmpeg del PATH como prueba del onefile: debe estar
    # físicamente bajo imageio_ffmpeg/binaries dentro de la distribución.
    bundled = Path(imageio_ffmpeg.__file__).resolve().parent / 'binaries'
    candidates = sorted(bundled.glob('ffmpeg-win*.exe')) if sys.platform == 'win32' else []
    if not candidates:
        raise RuntimeError('El FFmpeg Windows empaquetado no se encuentra dentro del ejecutable.')
    ffmpeg = candidates[0]
    run = subprocess.run([str(ffmpeg), '-hide_banner', '-version'],
                         capture_output=True, timeout=20,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if run.returncode != 0:
        raise RuntimeError('FFmpeg incluido no se puede ejecutar.')

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setWindowIcon(QIcon(str(icon)))
    if QPixmap(str(logo)).isNull():
        raise RuntimeError('El logotipo no se puede cargar.')
    if app.windowIcon().isNull():
        raise RuntimeError('El icono de Windows no se puede cargar.')
    audio_output = QAudioOutput()
    player = QMediaPlayer()
    player.setAudioOutput(audio_output)
    player.stop()
    return 0


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from ui.main_window import MainWindow
    from ui.theme_manager import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName('ModGames44 Video Editor')
    app.setOrganizationName('ModGames44')
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'assets' / 'icons' / 'modgames44.ico')))
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    if '--package-self-test' in sys.argv:
        sys.exit(package_self_test())
    sys.exit(main())
