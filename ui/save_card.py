"""Shared compact save form for vocabulary drafts and full sentence cards."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPlainTextEdit,QFrame,QSizePolicy
from ui.copyable_text import CopyableLabel
from ui.history import source_language_badge
from ui.deck_card import ConversationExample


class CompactMeaningEdit(QPlainTextEdit):
    """Keep short meanings compact; allow longer edits without a growing popup."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('saveMeaning')
        self.setAccessibleName('Meaning to save');self.setTabChangesFocus(True)
        self.document().setDocumentMargin(0)
        self.textChanged.connect(self.fit_content)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_content)
        self.setFixedHeight(38)

    def fit_content(self,*args):
        lines=max(1,self.document().documentLayout().documentSize().height())
        self.setFixedHeight(min(96,max(38,int(lines*self.fontMetrics().lineSpacing())+18)))

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_content()


class SaveCardFields(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('saveCardFields');self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.badge=source_language_badge('');layout.addWidget(self.badge,0,Qt.AlignmentFlag.AlignLeft)
        self.expression=CopyableLabel();self.expression.setObjectName('saveExpression');self.expression.setWordWrap(True);layout.addWidget(self.expression)
        self.pronunciation=CopyableLabel();self.pronunciation.setObjectName('hint');self.pronunciation.setWordWrap(True);layout.addWidget(self.pronunciation)
        caption=QLabel('MEANING');caption.setObjectName('saveCaption');layout.addWidget(caption)
        self.meaning=CompactMeaningEdit();layout.addWidget(self.meaning)
        self.example_section=QFrame();self.example_section.setObjectName('saveSection');self.example_section.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum);self.example_box=QVBoxLayout(self.example_section);self.example_box.setContentsMargins(0,14,0,12);self.example_box.setSpacing(6)
        self.example_caption=QLabel('CONVERSATION EXAMPLE');self.example_caption.setObjectName('saveCaption');self.example_box.addWidget(self.example_caption)
        self.example=None
        self.example_translation=CopyableLabel();self.example_translation.setWordWrap(True);self.example_translation.setObjectName('hint');self.example_box.addWidget(self.example_translation)
        self.included=QLabel();self.included.setObjectName('hint');self.included.setWordWrap(True);self.example_box.addWidget(self.included)
        layout.addWidget(self.example_section)
        from ui.card_audio import SaveAudioWidget
        self.audio=SaveAudioWidget(self);layout.addWidget(self.audio)
        self.notes_section=QFrame();self.notes_section.setObjectName('saveSection');self.notes_section.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum);box=QVBoxLayout(self.notes_section);box.setContentsMargins(0,14,0,0);box.setSpacing(6);box.setAlignment(Qt.AlignmentFlag.AlignTop)
        caption=QLabel('YOUR NOTES');caption.setObjectName('saveCaption');box.addWidget(caption)
        self.notes=QPlainTextEdit();self.notes.setFixedHeight(76);self.notes.setAccessibleName('Your notes');self.notes.setPlaceholderText('Your reminder, association or usage note');box.addWidget(self.notes);layout.addWidget(self.notes_section)

    def set_context(self,expression,pronunciation,language,example='',translation='',role='original'):
        codes={'zh':('CN','Chinese'),'th':('TH','Thai'),'en':('EN','English'),'id':('ID','Indonesian')}
        code,name=codes.get(language,('??','Unknown'));self.badge.setText(code);self.badge.setProperty('language',language);self.badge.setToolTip('Expression language: '+name);self.badge.setAccessibleName('Expression language: '+name)
        self.badge.style().unpolish(self.badge);self.badge.style().polish(self.badge)
        self.expression.setText(expression);self.pronunciation.setText(pronunciation);self.pronunciation.setVisible(bool(pronunciation))
        if self.example is not None:self.example_box.removeWidget(self.example);self.example.deleteLater()
        self.example=ConversationExample(example,expression,self);self.example.setWordWrap(True);self.example_box.insertWidget(1,self.example)
        self.example_caption.setText('SELECTED TRANSLATION EXAMPLE' if role=='translation' else 'CONVERSATION EXAMPLE')
        self.example_translation.setText(translation);self.example_translation.setVisible(bool(translation))
        self.example_section.setVisible(bool(example and example!=expression))
