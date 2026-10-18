"""Explicit review of a selected sentence, without changing live subtitles."""
from uuid import uuid4
from urllib.parse import urlsplit
from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit
from ml.phonetics import phonetics_auto
from ui.copyable_text import CopyableLabel
from core.config import SOURCE_LANGUAGE_LABELS
from core.revisions import revised_update


def preceding_context(history, selected, limit=5):
    items=history.items() if history is not None else []
    index=next((i for i,item in enumerate(items) if item.uid==selected.uid),0)
    # SessionHistory provides context groups across capture restarts/device changes.
    group=history.group_for(selected.uid) if history is not None else None
    limit=max(0,min(5,limit))
    return [{'text':item.native_text[:1000],'language':item.source_language}
            for item in items[max(0,index-limit):index]
            if history.group_for(item.uid)==group]


class SentenceAnalysis(QWidget):
    applied=Signal(object)

    def __init__(self, study, service, history):
        super().__init__(study)
        self.study,self.service,self.history=study,service,history
        self.token=None
        self.candidate=None
        self._original_context=preceding_context(history,study.subtitle,study.config.analysis_context_sentences)
        layout=QVBoxLayout(self);layout.setContentsMargins(8,12,8,12);layout.setSpacing(9);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.source_label=QLabel()
        layout.addWidget(self.source_label)
        self.source_text=QPlainTextEdit(study.text.toPlainText())
        self.source_text.setAccessibleName('Original transcript used for context analysis')
        self.source_text.setMaximumHeight(64)
        self.source_text.setReadOnly(True)
        self.source_text.hide()
        layout.addWidget(self.source_text)
        context_toggle=QPushButton('Earlier dialogue')
        context_toggle.setCheckable(True)
        layout.addWidget(context_toggle)
        self.context=QPlainTextEdit()
        self.context.setReadOnly(True)
        self.context.setMaximumHeight(72)
        self.context.setPlainText('\n'.join(item['text'] for item in self._original_context) or 'No preceding sentences in this session.')
        layout.addWidget(self.context)
        self.context.hide()
        context_toggle.toggled.connect(self.context.setVisible)
        local=study.config.analysis_provider=='local'
        notice=QLabel('Explains original speech and nearby dialogue locally.' if local else 'Online analysis sends original transcripts, language choices, glossary and saved examples to your selected provider.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row=QHBoxLayout()
        self.run=QPushButton('Explain locally' if local else 'Explain online')
        from ui.icons import icon_button
        self.cancel=icon_button('close','Cancel analysis',self)
        self.cancel.setEnabled(False)
        self.apply=QPushButton('Use revision')
        self.apply.setEnabled(False);self.apply.hide()
        for button in (self.run,self.cancel,self.apply):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        speech={'everyday':'Everyday conversation','neutral':'Neutral speech','formal':'Formal speech'}.get(study.config.analysis_speech_style,'Everyday conversation')
        style={'preserve_tone':'Preserve tone','natural':'Natural translation','literal':'Literal for study'}.get(study.config.analysis_translation_style,'Preserve tone')
        language={'id':'Indonesian','en':'English','zh':'Chinese','th':'Thai'}.get(study.config.analysis_explanation_language,'Indonesian')
        self.feedback=QLabel('')
        self.run.setToolTip(f'{speech} / {style}. Explanations: {language}. Model setup: Settings > Understanding.')
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.output=QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText('Source meaning, a fresh translation, explanation and the previous translation for comparison appear here.')
        layout.addWidget(self.output,1)
        self.output.hide()
        self.result_cards=QWidget()
        self.result_layout=QVBoxLayout(self.result_cards)
        self.result_layout.setContentsMargins(0,0,0,0)
        self.result_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.result_cards,1)
        empty=QLabel('Understand the meaning, informal expressions and possible ambiguity behind this sentence.')
        empty.setWordWrap(True);empty.setObjectName('hint');self.result_layout.addWidget(empty)
        self.save_example=QPushButton('Remember applied correction as a learning example')
        self.save_example.setEnabled(False)
        self.save_example.hide()
        self.save_example.clicked.connect(self._save_example)
        layout.addWidget(self.save_example)
        self.run.clicked.connect(self._run)
        self.cancel.clicked.connect(self.cancel_request)
        self.apply.clicked.connect(self._apply)
        service.completed.connect(self._finished)
        self.source_text.textChanged.connect(self._edit_source)
        study.text.textChanged.connect(self._sync_source)
        study.source.currentIndexChanged.connect(self._source_changed)
        study.target.currentIndexChanged.connect(self._invalidate)
        self._source_changed()

    def _source_changed(self):
        detected=SOURCE_LANGUAGE_LABELS.get(self.study.subtitle.source_language,'Unknown')
        selected=self.study.source.currentText() or 'Choose on Sentence tab'
        self.source_label.setText(f'{selected} → {self.study.target.currentText()}')
        self.source_label.setToolTip(f'Original speech detected as {detected}; analysis uses {selected}')
        self.source_label.setWordWrap(True)
        self._invalidate()

    def _edit_source(self):
        self.study.text.setPlainText(self.source_text.toPlainText())

    def _sync_source(self):
        if self.source_text.toPlainText()!=self.study.text.toPlainText():
            with QSignalBlocker(self.source_text):
                self.source_text.setPlainText(self.study.text.toPlainText())
        self._invalidate()

    def _invalidate(self):
        self.candidate=None
        self.apply.setEnabled(False)
        self.save_example.setEnabled(False)

    def _matches_input(self):
        return (self.study.text.toPlainText().strip()==self.payload['selected_sentence'] and
            self.study.source.currentData()==self.payload['source_language'] and
            self.study.target.currentData()==self.payload['target_language'])

    def _run(self):
        config=self.study.config
        if self.study.events.property('local_translation_owned'):
            self.feedback.setText('Stop context-aware live subtitles before running a manual explanation. Both use the same local model.')
            return
        if not config.analysis_enabled:
            self.feedback.setText('Enable and configure sentence analysis in Settings > Understanding first.')
            return
        text=self.study.text.toPlainText().strip()
        source,target=self.study.source.currentData(),self.study.target.currentData()
        if not text or len(text)>4000 or source is None:
            self.feedback.setText('Choose the spoken language and enter 1-4,000 transcript characters.')
            return
        token=uuid4().hex
        payload={'preceding_sentences':self._original_context,'selected_sentence':text,
            'source_language':source,'target_language':target}
        try:
            accepted=self.service.request(token,config,payload)
        except ValueError as exc:
            self.feedback.setText(str(exc))
            return
        if not accepted:
            self.feedback.setText('Another analysis is finishing. Try again shortly.')
            return
        self.token=token
        self.payload=payload
        self._comparison_translation=self.study.subtitle.target_text
        self.candidate=None
        self.apply.setEnabled(False)
        self.save_example.setEnabled(False)
        self.run.setEnabled(False)
        self.cancel.setEnabled(True)
        self.feedback.setText(('Loading/analyzing on the local Vulkan GPU model' if config.analysis_provider=='local' else 'Analyzing with '+str(urlsplit(config.analysis_endpoint).hostname)+' / '+config.analysis_model)+'. Live subtitles continue.')

    def _finished(self,token,value):
        if token!=self.token:
            return
        self.token=None
        self.run.setEnabled(True)
        self.cancel.setEnabled(False)
        if 'error' in value:
            self.feedback.setText(value['error'])
            return
        if not self._matches_input():
            self.feedback.setText('The original transcript or language changed. Analyze again to use the new input.')
            return
        self.candidate=value
        while self.result_layout.count():
            item=self.result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for heading,key in (('Meaning','source_meaning'),('Translation','translation'),('Informal expressions','explanation'),('Uncertainty','ambiguity')):
            title=QLabel(heading);title.setObjectName('field');self.result_layout.addWidget(title)
            text=CopyableLabel(value[key] or 'No specific ambiguity reported.');text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.result_layout.addWidget(text)
        self.output.setPlainText('Source meaning and intent\n'+value['source_meaning']+
            '\n\nFresh translation from original transcript\n'+value['translation']+'\n'+phonetics_auto(value['translation'])+
            '\n\nSlang and implied meaning\n'+value['explanation']+'\n\nAmbiguity / possible transcription issues\n'+value['ambiguity']+
            '\n\nPrevious translation - comparison only\n'+self._comparison_translation)
        duration=value.get('duration_ms',0)/1000
        self.feedback.setText(('Session cache. ' if value.get('cached') else f'Finished in {duration:.1f}s (includes loading if needed). ')+'Review the suggestion before applying it.')
        self.apply.setEnabled(True);self.apply.show()

    def _apply(self):
        if not self.candidate:
            return
        if not self._matches_input() or self.study.subtitle.target_text!=self._comparison_translation:
            self.feedback.setText('Transcript or language changed. Analyze again before applying.')
            return
        update=revised_update(self.study.subtitle,native_text=self.payload['selected_sentence'],
            native_phonetics=phonetics_auto(self.payload['selected_sentence']),
            target_text=self.candidate['translation'],phonetics=phonetics_auto(self.candidate['translation']),
            source_language=self.payload['source_language'],target_language=self.payload['target_language'],
            translation_status='refined')
        self.applied.emit(update)
        self.apply.setEnabled(False)
        self.save_example.setEnabled(True)
        self._applied_update=update
        self.feedback.setText('Applied to session history. The first transcript and translation remain available in Sentence details.')

    def _save_example(self):
        from core.tutor import save_example
        try:
            if self.study.subtitle!=getattr(self,'_applied_update',None):
                raise ValueError('This sentence changed. Analyze and apply a refinement again before saving an example.')
            save_example(self.study.config,self.study.subtitle.native_text,self.study.subtitle.target_text,
                self.study.subtitle.source_language,self.study.subtitle.target_language)
            self.study.events.state_changed.emit(self.study.config.snapshot())
            self.feedback.setText('Saved locally as a learning example (last 10 retained). Delete examples in Settings > Understanding > Advanced > Conversation.')
            self.save_example.setEnabled(False)
        except ValueError as exc:
            self.feedback.setText(str(exc))

    def cancel_request(self):
        if self.token:
            self.service.cancel(self.token)
        self.token=None
        self.run.setEnabled(True)
        self.cancel.setEnabled(False)
        self.feedback.setText('Cancelled. The in-flight connection will finish or time out in the background; its result will be ignored.')

    def dispose(self):
        self.cancel_request()
        self.service.completed.disconnect(self._finished)
        self.study.text.textChanged.disconnect(self._sync_source)
        self.study.source.currentIndexChanged.disconnect(self._source_changed)
        self.study.target.currentIndexChanged.disconnect(self._invalidate)
