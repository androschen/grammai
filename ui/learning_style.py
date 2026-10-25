"""Learning components using the shared app palette."""
from ui.theme_tokens import PALETTES


def learning_palette(widget):
    current=widget
    while current is not None:
        config=getattr(current,'config',None) or getattr(current,'_config',None)
        if config is not None:return PALETTES.get(config.theme,PALETTES['dark'])
        current=current.parentWidget()
    return PALETTES['dark']


def learning_style(theme):
    p=PALETTES.get(theme,PALETTES['dark'])
    return """
QWidget#learningDeck {{ background: {bg}; }}
QWidget#learningCardView {{ background: {surface}; }}
QWidget#learningDeck QLabel {{ color: {ink}; }}
QWidget#learningDeck QLabel#hint, QWidget#learningDeck QLabel#learningCaption, QWidget#learningDeck QLabel#learningPronunciation {{ color: {muted}; }}
QWidget#learningDeck QLabel#learningTitle {{ font-size: 22px; font-weight: 600; }}
QWidget#learningDeck QTabWidget::pane {{ background: transparent; border: none; }}
QWidget#learningDeck QTabBar::tab {{ color: {muted}; padding: 8px 15px; }}
QWidget#learningDeck QTabBar::tab:selected {{ background: {wash}; color: {accent}; }}
QWidget#learningDeck QLineEdit, QWidget#learningDeck QPlainTextEdit, QWidget#learningDeck QComboBox {{ background: {surface}; color: {ink}; border: 1px solid {line}; border-radius: 9px; selection-background-color: {wash}; selection-color: {ink}; }}
QWidget#learningDeck QLineEdit:focus, QWidget#learningDeck QPlainTextEdit:focus, QWidget#learningDeck QComboBox:focus {{ border-color: {accent}; }}
QWidget#learningDeck QComboBox QAbstractItemView {{ background: {surface}; color: {ink}; selection-background-color: {wash}; selection-color: {ink}; border: 1px solid {line}; }}
QWidget#learningDeck QPushButton {{ background: {soft}; color: {ink}; border: 1px solid {line}; border-radius: 9px; padding: 7px 12px; }}
QWidget#learningDeck QPushButton:hover {{ background: {wash}; border-color: {accent}; }}
QWidget#learningDeck QPushButton:disabled {{ background: {bg}; color: {muted}; border-color: {line}; }}
QWidget#learningDeck QPushButton#iconButton {{ background: transparent; border: none; padding: 5px; }}
QWidget#learningDeck QPushButton#iconButton:hover {{ background: {wash}; }}
QWidget#learningDeck QPushButton#learningPrimary {{ background: {accent}; color: {bg}; border-color: {accent}; font-weight: 600; }}
QWidget#learningDeck QPushButton#learningPrimary:disabled {{ background: {soft}; color: {muted}; border-color: {line}; }}
QWidget#learningDeck QListWidget#learningCards {{ background: transparent; color: {ink}; border: none; padding: 0; }}
QWidget#learningDeck QListWidget#learningCards::item, QWidget#learningDeck QListWidget#learningCards::item:selected {{ background: transparent; border: none; padding: 0; }}
QWidget#learningCardView {{ border: 1px solid {line}; border-radius: 14px; }}
QWidget#learningCardView QScrollArea {{ background: transparent; }}
QFrame#learningHero {{ background: transparent; border: none; border-radius: 0; }}
QFrame#learningHero QLabel#learningExpression {{ color: {ink}; font-size: 27px; font-weight: 600; }}
QFrame#learningHero QLabel#learningPronunciation {{ color: {muted}; font-size: 13px; }}
QFrame#learningHero QLabel#learningMeaning {{ color: {ink}; font-size: 18px; }}
QLabel#learningCaption {{ font-size: 12px; color: {muted}; font-weight: 600; }}
QFrame#learningConversation {{ background: transparent; border: none; border-top: 1px solid {line}; border-radius: 0; }}
QFrame#learningConversation QLabel#learningExample {{ font-size: 17px; }}
QFrame#learningWord {{ background: transparent; border: none; border-bottom: 1px solid {line}; border-radius: 0; }}
QFrame#learningWord QLabel#learningTerm {{ color: {accent}; font-size: 16px; font-weight: 600; }}
QFrame#learningWhy {{ background: transparent; border: none; border-top: 1px solid {line}; border-radius: 0; }}
QFrame#learningFlatSection {{ border: none; border-top: 1px solid {line}; background: transparent; }}
QFrame#learningPractice {{ background: {surface}; border: 1px solid {line}; border-radius: 14px; }}
QFrame#learningPractice QLabel#learningPrompt {{ font-size: 24px; font-weight: 600; }}
QFrame#learningPractice QLabel#learningAnswer {{ font-size: 19px; font-weight: 600; }}
QProgressBar#learningProgress {{ background: {soft}; border: none; border-radius: 3px; min-height: 5px; max-height: 5px; }}
QProgressBar#learningProgress::chunk {{ background: {accent}; border: none; border-radius: 3px; }}
""".format(**p)
