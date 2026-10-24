"""Reading-first learning card; corrections are an explicit secondary action."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,
    QCheckBox,QPushButton,QScrollArea,QWidget,QFrame,QSizePolicy)
from ui.copyable_text import CopyableLabel
from ui.icons import icon_button


class DeckCardContent:

    def __init__(self,parent,config=None,events=None,service=None,embedded=False):
        super().__init__(parent)
        self.setWindowTitle('Learning card')
        if not embedded:
            self.setWindowModality(Qt.WindowModality.WindowModal);self.resize(min(520,self.screen().availableGeometry().width()-40),min(760,self.screen().availableGeometry().height()-50))
        self.editing=False
        outer=QVBoxLayout(self);outer.setContentsMargins(10 if embedded else 18,0 if embedded else 14,4 if embedded else 18,0 if embedded else 14);outer.setSpacing(8)
        header=QHBoxLayout()
        self.back=icon_button('back','Back to cards',self);self.back.clicked.connect(self.back_requested.emit);self.back.setVisible(embedded);header.addWidget(self.back)
        title=QLabel('Learning card');title.setObjectName('field');header.addWidget(title);header.addStretch()
        self.edit=icon_button('edit','Edit expression and meaning',self);self.edit.setCheckable(True);self.edit.toggled.connect(self.set_editing);header.addWidget(self.edit)
        self.delete=icon_button('trash','Delete this card',self);header.addWidget(self.delete)
        close=icon_button('close','Close learning card',self);close.clicked.connect(lambda:self.reject() if not embedded else self.back_requested.emit());close.setVisible(not embedded);header.addWidget(close);outer.addLayout(header)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(2,2,8,4);layout.setSpacing(6)
        self.route=QLabel();self.route.setObjectName('hint');self.route.setWordWrap(True);layout.addWidget(self.route)
        if embedded:
            layout.removeWidget(self.route);header.insertWidget(1,self.route);title.hide()
        self.summary=QFrame();self.summary.setObjectName('learningFlatSection');summary=QVBoxLayout(self.summary);summary.setContentsMargins(0,8,0,12);summary.setSpacing(4)
        self.expression_text=CopyableLabel();self.expression_text.setObjectName('learningExpression');self.expression_text.setWordWrap(True);summary.addWidget(self.expression_text)
        self.pronunciation=CopyableLabel();self.pronunciation.setObjectName('hint');self.pronunciation.setWordWrap(True);summary.addWidget(self.pronunciation)
        self.meaning_text=CopyableLabel();self.meaning_text.setWordWrap(True);summary.addWidget(self.meaning_text);layout.addWidget(self.summary)
        self.edit_fields=QWidget();fields=QVBoxLayout(self.edit_fields);fields.setContentsMargins(0,4,0,8)
        self.original=QPlainTextEdit();self.meaning=QPlainTextEdit();self.notes=QPlainTextEdit()
        self.original.setMaximumHeight(65);self.meaning.setMaximumHeight(65);self.notes.setFixedHeight(66)
        self.original.setAccessibleName('Saved expression or sentence');self.meaning.setAccessibleName('Saved meaning');self.notes.setAccessibleName('Your notes')
        for heading,widget in (('Expression / sentence',self.original),('Meaning',self.meaning)):
            label=QLabel(heading);label.setObjectName('hint');fields.addWidget(label);fields.addWidget(widget)
        layout.addWidget(self.edit_fields);self.edit_fields.hide()
        self.provenance=QFrame();self.provenance.setObjectName('learningFlatSection');self.details=QVBoxLayout(self.provenance);self.details.setContentsMargins(0,10,0,12);self.details.setSpacing(5);layout.addWidget(self.provenance)
        from ui.card_explanation import CardExplanationWidget
        self.explanation=CardExplanationWidget(config,events,service,self,show_sentence_meaning=False);layout.addWidget(self.explanation)
        self.extra=QWidget();self.extra_details=QVBoxLayout(self.extra);self.extra_details.setContentsMargins(0,0,0,4);self.extra_details.setSpacing(4);layout.addWidget(self.extra)
        label=QLabel('My notes');label.setObjectName('field');layout.addWidget(label);layout.addWidget(self.notes);layout.addStretch()
        self.scroll.setWidget(body);outer.addWidget(self.scroll,1)
        self.checked=QCheckBox('I checked the expression and its meaning.');outer.addWidget(self.checked);self.checked.hide()
        footer=QHBoxLayout();self.feedback=QLabel('Saved');self.feedback.setWordWrap(True);self.feedback.setTextFormat(Qt.TextFormat.PlainText);self.feedback.setObjectName('hint');footer.addWidget(self.feedback,1)
        self.save=QPushButton('Save notes');footer.addWidget(self.save);outer.addLayout(footer)

    def set_editing(self,enabled):
        self.editing=bool(enabled);self.edit_fields.setVisible(self.editing);self.summary.setVisible(not self.editing)
        self.checked.setVisible(self.editing);self.save.setText('Save changes' if self.editing else 'Save notes')
        self.edit_mode_changed.emit()

    def show_context(self,item):
        self.edit.blockSignals(True);self.edit.setChecked(False);self.edit.blockSignals(False);self.set_editing(False)
        self.expression_text.setText(item.get('native_text',''));self.meaning_text.setText(item.get('target_text',''))
        for box in (self.details,self.extra_details):
            while box.count():
                widget=box.takeAt(0).widget()
                if widget:widget.deleteLater()
        def add(box,heading,text,large=False):
            if not text:return
            if heading:
                caption=QLabel(heading);caption.setObjectName('field');box.addWidget(caption)
            value=CopyableLabel(text);value.setWordWrap(True)
            if large:value.setObjectName('learningExample')
            box.addWidget(value)
            return value
        original=item.get('original_speech') if item.get('example_role')=='translation' else item.get('example_sentence')
        original=original or (item.get('native_text','') if item.get('example_role')!='translation' else '')
        add(self.details,'From your conversation',original,True)
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
