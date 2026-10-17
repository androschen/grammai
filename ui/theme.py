"""Shared visual system: quiet charcoal surfaces, mint accent and rounded controls."""
from pathlib import Path
_ASSETS = Path(__file__).parent / 'assets'
APP_STYLE = """
QWidget { color: #e7eded; font-family: 'Segoe UI'; font-size: 13px; }
QWidget#mainPanel, QDialog { background: #111617; }
QLabel { background: transparent; }
QLabel#title { font-size: 27px; font-weight: 700; color: #f5f8f7; }
QLabel#field { font-weight: 600; color: #e7eded; font-size: 14px; }
QLabel#section { color: #839694; font-size: 10px; font-weight: 700; padding-top: 12px; padding-bottom: 3px; }
QLabel#hint { color: #94a6a3; font-size: 12px; }
QLabel#status { color: #a8bab6; padding: 3px 0px 10px; font-size: 12px; }
QLabel#badge { color: #8bdcbb; background: #20352c; border: 1px solid #2c493a; border-radius: 11px; padding: 4px 11px; font-size: 10px; font-weight: 700; }
QFrame#card { background: #191f20; border: 1px solid #293233; border-radius: 18px; }
QFrame#latestEmpty { background: #1b2624; border: 1px solid #30443e; border-radius: 18px; }
QGroupBox { background: #191f20; border: 1px solid #293233; border-radius: 14px; margin-top: 12px; padding: 18px 14px 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
QPushButton { background: #242d2d; border: 1px solid #303d3b; border-radius: 10px; padding: 9px 15px; font-weight: 500; }
QPushButton:hover { background: #2e3b37; border-color: #50665e; }
QPushButton:pressed { background: #344c41; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border: 1px solid #89dcba; }
QPushButton#toggle { background: #b3f2ce; color: #142b20; border: 1px solid #b3f2ce; border-radius: 12px; font-size: 14px; font-weight: 700; padding: 14px 20px; }
QPushButton#toggle:hover { background: #c9f9dd; }
QPushButton#toggle[active='true'] { background: #2b3d35; color: #b3f2ce; border-color: #4c6e5a; }
QPushButton#secondary { background: transparent; border-color: transparent; color: #a8bcb5; padding: 6px 10px; }
QPushButton#secondary:hover { background: #293630; color: #d2f8e2; }
QPushButton:disabled { color: #667772; background: #202827; border-color: #28312f; }
QComboBox, QSpinBox, QLineEdit { background: #202829; border: 1px solid #33403e; border-radius: 10px; padding: 8px 12px; min-height: 22px; selection-background-color: #355c49; }
QComboBox { padding-right: 30px; }
QComboBox:hover, QSpinBox:hover, QLineEdit:hover { border-color: #52665d; }
QSpinBox { padding-right: 32px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: none; background: transparent; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; border: none; background: transparent; }
QSpinBox::up-arrow { image: url('@UP@'); width: 12px; height: 12px; }
QSpinBox::down-arrow { image: url('@CHEVRON@'); width: 12px; height: 12px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url('@CHEVRON@'); width: 16px; height: 16px; }
QComboBox QAbstractItemView { background: #232e2b; color: #e7eded; selection-background-color: #375549; border: 1px solid #445c51; padding: 6px; outline: none; }
QTabWidget::pane { border: none; background: #181f20; border-radius: 14px; top: 8px; }
QTabBar::tab { background: transparent; color: #94a6a3; border: none; border-radius: 9px; padding: 10px 18px; margin: 0px 5px 0px 0px; }
QTabBar::tab:hover { background: #202d28; color: #e3ede7; }
QTabBar::tab:selected { background: #2a4236; color: #b8f2d0; font-weight: 600; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPlainTextEdit { background: #171e1e; border: 1px solid #33403b; border-radius: 12px; padding: 12px; selection-background-color: #355c49; }
QCheckBox { spacing: 8px; color: #b4c6bf; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #52645b; border-radius: 5px; background: #202829; }
QCheckBox::indicator:checked { background: #b3f2ce; border-color: #b3f2ce; image: url('@CHECK@'); }
QSplitter::handle { background: transparent; width: 18px; }
QSplitter::handle:hover { background: #26372e; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: #3d5147; min-height: 28px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { color: #e7eded; background: #26332e; border: 1px solid #5b7567; padding: 6px; }
""".replace('@CHEVRON@', (_ASSETS / 'chevron.svg').as_posix()).replace('@CHECK@', (_ASSETS / 'check.svg').as_posix()).replace('@UP@', (_ASSETS / 'chevron-up.svg').as_posix())


# History inherits the window theme, so existing rows recolor without rebuilding.
APP_STYLE += """
QFrame#HistoryCard { background: #1b2322; border: 1px solid #2c3933; border-radius: 8px; }
QFrame#HistoryCard[featured="true"] { background: #1c2b25; border-color: #3b5747; border-radius: 18px; }
QFrame#HistoryCard QLabel#phonetic { color: #a5c5b2; font-size: 12px; }
QFrame#HistoryCard QLabel#target { color: #f1f8f4; font-size: 13px; font-weight: 600; }
QFrame#HistoryCard[featured="true"] QLabel#target { font-size: 22px; }
QFrame#HistoryCard QLabel#native { color: #99aca1; font-size: 12px; }
QFrame#HistoryCard QPushButton { background: transparent; color: #a3bfaf; border: none; border-radius: 5px; padding: 3px 6px; font-size: 11px; }
QFrame#HistoryCard QPushButton:hover, QFrame#HistoryCard QPushButton:checked { background: #34493e; color: #def6e7; }
"""

_LIGHT = {
    '#e7eded':'#24372e', '#111617':'#f3f6f3', '#f5f8f7':'#152c21',
    '#839694':'#5a7164', '#94a6a3':'#5a7064', '#a8bab6':'#526c5d',
    '#8bdcbb':'#235f41', '#20352c':'#dfefe3', '#2c493a':'#bed9c6',
    '#191f20':'#ffffff', '#293233':'#dce6de', '#1b2624':'#e9f4eb', '#30443e':'#c9dfcf',
    '#242d2d':'#e8eeea', '#303d3b':'#cedbd1', '#2e3b37':'#dce9df', '#50665e':'#86a691',
    '#344c41':'#c8dfce', '#89dcba':'#367b50', '#b3f2ce':'#b3f2ce', '#142b20':'#142b20',
    '#c9f9dd':'#c4f8d8', '#2b3d35':'#dcefe1', '#4c6e5a':'#9abda5', '#a8bcb5':'#43664e',
    '#293630':'#d8e9dd', '#d2f8e2':'#234e33', '#667772':'#7d8e83', '#202827':'#ebefec',
    '#28312f':'#dbe3dd', '#202829':'#f5f8f5', '#33403e':'#cbd9cf', '#355c49':'#bdddc6',
    '#52665d':'#7c9d86', '#232e2b':'#ffffff', '#375549':'#d9eddf', '#445c51':'#adccb7',
    '#181f20':'#ffffff', '#202d28':'#e2eee5', '#e3ede7':'#244c32', '#2a4236':'#d8ecdf',
    '#b8f2d0':'#285b39', '#171e1e':'#f7faf7', '#33403b':'#ccdbd0', '#b4c6bf':'#476352',
    '#52645b':'#9bb5a3', '#26372e':'#d5e6da', '#3d5147':'#afc5b5', '#26332e':'#edf5ef',
    '#5b7567':'#a8c4b1', '#1b2322':'#ffffff', '#2c3933':'#dde7e0', '#1c2b25':'#e8f4ec',
    '#3b5747':'#c4ddcc', '#a5c5b2':'#476f52', '#f1f8f4':'#203c2a', '#99aca1':'#526d5b',
    '#a3bfaf':'#466c52', '#34493e':'#d9eadd', '#def6e7':'#224e31',
}


def style_for(theme='dark'):
    import re
    if theme != 'light':
        return APP_STYLE
    light = re.sub(r'#[0-9a-fA-F]{6}', lambda m: _LIGHT.get(m.group().lower(), m.group()), APP_STYLE)
    light = light.replace("chevron.svg", "chevron-light.svg").replace("chevron-up.svg", "chevron-up-light.svg")
    return light + """
QPushButton#toggle[active='true'] { color: #285b39; }
"""
