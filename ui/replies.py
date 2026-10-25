"""On-demand speaking replies, bound to original speech; no typing or scoring."""
from dataclasses import replace
from uuid import uuid4
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFrame,QDialog,QScrollArea
from ui.copyable_text import CopyableLabel
from ui.icons import icon_button


class ReplySaveDialog(QDialog):
    def __init__(self,owner,reply,payload,config,book,events):
        super().__init__(owner);self.book,self.events,self.config=book,events,replace(config)
        self.reply=dict(reply);self.payload=dict(payload,context=[dict(x) for x in payload['context']]);self.stale=False
        self.setObjectName('saveCardDialog');self.setWindowTitle('Save reply to deck');self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(460,min(680,self.screen().availableGeometry().height()-64))
        outer=QVBoxLayout(self);outer.setContentsMargins(20,14,20,18);outer.setSpacing(12)
        header=QHBoxLayout();title=QLabel('Save to deck');title.setObjectName('field');header.addWidget(title);header.addStretch()
        close=icon_button('close','Close Save to deck',self);close.clicked.connect(self.reject);header.addWidget(close);outer.addLayout(header)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(0,0,4,0)
        badge=QLabel('AI-generated reply');badge.setObjectName('badge');box.addWidget(badge,0,Qt.AlignmentFlag.AlignLeft)
        from ui.save_card import SaveCardFields
        self.form=SaveCardFields(self);self.form.set_context(reply['text'],reply.get('pronunciation',''),payload['language'])
        self.form.audio.hide();box.addWidget(self.form)
        self.form.meaning.setPlainText(reply['meaning']);self.form.notes.setPlaceholderText('When would you use this reply?')
        # Keep the heard question distinct from the reply. It was never spoken in this clip.
        heading=QLabel('IN RESPONSE TO');heading.setObjectName('saveCaption')
        self.form.layout().insertWidget(self.form.layout().indexOf(self.form.notes_section),heading)
        question=CopyableLabel(payload['text']);question.setTextFormat(Qt.TextFormat.PlainText);question.setWordWrap(True)
        self.form.layout().insertWidget(self.form.layout().indexOf(self.form.notes_section),question)
        audio_note=QLabel('No recording · this reply was generated');audio_note.setObjectName('hint');audio_note.setWordWrap(True)
        self.form.layout().insertWidget(self.form.layout().indexOf(self.form.notes_section),audio_note)
        box.addStretch();scroll.setWidget(body);outer.addWidget(scroll,1)
        self.status=QLabel();self.status.setObjectName('hint');self.status.setTextFormat(Qt.TextFormat.PlainText);self.status.setWordWrap(True);outer.addWidget(self.status)
        from ui.controls import ToggleSwitch
        self.checked=ToggleSwitch('I’ve checked the reply and its meaning.');outer.addWidget(self.checked)
        self.save=QPushButton('Save card');self.save.setObjectName('primary');self.save.clicked.connect(self.commit);outer.addWidget(self.save)
        self.checked.toggled.connect(self.enabled);self.form.meaning.textChanged.connect(lambda:self.checked.setChecked(False));self.form.meaning.textChanged.connect(self.enabled);self.enabled()

    def enabled(self,*args):self.save.setEnabled(self.checked.isChecked() and bool(self.form.meaning.toPlainText().strip()) and not self.stale)

    def invalidate(self):
        self.stale=True;self.enabled();self.status.setText('Original speech changed. Close this popup and check fresh suggestions. Your notes are kept here.')

    def commit(self):
        if not self.save.isEnabled():return
        try:
            item=self.book.save_reply(self.payload,self.reply,self.form.meaning.toPlainText(),self.form.notes.toPlainText(),self.config.analysis_explanation_language,reviewed=True)
        except (ValueError,OSError) as exc:self.status.setText(str(exc));return
        self.events.card_saved.emit(item);self.accept()


class ReplySuggestionsWidget(QWidget):
    def __init__(self,study,service,history):
        super().__init__(study)
        service=service if hasattr(service,'replies_completed') else None
        self.study,self.service,self.history=study,service,history
        self.listeners=[]
        self.events=study.events;self.payload=None;self.signature=None;self.value=None;self.pending=False;self.token=None;self.claimed=False;self.disposed=False;self.popup=None
        self.setObjectName('replySuggestions');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        box=QVBoxLayout(self);box.setContentsMargins(10,12,10,10);box.setSpacing(7)
        row=QHBoxLayout();title=QLabel('How could I reply?');title.setObjectName('field');row.addWidget(title,1)
        self.cancel=icon_button('stop','Cancel reply suggestions',self);self.cancel.clicked.connect(self.cancel_request);self.cancel.hide();row.addWidget(self.cancel);box.addLayout(row)
        hint=QLabel('Choose what fits your situation. Say it aloud.');hint.setObjectName('hint');hint.setWordWrap(True);box.addWidget(hint)
        self.cards=QWidget();self.rows=QVBoxLayout(self.cards);self.rows.setContentsMargins(0,4,0,0);self.rows.setSpacing(8);box.addWidget(self.cards)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName('hint');self.status.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.status)
        self.run=QPushButton('Suggest replies');self.run.clicked.connect(self.request);box.addWidget(self.run)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.try_request)
        if service:service.replies_completed.connect(self.completed)
        self.hide()

    def sync(self):
        from ui.analysis import preceding_context
        from ml.reply_suggestions import reply_input
        s=self.study
        try:
            if s._busy or s._proposal is not None or s.text.toPlainText()!=s.subtitle.native_text or s.source.currentData()!=s.subtitle.source_language:
                raise ValueError('Finish reviewing the original transcript before suggesting replies.')
            payload=reply_input(dict(text=s.subtitle.native_text,language=s.subtitle.source_language,context=preceding_context(self.history,s.subtitle,2)))
            key=(payload['text'],payload['language'],tuple((x['text'],x['language']) for x in payload['context']),s.config.analysis_explanation_language,s.config.analysis_gguf,s.config.analysis_executable,s.config.analysis_context_tokens)
        except ValueError as exc:
            payload=None;key=None;message=str(exc)
        if key!=self.signature or payload is None:
            self.cancel_request();self.value=None
            self._clear_listeners()
            while self.rows.count():
                child=self.rows.takeAt(0).widget()
                if child:child.deleteLater()
            if self.popup and self.popup.isVisible():self.popup.invalidate()
            self.signature=key;self.payload=payload;self.run.show();self.status.clear()
        self.run.setEnabled(bool(payload and self.service))
        if payload is None:self.status.setText(message)
        elif self.service is None:self.status.setText('Local AI is unavailable in this window.')
        return payload is not None

    def set_open(self,opened):
        self.setVisible(opened)
        if not opened:self.cancel_request();return
        if self.sync() and self.value is None:self.request()

    def request(self):
        if self.disposed or self.pending or self.token or not self.service:return
        if not self.sync():return
        if self.events.property('local_translation_owned'):
            self.status.setText('Pause live translation with the Play/Pause control to use its local model for replies.');return
        self.pending=True;self.run.setEnabled(False);self.cancel.show()
        self.events.setProperty('learning_explanation_pending',int(self.events.property('learning_explanation_pending') or 0)+1);self.claimed=True
        self.status.setText('Waiting for the current local model task…');self.timer.start();self.try_request()

    def try_request(self):
        if not self.pending or self.disposed:return
        if self.service.closing:self.cancel_request();return
        token='reply-'+uuid4().hex
        try:accepted=self.service.suggest_replies(token,replace(self.study.config),self.payload)
        except ValueError as exc:self.cancel_request();self.status.setText(str(exc));return
        if accepted:
            self.token=token;self.pending=False;self.timer.stop();self.status.setText('Suggesting two short replies locally…')

    def completed(self,token,value):
        if self.disposed or token!=self.token:return
        self.token=None;self.release();self.timer.stop();self.cancel.hide();self.run.setEnabled(True)
        if 'error' in value:self.status.setText(str(value['error']));return
        from ml.reply_suggestions import validate_replies
        try:clean=validate_replies(value,self.payload,self.study.config.analysis_explanation_language)
        except ValueError as exc:self.status.setText(str(exc));return
        self.value=clean;self.run.hide()
        if clean['status']=='needs_context':self.status.setText(clean['reason']);return
        self.status.setText(('Cached local AI suggestions' if value.get('cached') else 'Local AI suggestions')+(' · '+clean['reason'] if clean['reason'] else ''))
        for reply in clean['replies']:
            frame=QFrame();frame.setObjectName('replyOption');row=QVBoxLayout(frame);row.setContentsMargins(12,10,12,10);row.setSpacing(4)
            head=QHBoxLayout();label=QLabel(reply['label']);label.setObjectName('hint');label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);head.addWidget(label,1)
            save=icon_button('bookmark','Save this AI-generated reply to deck',self);save.clicked.connect(lambda checked=False,r=dict(reply):self.save_reply(r));head.addWidget(save);row.addLayout(head)
            for text,name in ((reply['text'],'sentenceOriginal'),(reply['pronunciation'],'phonetic'),(reply['meaning'],'')):
                if text:
                    label=CopyableLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setObjectName(name);label.setWordWrap(True);row.addWidget(label)
            from ui.pronunciation import ListenWidget
            listen=ListenWidget(self.events,frame);listen.bind(reply['text'],self.payload['language']);row.addWidget(listen);self.listeners.append(listen)
            self.rows.addWidget(frame)

    def _clear_listeners(self):
        for listen in self.listeners:listen.dispose()
        self.listeners=[]

    def hideEvent(self,event):
        for listen in self.listeners:listen.stop()
        super().hideEvent(event)

    def save_reply(self,reply):
        previous=self.signature
        if not self.sync() or previous!=self.signature or not self.value:return
        if self.popup is not None:self.popup.reject();self.popup.deleteLater()
        self.popup=ReplySaveDialog(self,reply,self.payload,self.study.config,self.study.phrasebook,self.events);self.popup.open()

    def release(self):
        if self.claimed:self.events.setProperty('learning_explanation_pending',max(0,int(self.events.property('learning_explanation_pending') or 0)-1))
        self.claimed=False

    def cancel_request(self):
        if self.token and self.service:self.service.cancel(self.token)
        self.token=None;self.pending=False;self.timer.stop();self.cancel.hide();self.release()
        self.run.setEnabled(bool(self.payload and self.service))

    def dispose(self):
        if self.disposed:return
        self.disposed=True;self.cancel_request();self._clear_listeners()
        if self.popup:self.popup.reject()
        if self.service:
            try:self.service.replies_completed.disconnect(self.completed)
            except (RuntimeError,TypeError):pass
