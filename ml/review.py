"""Manual audio recheck or text-only translation; serialized with live inference."""
from dataclasses import replace
from PySide6.QtCore import QThread,Signal
from ml.translator import NllbTranslator
from ml.phonetics import phonetics_auto
from core.revisions import revised_update
from time import perf_counter


class ReviewWorker(QThread):
    result=Signal(object)
    def __init__(self,config,request):
        super().__init__()
        self.config,self.request=config,request

    def run(self):
        translator=NllbTranslator(self.config)
        original=self.request['update']
        engine=None
        started=perf_counter()
        try:
            if self.isInterruptionRequested():
                return
            native=self.request['text'].strip()
            source,target=self.request['source'],self.request['target']
            audio=self.request.get('audio')
            if self.request.get('recheck') and audio is not None:
                from ml.whisper_engine import WhisperEngine
                from ml.transcript import trim_overlap
                config=replace(self.config,source_language=source,beam_size=max(5,self.config.beam_size))
                engine=WhisperEngine(config)
                engine.ensure_loaded()
                native,_=engine._transcribe(audio,task='transcribe')
                native=trim_overlap(original.overlap_previous_text,native,original.audio_overlap_seconds)
            if self.isInterruptionRequested():
                return
            if not native or len(native)>4000:
                raise ValueError('Enter between 1 and 4,000 characters.')
            translated=translator.translate(native,source,target)
            if not translated:
                raise RuntimeError('The translator returned no text.')
            update=revised_update(original,native_text=native,target_text=translated,
                phonetics=phonetics_auto(translated),native_phonetics=phonetics_auto(native),
                source_language=source,target_language=target,
                translation_status='same_language' if source==target else 'translated',
                translation_model='NLLB-200 600M',translation_backend='CPU / int8',translation_fallback='',refinement_model='',refinement_backend='',
                **(engine.speech_identity() if engine is not None else {}))
            if not self.isInterruptionRequested():
                self.result.emit({'update':update,'id':original.uid,
                    'requires_confirmation':bool(self.request.get('recheck')),
                    'mode':'audio' if audio is not None and self.request.get('recheck') else 'text',
                    'duration_ms':(perf_counter()-started)*1000})
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.result.emit({'error':str(exc),'id':original.uid})
        finally:
            if engine is not None:
                engine.close()
            translator.close()
