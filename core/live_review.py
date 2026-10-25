"""One active and one pending local review; suggestions stay session-only."""
from dataclasses import replace
from core.revisions import revised_update
from core.model_info import refinement_enabled
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
        self.signature=self.current_signature()
        self.retry_after=0
        self.closed=False
        self.timer=QTimer(self);self.timer.setInterval(400);self.timer.timeout.connect(self.pump);self.timer.start()
        events.subtitle_ready.connect(self.enqueue)
        events.state_changed.connect(self.reset_if_changed)
        events.subtitles_toggled.connect(lambda enabled:self.reset())
        service.translation_completed.connect(self.completed)

    def current_signature(self):
        c=self.config
        return (c.translation_mode,c.refinement_enabled,c.refinement_destination,c.translation_enabled,c.source_language,c.target_language,c.audio_device_id,
                c.analysis_executable,c.analysis_gguf,c.analysis_context_sentences,c.analysis_context_tokens)

    def reset_if_changed(self,state):
        signature=self.current_signature()
        if self.signature!=signature:
            self.reset();self.signature=signature

    def _state(self,update,status,reason):
        current=next((item for item in self.history.items() if item.uid==update.uid),None)
        if not current or (current.native_text,current.target_text,current.revision_count)!=(update.native_text,update.target_text,update.revision_count):return
        from core.model_info import local_ai_name
        value=replace(current,review_status=status,review_reason=reason,
            refinement_model=local_ai_name(self.config,getattr(self.service,'runtime',None)) if status not in ('not_requested','skipped') else current.refinement_model,
            refinement_backend=str(getattr(getattr(self.service,'runtime',None),'status','')) if status=='reviewing' else current.refinement_backend)
        self.history.replace(value);self.events.review_state_changed.emit(value)

    def reset(self):
        if self.pending:self._state(self.pending,'skipped','Review stopped because the session or translation settings changed.')
        self.pending=None
        if self.active:
            self._state(self.active[1],'skipped','Review stopped because the session or translation settings changed.')
            self.service.cancel(self.active[0])
        self.active=None;self.retry_after=0

    def defer_for_explanation(self):
        if self.pending:self._state(self.pending,'skipped','Review yielded to your requested phrase explanation.')
        self.pending=None

    def close(self):
        self.closed=True;self.timer.stop();self.reset()

    def enqueue(self,update):
        if self.closed:return
        if not refinement_enabled(self.config) or not self.config.translation_enabled or not self.is_live():
            self._state(update,'not_requested','AI refinement is off or the translation session is inactive.');return
        if update.source_language not in ('zh','en','th','id') or update.source_language==update.target_language or len(update.native_text)>1000:
            reason='Original speech already matches the target language.' if update.source_language==update.target_language else 'The transcript language or length is outside automatic review limits.'
            self._state(update,'skipped',reason);return
        if self.pending:self._state(self.pending,'skipped','Newer speech replaced this pending review.')
        self.pending=update;self._state(update,'awaiting','Waiting for the shared local model to review the original speech.');self.pump()

    def pump(self):
        if self.events.property('phrase_explanation_open') or self.events.property('learning_explanation_pending'):
            return
        if self.closed or self.active or not self.pending or self.service.busy or monotonic()<self.retry_after:
            return
        if not refinement_enabled(self.config) or not self.is_live():
            self._state(self.pending,'skipped','Automatic review is no longer active.');self.pending=None;return
        update=self.pending
        items=self.history.items()
        index=next((i for i,item in enumerate(items) if item.uid==update.uid),None)
        if index is None:
            self.pending=None;return
        current=items[index]
        if (current.native_text,current.target_text,current.revision_count)!=(update.native_text,update.target_text,update.revision_count):
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
            self._state(update,'reviewing','Local AI is reviewing the original speech and nearby original dialogue.')

    def completed(self,token,value):
        if not self.active or self.active[0]!=token:
            return
        _,original,signature,group=self.active;self.active=None
        if signature!=self.current_signature() or not self.is_live():
            return
        current=next((item for item in self.history.items() if item.uid==original.uid),None)
        if not current or self.history.group_for(current.uid)!=group:
            return
        if (current.native_text,current.target_text,current.revision_count)!=(original.native_text,original.target_text,original.revision_count):
            return
        if 'error' in value:
            self.retry_after=monotonic()+30
            self._state(current,'failed','Local AI review could not complete. Fast translation is retained.')
            self.events.status_changed.emit('Automatic review unavailable; live subtitles continue. '+str(value['error']))
            return
        suggestion=value.get('translation','').strip()
        if not suggestion:
            self._state(current,'failed','Local AI returned no usable translation. Fast translation is retained.');return
        if suggestion==current.target_text:
            current=replace(current,refinement_model=value.get('model',current.refinement_model),refinement_backend=value.get('backend',current.refinement_backend))
            self.history.replace(current)
            self._state(current,'unchanged','Local AI reviewed this sentence and kept the wording.');return
        from core.model_info import local_ai_name
        refined=revised_update(current,refinement_model=value.get('model') or local_ai_name(self.config,getattr(self.service,'runtime',None)),refinement_backend=value.get('backend',''),target_text=suggestion,phonetics=phonetics_auto(suggestion),ai_refined=True,review_status='refined',review_reason='Local AI changed the translation. Reviewed does not mean verified correct.')
        self.history.replace(refined);self.events.subtitle_corrected.emit(refined)
