"""Load and test one candidate only after the old inference worker releases it."""
from dataclasses import replace
from PySide6.QtCore import QThread,Signal

class SpeechSwitchWorker(QThread):
    def __init__(self,engine,config):
        super().__init__();self.engine=engine;self.config=replace(config);self.error=None;self.backend='';self.note=''
    def run(self):
        try:
            self.engine.configure(self.config);self.engine.ensure_loaded(cancelled=self.isInterruptionRequested)
            if self.isInterruptionRequested():raise InterruptedError('Speech switch cancelled')
            from core.benchmark import fixture
            audio,_=fixture()
            self.engine.configure(replace(self.config,source_language='en'))
            text,_=self.engine._transcribe(audio,'transcribe')
            if not text.strip():raise RuntimeError('The speech model produced no transcript for the setup sample.')
            if self.isInterruptionRequested():raise InterruptedError('Speech switch cancelled')
            self.engine.configure(self.config)
            self.backend=getattr(self.engine,'active_backend','');self.note=getattr(self.engine,'processing_note','')
        except Exception as exc:
            self.error=str(exc);self.engine.close()
    def cancel(self):
        self.requestInterruption()
        speech=getattr(self.engine,'_vulkan',None);process=getattr(speech,'process',None)
        if process is not None and process.poll() is None:
            try:process.terminate()
            except OSError:pass
