"""One explicit local explanation request; no background batch inference."""
from uuid import uuid4
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,QWidget,QCheckBox
from core.events import SubtitleUpdate
from ml.phonetics import phonetics_auto
from ml.phrase_explanation import explanation_input
from ui.copyable_text import CopyableLabel
from ui.theme import style_for


class PhraseExplanationDialog(QDialog):
    def __init__(self,config,events,service,payload,phrasebook,parent=None):
        super().__init__(parent)
        self.config,self.events,self.service,self.phrasebook=config,events,service,phrasebook
        self.payload=explanation_input(payload);self.token=None;self.value=None;self.waiting=False;self.paused=False;self.closed=False
        self.setWindowTitle('Explain selected phrase');self.setStyleSheet(style_for(config.theme));self.resize(510,620)
        layout=QVBoxLayout(self);layout.setContentsMargins(14,14,14,14);layout.setSpacing(8)
        phrase=CopyableLabel(self.payload['phrase']);phrase.setObjectName('title');phrase.setWordWrap(True);layout.addWidget(phrase)
        pronunciation=CopyableLabel(phonetics_auto(self.payload['phrase']));pronunciation.setWordWrap(True);layout.addWidget(pronunciation)
        note=QLabel('Local AI draft - check the meaning before saving.')
        note.setWordWrap(True);note.setObjectName('hint');layout.addWidget(note)
        sentence=CopyableLabel(self.payload['sentence']);sentence.setWordWrap(True);layout.addWidget(sentence)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        body=QWidget();self.output=QVBoxLayout(body);self.output.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);layout.addWidget(scroll,1)
        self.checked=QCheckBox('I checked the phrase and its meaning');layout.addWidget(self.checked)
        self.save=QPushButton('Save phrase');self.save.setEnabled(False);self.save.clicked.connect(self._save);layout.addWidget(self.save)
        self.checked.toggled.connect(lambda checked:self.save.setEnabled(bool(checked and self.value)))
        row=QHBoxLayout();self.run=QPushButton('Explain locally');self.run.clicked.connect(self.request)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(self.cancel_request)
        from ui.icons import icon_button
        close=icon_button('close','Close explanation',self);close.clicked.connect(self.close)
        for b in (self.run,self.cancel,close):row.addWidget(b)
        layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.try_request)
        service.phrase_completed.connect(self.completed)
        QTimer.singleShot(0,self.begin)

    def begin(self):
        if self.closed:return
        if self.events.property('local_translation_owned'):
            self.status.setText('Context-aware subtitles own the local model. Pause them to explain this phrase. You can restart translation afterward.')
            self.run.setText('Pause subtitles and explain')
        else:self.request()

    def request(self):
        if self.closed or self.token or self.waiting:return
        if self.events.property('local_translation_owned'):
            self.paused=True;self.events.subtitles_toggled.emit(False)
        self.waiting=True;self.run.setEnabled(False);self.timer.start();self.try_request()

    def try_request(self):
        if self.closed or not self.waiting:return
        if self.events.property('local_translation_owned') or self.service.busy:
            self.status.setText('Waiting for the current model task. No extra model is loaded.');return
        token='phrase-'+uuid4().hex;self.token=token
        try:accepted=self.service.explain(token,self.config,self.payload)
        except ValueError as exc:
            self.cancel_request();self.status.setText(str(exc));return
        if accepted:
            self.waiting=False;self.timer.stop();self.status.setText('Explaining on your local GPU...')
        else:
            self.token=None
            if self.service.closing:self.cancel_request()

    def completed(self,token,value):
        if self.closed or token!=self.token:return
        self.token=None;self.run.setEnabled(True);self.run.setText('Explain again')
        if 'error' in value:
            self.status.setText(value['error']);return
        self.value=value
        while self.output.count():
            child=self.output.takeAt(0).widget()
            if child:child.deleteLater()
        for heading,key in (('Meaning','meaning'),('Tone / register','usage'),('Example','example'),('Uncertainty','uncertainty')):
            if key=='uncertainty' and not value[key]:continue
            title=QLabel(heading);title.setObjectName('field');self.output.addWidget(title)
            text=CopyableLabel(value[key] or 'No example provided.');text.setWordWrap(True);self.output.addWidget(text)
        self.checked.setChecked(False);self.save.setEnabled(False)
        self.status.setText(('Session cache - no new inference.' if value.get('cached') else f"Finished in {value.get('duration_ms',0)/1000:.1f}s, including loading.")+(' Translation is paused; restart it when ready.' if self.paused else ''))

    def _save(self):
        if not self.value or not self.checked.isChecked():return
        phrase=self.payload['phrase'];meaning=self.value['meaning']
        update=SubtitleUpdate(phonetics_auto(meaning),meaning,phrase,native_phonetics=phonetics_auto(phrase),
            source_language=self.payload['language'],target_language=self.config.analysis_explanation_language)
        notes='Example: '+self.value['example']+'\nUsage: '+self.value['usage']+'\nUncertainty: '+self.value['uncertainty']
        try:
            self.phrasebook.save(update,notes[:4000],reviewed=True)
            self.status.setText('Saved to Learning deck as text only. Reviewed by you, not guaranteed correct.')
        except (ValueError,OSError) as exc:self.status.setText(str(exc))

    def cancel_request(self):
        self.waiting=False;self.timer.stop()
        if self.token:self.service.cancel(self.token)
        self.token=None;self.run.setEnabled(True);self.status.setText('Cancelled.')

    def done(self,result):
        self.closed=True
        self.cancel_request()
        try:self.service.phrase_completed.disconnect(self.completed)
        except (TypeError,RuntimeError):pass
        super().done(result)
