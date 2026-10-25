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
        self.last_model="";self.last_backend="";self.last_fallback=""

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

    def _fallback_translate(self,text,source,target,reason=""):
        value=self.fallback.translate(text,source,target)
        self.last_model="NLLB-200 600M";self.last_backend="CPU / int8";self.last_fallback=reason
        return value

    def translate(self,text,source,target):
        if self.config.translation_mode!='context':
            return self._fallback_translate(text,source,target)
        try:
            if self.failed:
                return self._fallback_translate(text,source,target,'Local AI unavailable')
            value=QwenTranslator(self.config,self.runtime).translate(text,source,target,
                cancelled=self.cancelled,context=list(self.context)[-self.config.analysis_context_sentences:] if self.config.analysis_context_sentences else [])
            from core.model_info import local_ai_name
            self.last_model=local_ai_name(self.config,self.runtime);self.last_backend=self.runtime.status;self.last_fallback=""
            return value
        except InterruptedError:
            raise
        except Exception as exc:
            if self.cancelled():
                raise InterruptedError('Translation cancelled') from exc
            self.failed=True
            self.events.status_changed.emit(f'Local translation failed; using NLLB until restart: {exc}')
            return self._fallback_translate(text,source,target,'Local AI translation failed')

    def remember(self,text,language):
        self.context.append({'text':text[:240],'language':language})

    def reset_context(self):
        self.context.clear()

    def reset_failure(self):
        self.failed=False
        self.last_model="";self.last_backend="";self.last_fallback=""
        self.fallback.reset_failure()

    def close(self):
        self.context.clear()
        self.fallback.close()
        if self.claimed:
            self.runtime.close()
        self.claimed=False
        self.failed=False
        self.last_model="";self.last_backend="";self.last_fallback=""
