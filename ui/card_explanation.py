"""Reusable saved explanations and explicit, serialized local tutor requests."""
from uuid import uuid4
from dataclasses import replace
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QFrame,QGridLayout
from ui.copyable_text import CopyableLabel


class CardExplanationWidget(QWidget):
    def __init__(self,config=None,events=None,service=None,parent=None,show_sentence_meaning=True,regenerate=None):
        super().__init__(parent)
        self.config,self.events,self.service=config,events,service
        self.show_sentence_meaning=show_sentence_meaning;self.refresh=None;self.regenerate=regenerate
        self.payload=None;self.value=None;self.token=None;self.pending=None;self.persist=None;self.disposed=False;self.claimed=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,4);layout.setSpacing(8)
        self.reading=QWidget();self.reading_layout=QVBoxLayout(self.reading);self.reading_layout.setContentsMargins(0,0,0,0);layout.addWidget(self.reading)
        self.generate=QPushButton('Explain sentence');self.generate.clicked.connect(lambda:self.request());layout.addWidget(self.generate)
        self.questions=QWidget();row=QHBoxLayout(self.questions);row.setContentsMargins(0,0,0,0)
        self.question=QLineEdit();self.question.setMaxLength(400);self.question.setPlaceholderText('Ask about this sentence…');self.question.setAccessibleName('Question about the original sentence')
        self.ask=QPushButton('Ask');self.ask.clicked.connect(self.ask_question);self.question.returnPressed.connect(self.ask_question)
        row.addWidget(self.question,1);row.addWidget(self.ask);layout.addWidget(self.questions)
        self.response=CopyableLabel();self.response.setWordWrap(True);layout.addWidget(self.response);self.response.hide()
        self.status=QLabel();self.status.setObjectName('hint');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(self.cancel_request);layout.addWidget(self.cancel);self.cancel.hide()
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.try_request)
        if service:service.phrase_completed.connect(self.completed)
        self.set_data(None,None)

    def set_data(self,value,payload,persist=None):
        self.cancel_request();self.refresh=None;self.payload=payload;self.persist=persist;self.value=value
        self.response.clear();self.response.hide();self.status.clear()
        while self.reading_layout.count():
            child=self.reading_layout.takeAt(0).widget()
            if child:child.deleteLater()
        def section(title,text):
            frame=QFrame();frame.setObjectName('learningFlatSection');box=QVBoxLayout(frame);box.setContentsMargins(0,10,0,12);box.setSpacing(4)
            heading=QLabel(title);heading.setObjectName('field');box.addWidget(heading)
            label=CopyableLabel(text);label.setWordWrap(True);box.addWidget(label);self.reading_layout.addWidget(frame)
        if value:
            from ml.card_explanation import learning_source
            if payload and value.get('source') and value['source']!=learning_source(payload):
                section('Analyzed excerpt of original speech',value['source'])
            if self.show_sentence_meaning:section('Sentence meaning',value.get('sentence_meaning',''))
            words=value.get('words',[])
            if words:
                frame=QFrame();frame.setObjectName('learningFlatSection');box=QVBoxLayout(frame);box.setContentsMargins(0,10,0,12)
                header=QHBoxLayout();heading=QLabel('Word by word');heading.setObjectName('field');header.addWidget(heading);header.addStretch()
                if self.service and payload:
                    from ui.icons import icon_button
                    self.refresh=icon_button('sparkles','Update saved word breakdown locally',self)
                    self.refresh.clicked.connect(lambda:(self.regenerate or self.request)());header.addWidget(self.refresh)
                box.addLayout(header)
                grid=QGridLayout();grid.setHorizontalSpacing(14);grid.setVerticalSpacing(10);grid.setColumnStretch(1,1);grid.setColumnMinimumWidth(0,90)
                for row,word in enumerate(words):
                    term=QWidget();left=QVBoxLayout(term);left.setContentsMargins(0,0,0,0);left.setSpacing(2);term.setMaximumWidth(115)
                    text=CopyableLabel(word.get('text',''));text.setObjectName('learningTerm');text.setWordWrap(True);left.addWidget(text)
                    if word.get('pronunciation'):
                        pronunciation=CopyableLabel(word['pronunciation']);pronunciation.setObjectName('hint');pronunciation.setWordWrap(True);left.addWidget(pronunciation)
                    detail=QWidget();right=QVBoxLayout(detail);right.setContentsMargins(0,0,0,0);right.setSpacing(2)
                    meaning=CopyableLabel(word.get('meaning',''));meaning.setWordWrap(True);right.addWidget(meaning)
                    reason=CopyableLabel(word.get('reason',''));reason.setObjectName('hint');reason.setWordWrap(True);right.addWidget(reason)
                    grid.addWidget(term,row,0,Qt.AlignmentFlag.AlignTop);grid.addWidget(detail,row,1)
                box.addLayout(grid);self.reading_layout.addWidget(frame)
            section('Why this meaning?',value.get('why',''))
        available=bool(self.service and payload and self.config)
        self.generate.setVisible(available and not (value and value.get('words')));self.questions.setVisible(available and bool(value))
        self.reading.setVisible(bool(value))
        if payload and not value and not available:self.status.setText('No saved word breakdown yet.')

    def ask_question(self):
        if self.question.text().strip():self.request(self.question.text().strip())

    def request(self,question=''):
        if self.disposed or self.pending or self.token or not self.payload or not self.service:return
        if self.events and self.events.property('local_translation_owned'):
            self.status.setText('Pause live translation to use its local model for this explanation.');return
        self.pending=dict(self.payload,**({'question':question} if question else ({'refresh':True} if self.value else {})))
        if self.refresh:self.refresh.setEnabled(False)
        if self.events:
            self.events.setProperty('learning_explanation_pending',int(self.events.property('learning_explanation_pending') or 0)+1);self.claimed=True
        self.question.setReadOnly(True);self.ask.setEnabled(False);self.generate.setEnabled(False);self.cancel.show()
        self.status.setText('Waiting for the current local model task…');self.timer.start();self.try_request()

    def try_request(self):
        if not self.pending or self.disposed:return
        if self.service.closing:self.cancel_request();return
        token='card-'+uuid4().hex
        try:accepted=self.service.explain(token,replace(self.config),self.pending)
        except ValueError as exc:self.cancel_request();self.status.setText(str(exc));return
        if accepted:
            self.token=token;self.pending=None;self.timer.stop();self.status.setText('Explaining original speech locally…')

    def completed(self,token,value):
        if token!=self.token or self.disposed:return
        self.token=None;self._release();self._idle()
        if 'error' in value:self.status.setText(str(value['error']));return
        if 'answer' in value:
            self.response.setText(self.question.text().strip()+'\n'+value['answer']);self.response.show();self.status.setText('Local AI · check unclear wording against the original speech.');return
        try:
            if self.persist:self.persist(value)
        except (ValueError,OSError) as exc:self.status.setText('Explanation was not saved: '+str(exc));return
        payload,persist=self.payload,self.persist
        self.set_data(value,payload,persist);self.status.setText(('Saved local AI explanation' if persist else 'Local AI draft')+' · check against the original speech.')

    def _release(self):
        if self.claimed and self.events:
            self.events.setProperty('learning_explanation_pending',max(0,int(self.events.property('learning_explanation_pending') or 0)-1))
        self.claimed=False

    def _idle(self):
        self.timer.stop();self.cancel.hide();self.question.setReadOnly(False);self.ask.setEnabled(True);self.generate.setEnabled(True)
        if self.refresh:self.refresh.setEnabled(True)

    def cancel_request(self):
        if self.token and self.service:self.service.cancel(self.token)
        self.token=None;self.pending=None;self._release();self._idle()

    def dispose(self):
        self.disposed=True;self.cancel_request()
        if self.service:
            try:self.service.phrase_completed.disconnect(self.completed)
            except (TypeError,RuntimeError):pass
