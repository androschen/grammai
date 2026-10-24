"""Serialized local-model lifecycle and analysis; bounded session cache."""
from collections import OrderedDict
from dataclasses import replace, asdict
import json
from time import monotonic
from PySide6.QtCore import QObject, QThread, Signal, QTimer
from ml.context_analysis import analyze, analysis_input
from ml.local_analysis import LocalAnalysisRuntime


class AnalysisWorker(QThread):
    result = Signal(object)
    progress = Signal(str)
    download_progress = Signal(str, int)

    def __init__(self, config, payload, runtime, operation='analyze', parent=None):
        super().__init__(parent)
        self.config,self.payload,self.runtime,self.operation=replace(config),payload,runtime,operation

    def run(self):
        started=monotonic()
        try:
            if self.operation=='install':
                from core.local_assets import install
                self.runtime.close()
                value=install(self.download_progress.emit,self.isInterruptionRequested)
            elif self.operation=='load':
                self.runtime.ensure_loaded(self.config,self.progress.emit,self.isInterruptionRequested)
                value={'status':self.runtime.status}
            elif self.operation=='unload':
                self.runtime.close()
                value={'status':'Unloaded'}
            elif self.operation=='explain':
                from ml.phrase_explanation import explain
                value=explain(self.config,self.payload,self.runtime,self.progress.emit,self.isInterruptionRequested)
            elif self.operation=='refine':
                from ml.qwen_translator import QwenTranslator
                translator=QwenTranslator(self.config,self.runtime)
                translator.ensure_loaded(self.progress.emit,self.isInterruptionRequested)
                value={'translation':translator.translate(self.payload['text'],self.payload['source'],
                    self.payload['target'],cancelled=self.isInterruptionRequested,context=self.payload.get('context'))}
            elif self.operation=='compare':
                from core.translation_compare import compare_translations
                value=compare_translations(self.config,self.payload,self.runtime,
                    self.progress.emit,self.isInterruptionRequested)
            else:
                value=analyze(self.config,self.payload,runtime=self.runtime,
                    progress=self.progress.emit,cancelled=self.isInterruptionRequested)
            value=dict(value,duration_ms=(monotonic()-started)*1000)
        except Exception as exc:
            value={'error':str(exc)}
        if self.isInterruptionRequested():
            if self.operation in ('load','compare','refine','explain') or (self.config.analysis_provider=='local' and self.operation=='analyze'):
                self.runtime.close()
        else:
            self.result.emit(value)


class AnalysisService(QObject):
    completed=Signal(str,object)
    comparison_completed=Signal(str,object)
    translation_completed=Signal(str,object)
    phrase_completed=Signal(str,object)
    idle=Signal()
    status_changed=Signal(str)
    progress_changed=Signal(str,int)
    management_finished=Signal(object)

    def __init__(self,parent=None,events=None,config=None):
        super().__init__(parent)
        self.worker=None
        self.cache=OrderedDict()
        self.token=None
        self.runtime=LocalAnalysisRuntime()
        self.events,self.config=events,config
        self.closing=False
        self.timer=QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self._idle_unload)
        self.timer.start()

    @property
    def busy(self):
        return self.worker is not None

    def _status(self,message):
        self.status_changed.emit(message)
        if self.events:
            self.events.setProperty('analysis_status',message)
            self.events.activity_changed.emit(message)

    def request(self,token,config,payload):
        if self.busy or self.closing or (self.events and (self.events.property('review_busy') or self.events.property('local_translation_owned'))):
            return False
        payload=analysis_input(payload)
        from pathlib import Path
        path=Path(config.analysis_gguf) if config.analysis_gguf else self.runtime.paths(config)[1]
        version=(str(path),path.stat().st_mtime_ns,path.stat().st_size) if path.is_file() else None
        settings={key:value for key,value in asdict(config).items() if key.startswith('analysis_')}
        key=json.dumps([3,settings,version,payload],sort_keys=True)
        self.token=token
        if key in self.cache:
            value=dict(self.cache[key],cached=True)
            QTimer.singleShot(0,lambda:self.completed.emit(token,value) if self.token==token else None)
            return True
        self._start(config,payload,'analyze',token,key)
        return True

    def manage(self,operation,config):
        if self.busy or self.closing or (self.events and (self.events.property('review_busy') or self.events.property('local_translation_owned'))) or operation not in ('install','load','unload'):
            return False
        self._start(config,{},operation)
        return True

    def explain(self,token,config,payload):
        if self.busy or self.closing or (self.events and any(self.events.property(p) for p in ('review_busy','local_translation_owned','benchmark_busy'))):
            return False
        from ml.phrase_explanation import explanation_input
        refresh=bool(payload.get('refresh'))
        payload=explanation_input(payload)
        from pathlib import Path
        path=Path(config.analysis_gguf) if config.analysis_gguf else self.runtime.paths(config)[1]
        version=(str(path),path.stat().st_mtime_ns,path.stat().st_size) if path.is_file() else None
        key=json.dumps(['phrase-v4',version,config.analysis_executable,config.analysis_context_tokens,
            config.analysis_explanation_language,config.analysis_reasoning,payload],sort_keys=True)
        self.token=token
        if key in self.cache and not refresh:
            value=dict(self.cache[key],cached=True)
            QTimer.singleShot(0,lambda:self.phrase_completed.emit(token,value) if self.token==token else None)
            return True
        self._start(replace(config,analysis_provider='local'),payload,'explain',token,key)
        return True

    def refine(self,token,config,payload):
        if self.busy or self.closing or (self.events and (self.events.property('review_busy') or self.events.property('local_translation_owned') or self.events.property('benchmark_busy'))):
            return False
        self.token=token
        self._start(replace(config,analysis_provider='local'),payload,'refine',token)
        return True

    def compare(self,token,config,payload):
        if self.busy or self.closing or (self.events and (self.events.property('review_busy') or self.events.property('local_translation_owned'))):
            return False
        allowed=getattr(self.events,'comparison_allowed',lambda:True)
        if not allowed():
            raise ValueError('Stop live subtitles and wait for current model tasks to finish before comparing.')
        from ml.qwen_translator import translation_body
        translation_body(payload.get('text',''),payload.get('source'),payload.get('target'))
        self.token=token
        if self.events:
            self.events.setProperty('comparison_busy',True)
        self._start(config,dict(payload),'compare',token)
        return True

    def _start(self,config,payload,operation,token=None,key=None):
        self.worker=AnalysisWorker(config,payload,self.runtime,operation,self)
        self.worker.result.connect(lambda value:self._result(token,key,operation,value))
        self.worker.progress.connect(self._status)
        self.worker.download_progress.connect(self.progress_changed)
        self.worker.finished.connect(self._finished)
        self._status({'install':'Downloading local AI assets','load':'Loading local GPU model',
            'unload':'Unloading local model','compare':'Local translator comparison','refine':'Reviewing completed translation locally','explain':'Explaining selected phrase locally',
            'analyze':'Local GPU analysis' if config.analysis_provider=='local' else 'Online analysis'}[operation])
        self.worker.start()

    def _result(self,token,key,operation,value):
        if operation=='explain':
            if self.token==token:
                if 'error' not in value:
                    self.cache[key]=dict(value)
                    while len(self.cache)>80:
                        self.cache.popitem(last=False)
                self.phrase_completed.emit(token,value)
        elif operation=='refine':
            if self.token==token:
                self.translation_completed.emit(token,value)
        elif operation=='compare':
            if self.token==token:
                self.comparison_completed.emit(token,value)
        elif operation!='analyze':
            self.management_finished.emit(dict(value,operation=operation))
        elif self.token==token:
            if 'error' not in value:
                self.cache[key]=dict(value)
                while len(self.cache)>80:
                    self.cache.popitem(last=False)
            self.completed.emit(token,value)
        if self.events and operation=='analyze' and 'error' not in value:
            self.events.setProperty('analysis_duration_ms',value.get('duration_ms'))
        self._status(value.get('error') or (self.runtime.status if self.runtime.loaded else 'Unloaded'))

    def cancel(self,token=None):
        if token is None or self.token==token:
            self.token=None
            if self.worker:
                self.worker.requestInterruption()
                if self.worker.operation in ('load','compare','refine','explain') or (self.worker.config.analysis_provider=='local' and self.worker.operation=='analyze'):
                    self.runtime.interrupt()

    def shutdown(self):
        self.closing=True
        self.timer.stop()
        self.cancel()
        if not self.busy and not (self.events and self.events.property('local_translation_owned')):
            if self.runtime.loaded and self.config is not None:
                self._start(self.config,{},'unload')
            else:
                self.runtime.close()

    def _finished(self):
        worker,self.worker=self.worker,None
        if worker.operation=='compare' and self.events:
            self.events.setProperty('comparison_busy',False)
        worker.deleteLater()
        if self.closing and not (self.events and self.events.property('local_translation_owned')):
            self.runtime.close()
        if worker.isInterruptionRequested():
            self._status('Cancelled; ' + self.runtime.status)
        self.idle.emit()

    def _idle_unload(self):
        minutes=self.config.analysis_idle_minutes if self.config else 0
        if minutes and not self.busy and self.runtime.loaded and monotonic()-self.runtime.last_used>=minutes*60:
            self.manage('unload',self.config)
