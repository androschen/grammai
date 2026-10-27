"""One visual system for Conversation, learning, settings and resource pages."""
from pathlib import Path
from ui.theme_tokens import palette_for
_ASSETS=Path(__file__).parent/'assets'


def style_for(theme='dark'):
    from ui.learning_style import learning_style
    p=palette_for(theme)
    arrows='-light' if theme=='light' else ''
    css="""
QWidget {{ color: {ink}; font-family: 'Segoe UI'; font-size: 13px; }}
QWidget#mainPanel, QDialog, QWidget#settingsPage, QWidget#resourcesPage {{ background: {bg}; }}
QLabel {{ background: transparent; border: none; }}
QLabel#title {{ font-size: 23px; font-weight: 600; }}
QLabel#pageTitle {{ font-size: 20px; font-weight: 600; }}
QLabel#field {{ font-size: 14px; font-weight: 600; }}
QLabel#hint, QLabel#phonetic, QLabel#learningCaption, QLabel#contextPreview {{ color: {muted}; font-size: 12px; }}
QLabel#section {{ color: {muted}; font-size: 12px; font-weight: 600; padding: 8px 0 3px; }}
QLabel#status {{ color: {muted}; font-size: 12px; }}
QWidget#replySuggestions {{ border: none; border-top: 1px solid {line}; background: transparent; }}
QFrame#modelRoleCard, QFrame#componentCard {{ background: {surface}; border: 1px solid {line}; border-radius: 12px; }}
QPushButton#componentSelect {{ text-align: left; border: none; background: transparent; padding: 6px 8px; }}
QPushButton#componentSelect:hover, QPushButton#componentSelect:checked {{ background: {wash}; color: {accent}; }}
QFrame#replyOption {{ background: {surface}; border: 1px solid {line}; border-radius: 10px; }}
QLabel#saveNotice {{ background: {wash}; color: {accent}; border: 1px solid {line}; border-radius: 9px; padding: 10px 16px; }}
QLabel#badge {{ color: {accent}; background: {wash}; padding: 3px 8px; border-radius: 5px; font-size: 11px; }}
QFrame#navigationRail {{ background: {surface}; border: none; border-right: 1px solid {line}; }}
QLabel#railBrand {{ color: {accent}; font-size: 22px; font-weight: 600; min-height: 38px; }}
QFrame#card, QFrame#latestEmpty, QFrame#resourceCard {{ background: {surface}; border: 1px solid {line}; border-radius: 12px; }}
QGroupBox {{ background: {surface}; border: 1px solid {line}; border-radius: 10px; margin-top: 12px; padding: 16px 12px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
QPushButton {{ background: {surface}; border: 1px solid {line}; border-radius: 8px; padding: 7px 11px; font-weight: 500; }}
QPushButton:hover {{ background: {soft}; border-color: {muted}; }}
QPushButton:pressed, QPushButton:checked {{ background: {wash}; color: {accent}; }}
QPushButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {accent}; }}
QPushButton:disabled {{ background: {bg}; color: {muted}; border-color: {line}; }}
QPushButton#primary {{ background: {accent}; color: {bg}; border-color: {accent}; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {soft}; color: {muted}; border-color: {line}; }}
QPushButton#iconButton {{ background: transparent; padding: 5px; border: none; border-radius: 8px; }}
QPushButton#iconButton:hover, QPushButton#iconButton:checked {{ background: {wash}; }}
QPushButton#secondary {{ background: transparent; border: none; padding: 5px 8px; color: {muted}; }}
QPushButton#secondary:hover {{ background: {soft}; color: {ink}; }}
QPushButton#danger {{ color: {alert}; background: transparent; border-color: {alert}; }}
QPushButton#danger:disabled {{ color: {muted}; border-color: {line}; }}
QPushButton#dangerLink {{ color: {alert}; background: transparent; border: none; padding: 5px 0; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {surface}; border: 1px solid {line}; border-radius: 8px; padding: 7px 10px; min-height: 20px; selection-background-color: {wash}; selection-color: {ink}; }}
QProgressBar#speechDownloadProgress {{ background: {line}; border: none; border-radius: 2px; }}
QProgressBar#speechDownloadProgress::chunk {{ background: {accent}; border: none; border-radius: 2px; }}
QProgressBar#cardAudioProgress {{ background: {line}; border: none; border-radius: 2px; min-height: 5px; max-height: 5px; }}
QProgressBar#cardAudioProgress::chunk {{ background: {accent}; border: none; border-radius: 2px; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url('@DOWN@'); width: 14px; height: 14px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 25px; border: none; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 25px; border: none; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url('@UP@'); width: 11px; height: 11px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url('@DOWN@'); width: 11px; height: 11px; }}
QComboBox QAbstractItemView {{ background: {surface}; color: {ink}; selection-background-color: {wash}; selection-color: {ink}; border: 1px solid {line}; padding: 5px; }}
QTabWidget::pane {{ background: transparent; border: none; top: 6px; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 8px 12px; margin-right: 3px; border-radius: 8px; }}
QTabBar::tab:selected {{ background: {wash}; color: {accent}; font-weight: 600; }}
QTabBar::tab:hover {{ background: {soft}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QPlainTextEdit, QTextBrowser, QListWidget {{ background: {surface}; color: {ink}; border: 1px solid {line}; border-radius: 9px; padding: 10px; selection-background-color: {wash}; selection-color: {ink}; }}
QListWidget::item {{ padding: 8px; border-bottom: 1px solid {line}; }}
QListWidget::item:selected {{ background: {wash}; color: {ink}; border-radius: 7px; }}
QListWidget#settingsNavigation {{ border: none; background: transparent; padding: 0; }}
QCheckBox {{ spacing: 7px; color: {muted}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {muted}; border-radius: 5px; background: {surface}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url('@CHECK@'); }}
QSlider::groove:horizontal {{ height: 5px; background: {soft}; border: none; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; background: {accent}; border-radius: 7px; }}
QSplitter::handle {{ background: transparent; width: 16px; }}
QSplitter::handle:hover {{ background: {line}; }}
QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {line}; min-height: 28px; border-radius: 3px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip, QMenu {{ color: {ink}; background: {surface}; border: 1px solid {line}; padding: 6px; }}
QMenu::item:selected {{ background: {wash}; }}
QFrame#HistoryCard {{ background: transparent; border: none; border-bottom: 1px solid {line}; border-radius: 0; }}
QFrame#HistoryCard[selected='true'] {{ background: {wash}; border: none; border-radius: 9px; }}
QFrame#HistoryCard QLabel#originalSpeech {{ font-size: 17px; font-weight: 500; }}
QFrame#HistoryCard QLabel#target, QFrame#HistoryCard QLabel#aiSuggestionText {{ font-size: 14px; }}
QFrame#HistoryCard QLabel#native, QFrame#HistoryCard QLabel#phonetic {{ color: {muted}; font-size: 12px; }}
QLabel#sourceLanguageBadge {{ background: {soft}; color: {muted}; border: none; border-radius: 4px; padding: 2px 4px; font-size: 11px; }}
QLabel#sourceLanguageBadge[language='zh'] {{ color: {zh}; }}
QLabel#sourceLanguageBadge[language='th'] {{ color: {th}; }}
QLabel#sourceLanguageBadge[language='en'] {{ color: {en}; }}
QLabel#sourceLanguageBadge[language='id'] {{ color: {id}; }}
QDialog#sentenceStudy {{ background: {surface}; border: none; border-radius: 10px; }}
QFrame#sentenceDetails {{ background: {surface}; border: 1px solid {line}; border-radius: 12px; }}
QFrame#sentenceReadingSection, QFrame#sentenceTranslationSection {{ background: transparent; border: none; border-bottom: 1px solid {line}; border-radius: 0; }}
QFrame#sentenceHistorySection {{ background: transparent; border: none; }}
QLabel#sentenceOriginal {{ font-size: 19px; font-weight: 500; }}
QLabel#sentenceTranslation {{ font-size: 17px; }}
QTextBrowser#translationHistory {{ background: transparent; border: none; padding: 0; }}
QDialog#saveCardDialog {{ background: {surface}; }}
QLabel#saveExpression {{ font-size: 27px; font-weight: 600; }}
QLabel#saveCaption {{ color: {muted}; font-size: 11px; font-weight: 600; padding-top: 8px; }}
QFrame#saveSection {{ background: transparent; border: none; border-top: 1px solid {line}; border-radius: 0; }}
QPlainTextEdit#saveMeaning {{ background: {surface}; padding: 7px 10px; }}
QLabel#reviewStatus {{ color: {muted}; font-size: 12px; }}
QLabel#contextPreview {{ border-left: 2px solid {line}; padding: 4px 10px; }}
""".format(**p)
    css=css.replace('@DOWN@',(_ASSETS/('chevron'+arrows+'.svg')).as_posix()).replace('@UP@',(_ASSETS/('chevron-up'+arrows+'.svg')).as_posix()).replace('@CHECK@',(_ASSETS/'check.svg').as_posix())
    return css+learning_style(theme)

APP_STYLE=style_for('dark')
