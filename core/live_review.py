"""One active and one pending local review; suggestions stay session-only."""
from core.revisions import revised_update
from ml.phonetics import phonetics_auto
from time import monotonic
from uuid import uuid4
from PySide6.QtCore import QObject,QTimer


class LiveReview(QObject):
    def __init__(self,config,events,service,history,is_live,parent=None):
        super().__init__(parent)
        self.config,self.events,self.service,self.history,self.is_live=config,events,service,history,is_live
        self.pending=None
        self.active=None
        self.signature=None
        self.retry_after=0
        self.closed=False
        self.timer=QTimer(self);self.timer.setInterval(400);self.timer.timeout.connect(self.pump);self.timer.start()
        events.subtitle_ready.connect(self.enqueue)
        events.state_changed.connect(self.reset_if_changed)
        events.subtitles_toggled.connect(lambda enabled:self.reset())
        service.translation_completed.connect(self.completed)

    def current_signature(self):
        c=self.config
        return (c.translation_mode,c.translation_enabled,c.source_language,c.target_language,c.audio_device_id,
                c.analysis_executable,c.analysis_gguf,c.analysis_context_sentences,c.analysis_context_tokens)

    def reset_if_changed(self,state):
        signature=self.current_signature()
        if self.signature!=signature:
            self.reset();self.signature=signature

    def reset(self):
        self.pending=None
        if self.active:
            self.service.cancel(self.active[0])
        self.active=None
        self.retry_after=0

    def defer_for_explanation(self):
        # Finish the one in-flight review so its loaded model can be reused.
        # The open-dialog property stops subsequent reviews from starting.
        self.pending=None

    def close(self):
        self.closed=True;self.timer.stop();self.reset()

    def enqueue(self,update):
        if self.closed or self.config.translation_mode!='review' or not self.config.translation_enabled or not self.is_live():
            return
        if update.source_language not in ('zh','en','th','id') or update.source_language==update.target_language or len(update.native_text)>1000:
            return
        # New speech replaces old pending work; in-flight work is bounded too.
        self.pending=update
        self.pump()

    def pump(self):
        if self.events.property('phrase_explanation_open'):
            return
        if self.closed or self.active or not self.pending or self.service.busy or monotonic()<self.retry_after:
            return
        if self.config.translation_mode!='review' or not self.is_live():
            self.pending=None;return
        update=self.pending
        items=self.history.items()
        index=next((i for i,item in enumerate(items) if item.uid==update.uid),None)
        if index is None:
            self.pending=None;return
        group=self.history.group_for(update.uid)
        limit=min(3,self.config.analysis_context_sentences)
        context=[{'text':item.native_text[:240],'language':item.source_language}
            for item in items[max(0,index-limit):index] if self.history.group_for(item.uid)==group]
        token='live-review-'+uuid4().hex
        payload={'text':update.native_text,'source':update.source_language,'target':update.target_language,'context':context}
        if self.service.refine(token,self.config,payload):
            self.active=(token,update,self.current_signature(),group)
            self.pending=None

    def completed(self,token,value):
        if not self.active or self.active[0]!=token:
            return
        _,original,signature,group=self.active;self.active=None
        if signature!=self.current_signature() or not self.is_live():
            return
        if 'error' in value:
            self.retry_after=monotonic()+30
            self.events.status_changed.emit('Automatic review unavailable; live subtitles continue. '+value['error'])
            return
        current=next((item for item in self.history.items() if item.uid==original.uid),None)
        if not current or self.history.group_for(current.uid)!=group:
            return
        if (current.native_text,current.target_text,current.revision_count)!=(original.native_text,original.target_text,original.revision_count):
            return
        suggestion=value.get('translation','').strip()
        if suggestion and suggestion!=current.target_text:
            self.events.subtitle_corrected.emit(revised_update(current,target_text=suggestion,phonetics=phonetics_auto(suggestion),ai_refined=True))
