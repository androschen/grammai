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
    def __init__(self,config,events,service,payload,phrasebook,parent=None,replays=None):
        super().__init__(parent)
        self.config,self.events,self.service,self.phrasebook=replace(config),events,service,phrasebook
        self.payload=explanation_input(payload)
        # Inference uses a short window; the saved example retains the complete selected sentence.
        self.snapshot={key:payload.get(key,'') for key in ('phrase','sentence','language','original_text','original_language','text_role','example_translation')}
        self.snapshot.update(phrase=self.payload['phrase'],context=self.payload['context'])
        self.token=None;self.value=None;self.waiting=False;self.paused=False;self.closed=False
        self.setObjectName('saveCardDialog');self.setWindowTitle('Save to deck');self.setStyleSheet(style_for(config.theme));self.resize(460,790)
        self.setMinimumWidth(360);self.setMaximumHeight(max(480,self.screen().availableGeometry().height()-64))
        layout=QVBoxLayout(self);layout.setContentsMargins(20,14,20,18);layout.setSpacing(12)
        header=QHBoxLayout();title=QLabel('Save to deck');title.setObjectName('field');header.addWidget(title);header.addStretch()
        from ui.icons import icon_button,set_button_icon
        self.edit_meaning=icon_button('edit','Edit the suggested meaning',self);self.edit_meaning.setCheckable(True);self.edit_meaning.hide()
        close=icon_button('close','Close learning card',self);close.clicked.connect(self.reject);header.addWidget(close);layout.addLayout(header)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();content=QVBoxLayout(body);content.setContentsMargins(0,2,6,4);content.setSpacing(10);content.setAlignment(Qt.AlignmentFlag.AlignTop)
        from ui.save_card import SaveCardFields
        self.form=SaveCardFields(self);self.form.set_context(self.payload['phrase'],phonetics_auto(self.payload['phrase']),self.payload['language'],self.snapshot['sentence'],'',self.payload['text_role'])
        self.form.audio.bind(replays,payload.get('audio_id',''),config,self.snapshot['original_text'] or self.snapshot['sentence'],self.payload['original_language'],events=events)
        self.meaning=self.form.meaning;self.notes=self.form.notes;self.sentence_meaning=CopyableLabel(parent=self);self.sentence_meaning.setWordWrap(True)
        self.meaning.setReadOnly(True);self.meaning.setPlaceholderText('Preparing a contextual meaning…')
        content.addWidget(self.form)
        self.selected_summary=CopyableLabel(parent=self);self.selected_summary.hide();self.meaning_heading=QLabel(self);self.meaning_heading.hide()
        self.usage=CopyableLabel();self.usage.setWordWrap(True);self.usage.setObjectName('hint')
        self.uncertainty=CopyableLabel();self.uncertainty.setWordWrap(True);self.uncertainty.hide()
        self.explanation_toggle=QPushButton('Word explanation & original context');self.explanation_toggle.setCheckable(True);content.addWidget(self.explanation_toggle)
        self.details=QWidget();details=QVBoxLayout(self.details);details.setContentsMargins(0,0,0,0);details.setSpacing(8);details.addWidget(self.sentence_meaning)
        from ui.card_explanation import CardExplanationWidget
        self.explanation=CardExplanationWidget(self.config,events,service,self,show_sentence_meaning=False,regenerate=self.request);details.addWidget(self.explanation)
        if self.payload['text_role']=='translation' and self.snapshot['original_text']:
            heading=QLabel('Original speech');heading.setObjectName('saveCaption');details.addWidget(heading)
            original=CopyableLabel(self.snapshot['original_text']);original.setWordWrap(True);details.addWidget(original)
        context='\n'.join(x['text'] for x in self.payload['context'])
        if context:
            heading=QLabel('Earlier original dialogue');heading.setObjectName('saveCaption');details.addWidget(heading)
            earlier=CopyableLabel(context);earlier.setWordWrap(True);details.addWidget(earlier)
        details.addWidget(self.usage);details.addWidget(self.uncertainty);content.addWidget(self.details);self.details.hide();self.explanation_toggle.toggled.connect(self.details.setVisible)
        scroll.setWidget(body);layout.addWidget(scroll,1)
        self.status=QLabel('Local AI draft · check before saving.');self.status.setObjectName('hint');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        from ui.controls import ToggleSwitch
        self.checked=ToggleSwitch("I've checked the expression and meaning.");layout.addWidget(self.checked)
        row=QHBoxLayout();self.run=QPushButton('Prepare locally');self.run.clicked.connect(self.request);row.addWidget(self.run)
        self.cancel=icon_button('stop','Cancel card preparation',self);self.cancel.clicked.connect(self.cancel_request);self.cancel.hide();row.addWidget(self.cancel);row.addStretch();layout.addLayout(row)
        self.save=QPushButton('Save card');self.save.setObjectName('primary');set_button_icon(self.save,'bookmark',tone='primary');self.save.setEnabled(False);self.save.clicked.connect(self._save);layout.addWidget(self.save)
        self.form.audio.busy_changed.connect(self._save_enabled)
        self.checked.toggled.connect(self._save_enabled);self.meaning.textChanged.connect(self._meaning_changed)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.try_request)
        service.phrase_completed.connect(self.completed)
        QTimer.singleShot(0,self.begin)

    def _save_enabled(self,*args):
        self.save.setEnabled(bool(self.value and self.checked.isChecked() and self.meaning.toPlainText().strip() and not (self.waiting or self.token or self.form.audio.busy)))

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
        self.sentence_meaning.setText(value.get('sentence_meaning',''));self.sentence_meaning.setVisible(bool(value.get('sentence_meaning')))
        self.form.included.setText('Word explanation and original context included.' if value.get('words') else 'Conversation example and original context included.')
        self.explanation.set_data(value if 'words' in value else None,self.payload)
        self.run.setVisible(not value.get('words'))
        self.usage.setText(' · '.join(x for x in (value.get('usage',''),value.get('usage_note','')) if x));self.usage.setVisible(bool(self.usage.text()))
        self.uncertainty.setText('Uncertainty · '+value.get('uncertainty',''));self.uncertainty.setVisible(bool(value.get('uncertainty')))
        self.checked.setChecked(False);self._save_enabled()
        self.status.setText(('Cached draft · no new inference.' if value.get('cached') else 'AI draft · check the meaning before saving.')+(' Translation paused; restart when ready.' if self.paused else ''))

    def _save(self):
        if not self.value or not self.checked.isChecked() or self.token or self.waiting or self.form.audio.busy:return
        snapshot=dict(self.snapshot);value=dict(self.value);meaning=self.meaning.toPlainText();notes=self.notes.toPlainText()
        saved=[]
        def persist(audio):
            saved.append(self.phrasebook.save_vocabulary(snapshot,value,meaning,notes,self.config.analysis_explanation_language,reviewed=True,audio=audio))
        def finished(error):
            if self.closed:return
            if error is not None:
                self.status.setText(error);self._save_enabled();return
            self.checked.setChecked(False)
            self.events.card_saved.emit(saved[0])
            self.accept()
        self.form.audio.commit(persist,finished)

    def cancel_request(self):
        self.waiting=False;self.timer.stop()
        if self.token:self.service.cancel(self.token)
        self.token=None;self.run.show();self.run.setEnabled(True);self.run.setText('Try again');self.cancel.hide();self.meaning.setReadOnly(False)
        self._save_enabled();self.status.setText('Preparation cancelled. Your notes and conversation are preserved.')

    def done(self,result):
        self.form.audio.cancel_pending()
        self.closed=True;self.explanation.dispose();self.cancel_request()
        try:self.service.phrase_completed.disconnect(self.completed)
        except (TypeError,RuntimeError):pass
        super().done(result)
