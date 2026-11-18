"""Acceso al código de MainWindow, repartido en ui/main_window.py y mixins.

Desde v0.6.6 los métodos de la ventana están en ui/main_window_parts/*.py.
Las pruebas que inspeccionan el código (sin Qt) usan estas funciones.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / 'ui' / 'main_window.py', *sorted((ROOT / 'ui' / 'main_window_parts').glob('*.py'))]


def main_window_source():
    return '\n'.join(path.read_text(encoding='utf-8') for path in FILES)


def main_window_method(name):
    """(FunctionDef, ruta) del método `name` de MainWindow o de sus mixins."""
    for path in FILES:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef) and (cls.name == 'MainWindow' or cls.name.endswith('Mixin')):
                for node in cls.body:
                    if isinstance(node, ast.FunctionDef) and node.name == name:
                        return node, path
    raise LookupError(name)
