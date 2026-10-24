"""On-demand local vocabulary drafts with immutable conversation provenance."""
from dataclasses import replace
from uuid import uuid4
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QScrollArea,QWidget,QCheckBox,QPlainTextEdit,QFrame,QSizePolicy)
from ml.phonetics import phonetics_auto
from ml.phrase_explanation import explanation_input
from ui.copyable_text import CopyableLabel
from ui.theme import style_for


class PhraseExplanationDialog(QDialog):
    def __init__(self,config,events,service,payload,phrasebook,parent=None):
        super().__init__(parent)
        self.config,self.events,self.service,self.phrasebook=replace(config),events,service,phrasebook
        self.payload=explanation_input(payload)
        # Inference uses a short window; the saved example retains the complete selected sentence.
        self.snapshot={key:payload.get(key,'') for key in ('phrase','sentence','language','original_text','original_language','text_role','example_translation')}
        self.snapshot.update(phrase=self.payload['phrase'],context=self.payload['context'])
        self.token=None;self.value=None;self.waiting=False;self.paused=False;self.closed=False
        self.setWindowTitle('Save to deck');self.setStyleSheet(style_for(config.theme));self.resize(520,730)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,14,16,14);layout.setSpacing(8)
        header=QHBoxLayout();title=QLabel('Save to deck');title.setObjectName('field');header.addWidget(title);header.addStretch()
        from ui.icons import icon_button
        self.edit_meaning=icon_button('edit','Edit the suggested meaning',self);self.edit_meaning.setCheckable(True);header.addWidget(self.edit_meaning)
        close=icon_button('close','Close learning card',self);close.clicked.connect(self.reject);header.addWidget(close);layout.addLayout(header)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();content=QVBoxLayout(body);content.setContentsMargins(2,2,8,4);content.setSpacing(7)
        from ml.qwen_translator import LANGUAGES
        route=QLabel(LANGUAGES[self.payload['language']]+' → '+LANGUAGES.get(config.analysis_explanation_language,'Indonesian'));route.setObjectName('hint');content.addWidget(route)
        source=self.snapshot['original_text'] if self.payload['text_role']=='translation' else self.snapshot['sentence']
        phrase=CopyableLabel(source or self.payload['phrase']);phrase.setObjectName('title');phrase.setWordWrap(True);content.addWidget(phrase)
        pronunciation=CopyableLabel(phonetics_auto(source or self.payload['phrase']));pronunciation.setObjectName('hint');pronunciation.setWordWrap(True)
        content.addWidget(pronunciation);pronunciation.setVisible(bool(pronunciation.text()))
        self.sentence_meaning=CopyableLabel();self.sentence_meaning.setWordWrap(True);content.addWidget(self.sentence_meaning)
        self.selected_summary=CopyableLabel();self.selected_summary.setObjectName('hint');self.selected_summary.setWordWrap(True);content.addWidget(self.selected_summary)
        self.status=QLabel('Local AI draft · check before saving.');self.status.setObjectName('hint');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);content.addWidget(self.status)
        self.meaning_heading=QLabel('Meaning in this conversation');self.meaning_heading.setObjectName('hint');content.addWidget(self.meaning_heading)
        self.meaning=QPlainTextEdit();self.meaning.setMaximumHeight(74);self.meaning.setPlaceholderText('The contextual meaning will appear here.');self.meaning.setAccessibleName('Meaning in this conversation');content.addWidget(self.meaning);self.meaning.hide();self.meaning_heading.hide()
        self.edit_meaning.toggled.connect(self.meaning.setVisible);self.edit_meaning.toggled.connect(self.meaning_heading.setVisible)
        self.usage=CopyableLabel();self.usage.setWordWrap(True);self.usage.setObjectName('hint');content.addWidget(self.usage)
        self.uncertainty=CopyableLabel();self.uncertainty.setWordWrap(True);content.addWidget(self.uncertainty);self.uncertainty.hide()
        example=QFrame();example.setObjectName('sentenceReadingSection');example.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        example_box=QVBoxLayout(example);example_box.setContentsMargins(12,10,12,10);example_box.setSpacing(5)
        def reading(heading,text):
            if not text:return
            caption=QLabel(heading);caption.setObjectName('hint');example_box.addWidget(caption)
            label=CopyableLabel(text);label.setWordWrap(True);example_box.addWidget(label)
        if self.payload['text_role']=='translation':reading('Selected translation',self.snapshot['sentence'])
        context='\n'.join(x['text'] for x in self.payload['context'])
        reading('Earlier original dialogue',context)
        from ui.card_explanation import CardExplanationWidget
        self.explanation=CardExplanationWidget(self.config,events,service,self,show_sentence_meaning=False,regenerate=self.request)
        content.addWidget(self.explanation)
        content.addWidget(example);example.setVisible(bool(context or self.payload['text_role']=='translation'))
        content.addWidget(self.usage);content.addWidget(self.uncertainty)
        notes_heading=QLabel('Your notes');notes_heading.setObjectName('hint');content.addWidget(notes_heading)
        self.notes=QPlainTextEdit();self.notes.setMaximumHeight(80);self.notes.setPlaceholderText('Your reminder, association or usage note');self.notes.setAccessibleName('Your notes');content.addWidget(self.notes)
        content.addStretch();scroll.setWidget(body);layout.addWidget(scroll,1)
        self.checked=QCheckBox('I checked the expression and its meaning.');layout.addWidget(self.checked)
        row=QHBoxLayout();self.run=QPushButton('Prepare locally');self.run.clicked.connect(self.request)
        self.cancel=icon_button('stop','Cancel card preparation',self);self.cancel.clicked.connect(self.cancel_request);self.cancel.hide()
        self.save=QPushButton('Save card');self.save.setEnabled(False);self.save.clicked.connect(self._save)
        row.addWidget(self.run);row.addWidget(self.cancel);row.addStretch();row.addWidget(self.save);layout.addLayout(row)
        self.checked.toggled.connect(self._save_enabled);self.meaning.textChanged.connect(self._meaning_changed)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.try_request)
        service.phrase_completed.connect(self.completed)
        QTimer.singleShot(0,self.begin)

    def _save_enabled(self,*args):
        self.save.setEnabled(bool(self.value and self.checked.isChecked() and self.meaning.toPlainText().strip() and not (self.waiting or self.token)))

    def _meaning_changed(self):
        self.selected_summary.setText('Expression: '+self.payload['phrase']+' · '+self.meaning.toPlainText())
        self.checked.setChecked(False);self._save_enabled()

    def begin(self):
        if self.closed:return
        if self.events.property('local_translation_owned'):
            self.status.setText('Pause context-aware translation to prepare this card with the same local model.')
            self.run.setText('Pause translation & prepare')
        else:self.request()

    def request(self):
        if self.closed or self.token or self.waiting:return
        if self.events.property('local_translation_owned'):
            self.paused=True;self.events.subtitles_toggled.emit(False)
        self.explanation.set_data(None,None)
        self.value=None;self.checked.setChecked(False);self._save_enabled()
        self.waiting=True;self.run.show();self.run.setEnabled(False);self.run.setText('Preparing…');self.cancel.show()
        self.meaning.setReadOnly(True);self.timer.start();self.try_request()

    def try_request(self):
        if self.closed or not self.waiting:return
        if self.service.closing:
            self.cancel_request();return
        if self.events.property('local_translation_owned') or self.service.busy:
            self.status.setText('Waiting for the current model task. Your notes stay editable.');return
        token='phrase-'+uuid4().hex;self.token=token
        try:accepted=self.service.explain(token,self.config,self.payload)
        except ValueError as exc:
            self.cancel_request();self.status.setText(str(exc));return
        if accepted:
            self.waiting=False;self.timer.stop();self.status.setText('Reading the original speech and nearby dialogue with local Qwen…')
        else:self.token=None

    def completed(self,token,value):
        if self.closed or token!=self.token:return
        self.token=None;self.run.setEnabled(True);self.run.setText('Regenerate');self.cancel.hide();self.meaning.setReadOnly(False)
        if 'error' in value:
            self.value=None;self._save_enabled();self.run.setText('Try again')
            self.status.setText('Could not prepare the card: '+str(value['error'])+'. Your example and notes are preserved.');return
        self.value=dict(value);self.meaning.setPlainText(value['meaning'])
        self.sentence_meaning.setText(value.get('sentence_meaning',''))
        self.explanation.set_data(value if 'words' in value else None,self.payload)
        self.run.setVisible(not value.get('words'))
        self.usage.setText(' · '.join(x for x in (value.get('usage',''),value.get('usage_note','')) if x));self.usage.setVisible(bool(self.usage.text()))
        self.uncertainty.setText('Uncertainty · '+value.get('uncertainty',''));self.uncertainty.setVisible(bool(value.get('uncertainty')))
        self.checked.setChecked(False);self._save_enabled()
        self.status.setText(('Cached draft · no new inference.' if value.get('cached') else 'AI draft · check the meaning before saving.')+(' Translation paused; restart when ready.' if self.paused else ''))

    def _save(self):
        if not self.value or not self.checked.isChecked() or self.token or self.waiting:return
        try:
            self.phrasebook.save_vocabulary(self.snapshot,self.value,self.meaning.toPlainText(),self.notes.toPlainText(),self.config.analysis_explanation_language,reviewed=True)
            self.status.setText('Saved to Learning deck with its original example, context and your notes.')
            self.checked.setChecked(False);self._save_enabled()
        except (ValueError,OSError) as exc:self.status.setText(str(exc))

    def cancel_request(self):
        self.waiting=False;self.timer.stop()
        if self.token:self.service.cancel(self.token)
        self.token=None;self.run.show();self.run.setEnabled(True);self.run.setText('Try again');self.cancel.hide();self.meaning.setReadOnly(False)
        self._save_enabled();self.status.setText('Preparation cancelled. Your notes and conversation are preserved.')

    def done(self,result):
        self.closed=True;self.explanation.dispose();self.cancel_request()
        try:self.service.phrase_completed.disconnect(self.completed)
        except (TypeError,RuntimeError):pass
        super().done(result)
