"""Tema compartido Cyber Neon y Cyber Studio, sin afectar estado multimedia."""
from pathlib import Path
from PySide6.QtGui import QColor, QFont, QPalette

PALETTE = {
    'background': '#060c16',
    'surface': '#0b1728',
    'raised': '#152940',
    'text': '#e9f5ff',
    'cyan': '#11dceb',
    'violet': '#cb4af7',
    'yellow': '#ffcc42',
}

STYLE_FILE = Path(__file__).resolve().parents[1] / 'assets' / 'styles' / 'cyber_neon.qss'


def load_style():
    return STYLE_FILE.read_text(encoding='utf-8')


def apply_theme(app):
    app.setFont(QFont('Segoe UI', 10))
    app.setStyleSheet(load_style())
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(PALETTE['background']))
    pal.setColor(QPalette.ColorRole.Base, QColor(PALETTE['surface']))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE['text']))
    pal.setColor(QPalette.ColorRole.Highlight, QColor('#155b84'))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor('white'))
    app.setPalette(pal)
