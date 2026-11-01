"""Compilar en Windows 10/11 (64 bits) con Nuitka ONEFILE.

    python -m pip install -r requirements.txt
    python build.py
    python build.py --dry-run  # muestra el comando sin compilar

Salida: dist/ModGames44VideoEditor.exe
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
APP_NAME = 'ModGames44VideoEditor.exe'


def verify_inputs(allow_non_windows=False):
    if sys.platform != 'win32' and not allow_non_windows:
        raise SystemExit('Nuitka debe compilar el ejecutable Windows desde Windows 10/11 de 64 bits.')
    if sys.platform == 'win32' and sys.maxsize <= 2**32:
        raise SystemExit('Utiliza Python de 64 bits para el ejecutable.')
    files = [ROOT / 'main.py', ROOT / 'nuitka-package.config.yml',
             ROOT / 'assets' / 'icons' / 'modgames44.ico',
             ROOT / 'assets' / 'icons' / 'modgames44_logo.png',
             ROOT / 'assets' / 'styles' / 'cyber_neon.qss']
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise SystemExit('Archivos obligatorios ausentes: ' + ', '.join(missing))
    if not allow_non_windows:
        for package in ('nuitka', 'PySide6', 'imageio_ffmpeg', 'numpy', 'PIL'):
            if importlib.util.find_spec(package) is None:
                raise SystemExit(f'Falta {package}. Ejecuta: python -m pip install -r requirements.txt')
        # imageio-ffmpeg incluye el FFmpeg que el instalador de Nuitka integra.
        import imageio_ffmpeg
        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if not exe.is_file() or exe.suffix.lower() != '.exe':
            raise SystemExit('Instala la versión de imageio-ffmpeg para Windows con su FFmpeg .exe.')
        # Ruta de la rueda Windows que la regla Nuitka busca explícitamente.
        vendored = list((Path(imageio_ffmpeg.__file__).resolve().parent / 'binaries').glob('ffmpeg-win*.exe'))
        if not vendored:
            raise SystemExit('El wheel de imageio-ffmpeg no incluye su ejecutable Windows. Reinstala imageio-ffmpeg.')



def verify_package_config():
    """Evita repetir el error de sangría de la regla FFmpeg.

    Nuitka comprobará el esquema completo; este control es un aviso temprano.
    """
    path = ROOT / 'nuitka-package.config.yml'
    lines = path.read_text(encoding='utf-8').splitlines()
    selector_indent = None
    executable_ok = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- from_filenames:'):
            selector_indent = len(line) - len(line.lstrip())
        elif stripped.startswith('executable:'):
            indent = len(line) - len(line.lstrip())
            if selector_indent is None or indent != selector_indent + 4:
                raise SystemExit(
                    "Regla Nuitka inválida: 'executable' debe ir dentro "
                    "de 'from_filenames' en " + str(path)
                )
            executable_ok = stripped.split(':', 1)[1].strip().strip("\"'") == 'yes'
    if not executable_ok:
        raise SystemExit("Falta 'executable: yes' dentro de from_filenames: " + str(path))


def build_command():
    cmd = [
        sys.executable, '-m', 'nuitka',
        '--mode=onefile',
        '--enable-plugin=pyside6',
        '--include-qt-plugins=multimedia',
        '--windows-console-mode=disable',
        f'--windows-icon-from-ico={ROOT / "assets" / "icons" / "modgames44.ico"}',
        f'--include-data-dir={ROOT / "assets"}=assets',
        f'--user-package-configuration-file={ROOT / "nuitka-package.config.yml"}',
        '--include-package=imageio_ffmpeg',
        '--include-package-data=imageio_ffmpeg',
        '--company-name=ModGames44',
        '--product-name=ModGames44 Video Editor',
        '--file-description=Editor de video ModGames44',
        '--product-version=0.4.12.0',
        '--file-version=0.4.12.0',
        f'--output-filename={APP_NAME}',
        f'--output-dir={DIST}',
        '--remove-output',
        '--assume-yes-for-downloads',
    ]
    # Incluir el conector OpenAI solamente cuando se instale explícitamente.
    if importlib.util.find_spec('openai') is not None:
        cmd.append('--include-package=openai')
        cmd.append('--include-distribution-metadata=openai')
    cmd.append(str(ROOT / 'main.py'))
    return cmd


def main(argv=None):
    parser = argparse.ArgumentParser(description='Compilador Nuitka onefile para ModGames44.')
    parser.add_argument('--dry-run', action='store_true', help='Mostrar comando; no compilar')
    parser.add_argument('--skip-self-test', action='store_true', help='No lanzar verificación tras compilar')
    args = parser.parse_args(argv)
    verify_inputs(allow_non_windows=args.dry_run)
    verify_package_config()
    cmd = build_command()
    print('\nCOMANDO NUITKA:\n' + subprocess.list2cmdline(cmd), flush=True)
    if args.dry_run:
        return 0
    DIST.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(cmd, cwd=ROOT)
    binary = DIST / APP_NAME
    if not binary.is_file():
        raise RuntimeError(f'Nuitka terminó pero no se encontró {binary}')
    print(f'\nEXE GENERADO: {binary} ({binary.stat().st_size / 2**20:.1f} MiB)', flush=True)
    if not args.skip_self_test:
        print('Probando archivos incluidos, Qt Multimedia y FFmpeg...', flush=True)
        try:
            run = subprocess.run([str(binary), '--package-self-test'], timeout=180,
                                 cwd=DIST, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('El auto-test del ejecutable excedió 180 segundos.') from exc
        if run.returncode != 0:
            raise RuntimeError('El EXE se generó, pero su auto-test falló. '
                               'No distribuir hasta revisar Qt Multimedia/FFmpeg.')
        print('Auto-test inicial OK. Falta probar reproducción y exportación reales.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
