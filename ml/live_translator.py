"""Session-scoped Qwen translation with original-only context and NLLB fallback."""
from collections import deque
from ml.qwen_translator import QwenTranslator


class LiveTranslator:
    def __init__(self,config,fallback,runtime,events):
        self.config,self.fallback,self.runtime,self.events=config,fallback,runtime,events
        self.cancelled=lambda:False
        self.context=deque(maxlen=3)
        self.claimed=False
        self.failed=False

    def configure(self,config):
        self.config=config
        self.fallback.configure(config)

    def ensure_loaded(self):
        if self.config.translation_mode!='context':
            return self.fallback.ensure_loaded()
        self.claimed=True
        try:
            QwenTranslator(self.config,self.runtime).ensure_loaded(self.events.status_changed.emit,self.cancelled)
        except InterruptedError:
            raise
        except Exception as exc:
            if self.cancelled():
                raise InterruptedError('Translation cancelled') from exc
            self.failed=True
            self.events.status_changed.emit(f'Local translator unavailable; using NLLB: {exc}')
            self.fallback.ensure_loaded()

    def translate(self,text,source,target):
        if self.config.translation_mode!='context':
            return self.fallback.translate(text,source,target)
        try:
            if self.failed:
                return self.fallback.translate(text,source,target)
            return QwenTranslator(self.config,self.runtime).translate(text,source,target,
                cancelled=self.cancelled,context=list(self.context)[-self.config.analysis_context_sentences:] if self.config.analysis_context_sentences else [])
        except InterruptedError:
            raise
        except Exception as exc:
            if self.cancelled():
                raise InterruptedError('Translation cancelled') from exc
            self.failed=True
            self.events.status_changed.emit(f'Local translation failed; using NLLB until restart: {exc}')
            return self.fallback.translate(text,source,target)

    def remember(self,text,language):
        self.context.append({'text':text[:240],'language':language})

    def reset_context(self):
        self.context.clear()

    def reset_failure(self):
        self.failed=False
        self.fallback.reset_failure()

    def close(self):
        self.context.clear()
        self.fallback.close()
        if self.claimed:
            self.runtime.close()
        self.claimed=False
        self.failed=False
