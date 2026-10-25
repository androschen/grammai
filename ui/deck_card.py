"""Reading-first learning card; corrections are an explicit secondary action."""
import re
from html import escape
from PySide6.QtCore import Qt,Signal,QEvent
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,
    QCheckBox,QPushButton,QScrollArea,QWidget,QFrame,QSizePolicy,QApplication)
from ui.copyable_text import CopyableLabel
from ui.icons import icon_button


class ConversationExample(CopyableLabel):
    """Highlight the saved expression while keeping clipboard text plain."""
    def __init__(self,text,expression,parent=None):
        super().__init__('',parent)
        self.original_text=text;self.expression=expression
        self.setTextFormat(Qt.TextFormat.RichText)
        self.refresh_highlight()

    def refresh_highlight(self):
        from ui.learning_style import learning_palette
        colors=learning_palette(self)
        parts=[];offset=0
        pattern=re.escape(self.expression)
        if self.expression and self.expression[0].isascii() and self.expression[0].isalnum():pattern=r'(?<!\w)'+pattern
        if self.expression and self.expression[-1].isascii() and self.expression[-1].isalnum():pattern+=r'(?!\w)'
        for match in re.finditer(pattern,self.original_text) if self.expression else []:
            parts.append(escape(self.original_text[offset:match.start()]))
            parts.append(f'<span style="background-color:{colors["wash"]};color:{colors["accent"]}">{escape(match.group())}</span>')
            offset=match.end()
        parts.append(escape(self.original_text[offset:]));text=''.join(parts).replace('\n','<br>')
        self.setText(text)

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange,QEvent.Type.StyleChange) and hasattr(self,'original_text'):
            self.refresh_highlight()

    def copy(self):
        QApplication.clipboard().setText(self.selectedText() if self.hasSelectedText() else self.original_text)

    def select_all(self):
        self.setSelection(0,len(self.original_text.encode('utf-16-le'))//2)


class DeckCardContent:

    def __init__(self,parent,config=None,events=None,service=None,embedded=False):
        super().__init__(parent)
        self.setWindowTitle('Learning card')
        if not embedded:
            self.setWindowModality(Qt.WindowModality.WindowModal);self.resize(min(520,self.screen().availableGeometry().width()-40),min(760,self.screen().availableGeometry().height()-50))
        self.setObjectName('learningCardView');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.editing=False
        outer=QVBoxLayout(self);outer.setContentsMargins(16 if embedded else 18,12 if embedded else 14,16 if embedded else 18,12 if embedded else 14);outer.setSpacing(8)
        header=QHBoxLayout()
        self.back=icon_button('back','Back to cards',self);self.back.clicked.connect(self.back_requested.emit);self.back.setVisible(embedded);header.addWidget(self.back)
        title=QLabel('Learning card');title.setObjectName('field');header.addWidget(title);header.addStretch()
        self.edit=icon_button('edit','Edit expression and meaning',self);self.edit.setCheckable(True);self.edit.toggled.connect(self.set_editing);header.addWidget(self.edit)
        self.delete=icon_button('trash','Delete this card',self);header.addWidget(self.delete)
        close=icon_button('close','Close learning card',self);close.clicked.connect(lambda:self.reject() if not embedded else self.back_requested.emit());close.setVisible(not embedded);header.addWidget(close);outer.addLayout(header)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(0,2,0,4);layout.setSpacing(12)
        self.route=QLabel();self.route.setObjectName('hint');self.route.setWordWrap(True);layout.addWidget(self.route)
        if embedded:
            layout.removeWidget(self.route);header.insertWidget(1,self.route);title.hide()
        self.summary=QFrame();self.summary.setObjectName('learningHero');summary=QVBoxLayout(self.summary);summary.setContentsMargins(0,10,0,14);summary.setSpacing(6)
        self.generated_badge=QLabel('AI-generated reply');self.generated_badge.setObjectName('badge');summary.addWidget(self.generated_badge,0,Qt.AlignmentFlag.AlignLeft);self.generated_badge.hide()
        self.expression_text=CopyableLabel();self.expression_text.setObjectName('learningExpression');self.expression_text.setWordWrap(True);summary.addWidget(self.expression_text)
        self.pronunciation=CopyableLabel();self.pronunciation.setObjectName('learningPronunciation');self.pronunciation.setWordWrap(True);summary.addWidget(self.pronunciation)
        self.meaning_text=CopyableLabel();self.meaning_text.setObjectName('learningMeaning');self.meaning_text.setWordWrap(True);summary.addWidget(self.meaning_text);layout.addWidget(self.summary)
        from ui.pronunciation import ListenWidget
        self.listen=ListenWidget(events,self);summary.addWidget(self.listen)
        from ui.card_audio import AudioTransport
        self.audio=AudioTransport(events,self,removable=True);layout.addWidget(self.audio)
        self.edit_fields=QWidget();fields=QVBoxLayout(self.edit_fields);fields.setContentsMargins(0,4,0,8)
        self.original=QPlainTextEdit();self.meaning=QPlainTextEdit();self.notes=QPlainTextEdit()
        self.original.setMaximumHeight(65);self.meaning.setMaximumHeight(65);self.notes.setFixedHeight(66)
        self.original.setAccessibleName('Saved expression or sentence');self.meaning.setAccessibleName('Saved meaning');self.notes.setAccessibleName('Your notes')
        for heading,widget in (('Expression / sentence',self.original),('Meaning',self.meaning)):
            label=QLabel(heading);label.setObjectName('hint');fields.addWidget(label);fields.addWidget(widget)
        layout.addWidget(self.edit_fields);self.edit_fields.hide()
        self.provenance=QFrame();self.provenance.setObjectName('learningConversation');self.details=QVBoxLayout(self.provenance);self.details.setContentsMargins(0,12,0,14);self.details.setSpacing(5);layout.addWidget(self.provenance)
        from ui.card_explanation import CardExplanationWidget
        self.explanation=CardExplanationWidget(config,events,service,self,show_sentence_meaning=False);layout.addWidget(self.explanation)
        self.extra=QWidget();self.extra_details=QVBoxLayout(self.extra);self.extra_details.setContentsMargins(0,0,0,4);self.extra_details.setSpacing(4);layout.addWidget(self.extra)
        label=QLabel('Your notes');label.setObjectName('learningCaption');layout.addWidget(label);layout.addWidget(self.notes)
        self.saved_at=QLabel();self.saved_at.setObjectName('hint');self.saved_at.setWordWrap(True);self.saved_at.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.saved_at);layout.addStretch()
        self.scroll.setWidget(body);outer.addWidget(self.scroll,1)
        self.checked=QCheckBox('I checked the expression and its meaning.');outer.addWidget(self.checked);self.checked.hide()
        footer=QHBoxLayout();self.feedback=QLabel('Saved');self.feedback.setWordWrap(True);self.feedback.setTextFormat(Qt.TextFormat.PlainText);self.feedback.setObjectName('hint');footer.addWidget(self.feedback,1)
        self.save=QPushButton('Save notes');self.save.setObjectName('learningPrimary');footer.addWidget(self.save);outer.addLayout(footer)

    def set_editing(self,enabled):
        self.editing=bool(enabled);self.edit_fields.setVisible(self.editing);self.summary.setVisible(not self.editing)
        self.checked.setVisible(self.editing);self.save.setText('Save changes' if self.editing else 'Save notes')
        self.edit_mode_changed.emit()

    def update_saved_time(self,item):
        from core.card_time import saved_caption
        label,tooltip=saved_caption(item.get('saved_at'))
        self.saved_at.setText(label);self.saved_at.setToolTip(tooltip);self.saved_at.setVisible(bool(item))

    def show_context(self,item):
        generated=item.get('card_type')=='reply'
        self.generated_badge.setVisible(generated)
        self.update_saved_time(item)
        self.audio.bind(item)
        self.listen.bind(item.get('native_text',''),item.get('source_language',''))
        self.edit.blockSignals(True);self.edit.setChecked(False);self.edit.blockSignals(False);self.set_editing(False)
        self.expression_text.setText(item.get('native_text',''));self.meaning_text.setText(item.get('target_text',''))
        for box in (self.details,self.extra_details):
            while box.count():
                widget=box.takeAt(0).widget()
                if widget:widget.deleteLater()
        def add(box,heading,text,large=False):
            if not text:return
            if heading:
                caption=QLabel(heading);caption.setObjectName('learningCaption');box.addWidget(caption)
            value=ConversationExample(text,item.get('native_text',''),self) if large else CopyableLabel(text);value.setWordWrap(True)
            if large:value.setObjectName('learningExample')
            box.addWidget(value)
            return value
        original=item.get('reply_question') if generated else (item.get('original_speech') if item.get('example_role')=='translation' else item.get('example_sentence'))
        original=original or (item.get('native_text','') if item.get('example_role')!='translation' else '')
        add(self.details,'In response to' if generated else 'From your conversation',original,True)
        if original:
            from ml.phonetics import phonetics_auto
            add(self.details,'',phonetics_auto(original))
        explanation=item.get('learning_explanation') or {}
        sentence_meaning=explanation.get('sentence_meaning') or item.get('example_translation','')
        self.example_meaning=add(self.details,'',sentence_meaning)
        if item.get('example_translation') and item['example_translation']!=sentence_meaning:
            add(self.extra_details,'Live translation',item['example_translation'])
        add(self.extra_details,'Usage',' · '.join(x for x in (item.get('usage',''),item.get('usage_note','')) if x))
        add(self.extra_details,'Earlier original dialogue','\n'.join(x.get('text','') for x in item.get('conversation_context',[]) if isinstance(x,dict)))
        add(self.extra_details,'Uncertainty',item.get('uncertainty',''))
        self.provenance.setVisible(self.details.count()>0);self.extra.setVisible(self.extra_details.count()>0)
        self.scroll.verticalScrollBar().setValue(0)

    def deactivate(self):
        self.audio.stop();self.listen.stop()
        self.explanation.cancel_request()


class DeckCardView(DeckCardContent,QWidget):
    edit_mode_changed=Signal()
    back_requested=Signal()

    def __init__(self,parent,config=None,events=None,service=None):
        super().__init__(parent,config,events,service,embedded=True)


class DeckCardDialog(DeckCardContent,QDialog):
    edit_mode_changed=Signal()
    back_requested=Signal()

    def done(self,result):
        self.deactivate();super().done(result)
