"""Side-by-side local translation tests, with explicit human meaning ratings."""
from uuid import uuid4
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QComboBox,QPlainTextEdit,QFrame,QScrollArea,QWidget)
from core.config import LANGUAGE_LABELS
from core.translation_compare import SAMPLES
from ui.theme import style_for


class TranslationComparisonDialog(QDialog):
    def __init__(self,config,events,parent=None):
        super().__init__(parent)
        self.config,self.events=config,events
        self.service=getattr(events,'analysis_service',None)
        self.token=None
        self.entries=[]
        self.setWindowTitle('Compare local translators')
        self.setStyleSheet(style_for(config.theme));self.resize(900,760)
        outer=QVBoxLayout(self)
        title=QLabel('Which translation keeps the meaning?');title.setObjectName('title');title.setWordWrap(True)
        outer.addWidget(title)
        note=QLabel('NLLB CPU vs your existing local Qwen GPU model. Both receive the same source sentence. No history, glossary, saved examples or earlier translations are used. This comparison does not change your selected live translation mode.')
        note.setWordWrap(True);note.setObjectName('hint');outer.addWidget(note)
        body=QWidget();layout=QVBoxLayout(body)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body)
        scroll.setFrameShape(QFrame.Shape.NoFrame);outer.addWidget(scroll,1)
        self.samples=QComboBox()
        for label,*_ in SAMPLES:self.samples.addItem(label)
        layout.addWidget(self.samples)
        self.source,self.target=QComboBox(),QComboBox()
        for code,label in LANGUAGE_LABELS.items():
            self.source.addItem(label,code.value);self.target.addItem(label,code.value)
        form=QFormLayout();form.addRow('Original language',self.source);form.addRow('Translate into',self.target)
        layout.addLayout(form)
        self.text=QPlainTextEdit();self.text.setMaximumHeight(100)
        self.text.setAccessibleName('Original sentence shared by both translators')
        layout.addWidget(self.text)
        row=QHBoxLayout()
        self.stop=QPushButton('Stop live subtitles');self.stop.clicked.connect(lambda:events.subtitles_toggled.emit(False))
        self.run=QPushButton('Compare translations');self.run.clicked.connect(self._run)
        self.cancel=QPushButton('Cancel');self.cancel.setEnabled(False);self.cancel.clicked.connect(self._cancel)
        for button in (self.stop,self.run,self.cancel):row.addWidget(button)
        layout.addLayout(row)
        self.feedback=QLabel('Review meaning, not just fluency. Times below do not measure speech recognition or end-to-end subtitle delay.')
        self.feedback.setWordWrap(True);self.feedback.setObjectName('hint');layout.addWidget(self.feedback)
        self.recent=QComboBox();self.recent.setPlaceholderText('Recent comparisons (this window only)')
        self.recent.currentIndexChanged.connect(self._render);layout.addWidget(self.recent)
        results=QHBoxLayout();self.cards={}
        for engine,label in (('nllb','NLLB · CPU baseline'),('qwen','Qwen · local AI translator')):
            frame=QFrame();frame.setObjectName('sentenceTranslation' if engine=='qwen' else 'sentenceSource')
            box=QVBoxLayout(frame);box.setContentsMargins(16,16,16,16)
            heading=QLabel(label);heading.setObjectName('field');heading.setWordWrap(True);box.addWidget(heading)
            output=QLabel('Run a comparison to see the translation.');output.setWordWrap(True)
            output.setTextFormat(Qt.TextFormat.PlainText)
            output.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            output.setStyleSheet('font-size:18px;');box.addWidget(output,1)
            timing=QLabel();timing.setObjectName('hint');timing.setWordWrap(True);box.addWidget(timing)
            rating=QComboBox()
            rating.addItems(['Meaning: not rated','Correct meaning','Partly correct','Wrong meaning'])
            rating.setEnabled(False);rating.setAccessibleName(label+' meaning rating')
            rating.currentIndexChanged.connect(lambda index,e=engine:self._rate(e,index))
            box.addWidget(rating);results.addWidget(frame,1)
            self.cards[engine]=(output,timing,rating)
        layout.addLayout(results)
        warning=QLabel('Small starter examples are diagnostics, not an accuracy percentage. Ratings and custom text stay in RAM and disappear when this window closes. Comparison never downloads models or applies changes to live subtitles.')
        warning.setWordWrap(True);warning.setObjectName('hint');layout.addWidget(warning)
        close=QPushButton('Close');close.clicked.connect(self.reject);outer.addWidget(close)
        self.samples.currentIndexChanged.connect(self._sample)
        self._sample(0)
        if self.service is not None:
            self.service.comparison_completed.connect(self._finished)
            self.service.status_changed.connect(self._progress)
            self.service.idle.connect(self._idle)
        else:
            self.run.setEnabled(False);self.feedback.setText('Open this tool from the main GrammAI application.')

    def _sample(self,index):
        _,source,target,text=SAMPLES[index]
        self.source.setCurrentIndex(self.source.findData(source));self.target.setCurrentIndex(self.target.findData(target))
        self.text.setPlainText(text)

    def _controls(self,enabled):
        for widget in (self.samples,self.source,self.target,self.text,self.recent):widget.setEnabled(enabled)
        self.run.setEnabled(enabled and self.service is not None)
        self.cancel.setEnabled(not enabled)

    def _run(self):
        if self.token or self.service is None:return
        payload={'text':self.text.toPlainText().strip(),'source':self.source.currentData(),'target':self.target.currentData()}
        token=uuid4().hex
        try:
            accepted=self.service.compare(token,self.config,payload)
        except ValueError as exc:
            self.feedback.setText(str(exc));return
        if not accepted:
            self.feedback.setText('Another model task is finishing. Wait or cancel that task, then try again.');return
        self.token=token;self.payload=payload;self._controls(False)
        self.feedback.setText('Comparing locally. Model setup and translation are timed separately; no text is sent online.')

    def _finished(self,token,value):
        if token!=self.token:return
        self.token=None;self.cancel.setEnabled(False)
        if 'error' in value:
            self.feedback.setText(value['error']);return
        self.entries.append({'result':value,'ratings':{'nllb':0,'qwen':0}})
        self.recent.blockSignals(True)
        if len(self.entries)>40:
            self.entries.pop(0);self.recent.removeItem(0)
        self.recent.addItem(value['text'][:65]);self.recent.setCurrentIndex(len(self.entries)-1)
        self.recent.blockSignals(False);self._render(len(self.entries)-1)
        self.feedback.setText('Compare the outputs with your intended meaning. No automatic winner or live-model change has been selected.')

    def _render(self,index):
        if not 0<=index<len(self.entries):return
        entry=self.entries[index];data=entry['result']
        self.source.setCurrentIndex(self.source.findData(data['source']))
        self.target.setCurrentIndex(self.target.findData(data['target']))
        self.text.setPlainText(data['text'])
        for engine,(output,timing,rating) in self.cards.items():
            item=next((r for r in data['results'] if r['engine']==engine),{})
            output.setText(item.get('text') or item.get('error') or 'No result')
            timing.setText((f"Translate {item['translation_ms']/1000:.2f}s · setup/reuse {item.get('loading_ms',0)/1000:.2f}s"+
                ('\n'+item['model'] if item.get('model') else '')) if 'translation_ms' in item else 'Unavailable for this comparison')
            rating.blockSignals(True);rating.setCurrentIndex(entry['ratings'][engine]);rating.blockSignals(False)
            rating.setEnabled('text' in item)

    def _rate(self,engine,index):
        selected=self.recent.currentIndex()
        if 0<=selected<len(self.entries):self.entries[selected]['ratings'][engine]=index

    def _progress(self,message):
        if self.token:self.feedback.setText(message)

    def _cancel(self):
        if self.token and self.service:
            self.service.cancel(self.token);self.token=None
            self.cancel.setEnabled(False);self.feedback.setText('Cancelling; waiting for the local worker to stop…')

    def _idle(self):
        self._controls(True)

    def done(self,result):
        self._cancel()
        if self.service:
            for signal,slot in ((self.service.comparison_completed,self._finished),
                (self.service.status_changed,self._progress),(self.service.idle,self._idle)):
                try:signal.disconnect(slot)
                except (TypeError,RuntimeError):pass
        self.entries.clear()
        super().done(result)
