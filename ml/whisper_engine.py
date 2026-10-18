"""Local faster-whisper inference on CPU (int8)."""

from __future__ import annotations

import numpy as np
from time import perf_counter

from core.config import AppConfig, TargetLanguage
from core.events import SubtitleUpdate
from ml.phonetics import phonetics_auto
from ml.translator import NllbTranslator, whisper_to_short_code


class WhisperEngine:
    """Loads once, then transcribes and routes text through NLLB when needed."""

    def __init__(
        self,
        config: AppConfig,
        translator: NllbTranslator | None = None,
    ) -> None:
        self._config = config
        self._translator = translator
        self._model = None
        self._loaded_size = None
        self._vulkan = None
        self.last_timings = {}
        self.active_backend = "Not loaded"
        self.activity_callback = None
        self._overlap_seconds=0.
        self._previous_native=''
        self._previous_language=None

    def set_audio_overlap(self,seconds):
        self._overlap_seconds=max(0.,float(seconds))

    def configure(self, config: AppConfig) -> None:
        self._config = config
        if self._translator is not None:
            self._translator.configure(config)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None or self._vulkan is not None

    def ensure_loaded(self) -> None:
        key = (self._config.backend, self._config.model_size, self._config.cpu_threads,
               self._config.vulkan_executable, self._config.vulkan_model, self._config.beam_size)
        if self.is_loaded and self._loaded_size == key:
            return
        self.close()
        if self._config.backend == "vulkan":
            from ml.vulkan_engine import VulkanWhisper
            self._vulkan = VulkanWhisper(self._config)
            try:
                self._vulkan.start()
            except Exception:
                self.close()
                raise
            self.active_backend = "Radeon / Vulkan"
            self._loaded_size = key
            return
        size = self._config.model_size
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            size,
            device=self._config.device,
            compute_type=self._config.compute_type,
            cpu_threads=self._config.cpu_threads,
        )
        self._loaded_size = key
        self.active_backend = "CPU / int8"

    def close(self):
        if self._translator is not None:
            self._translator.close()
        if self._vulkan is not None:
            self._vulkan.close()
            self._vulkan = None
        self._model = None
        self._loaded_size = None
        self.active_backend = "Not loaded"
        self._previous_native=''
        self._previous_language=None
        self._overlap_seconds=0.

    def reset_failures(self) -> None:
        if self._translator is not None:
            self._translator.reset_failure()

    def ensure_translator(self) -> None:
        if not self._config.translation_enabled or self._translator is None:
            return
        if self.activity_callback:
            self.activity_callback('Translation model loading')
        self._translator.ensure_loaded()

    def process(self, audio: np.ndarray, target: TargetLanguage) -> SubtitleUpdate | None:
        started = perf_counter()
        if self.activity_callback:
            self.activity_callback('Transcription')
        native, source_lang = self._transcribe(audio, task="transcribe")
        from ml.transcript import trim_overlap
        raw_native=native
        overlap_seconds=self._overlap_seconds
        previous_native=self._previous_native if self._previous_language==source_lang else ''
        if self._previous_language==source_lang:
            native=trim_overlap(self._previous_native,native,self._overlap_seconds)
        self._previous_native,self._previous_language=raw_native,source_lang
        self._overlap_seconds=0.
        stt_end = perf_counter()
        self.last_timings = {"stt_ms": (stt_end - started) * 1000,
                             "mt_ms": 0., "total_ms": (stt_end - started) * 1000,
                             "audio_seconds": len(audio) / self._config.sample_rate}
        if not native:
            return None

        source = whisper_to_short_code(source_lang, native)
        if not self._config.translation_enabled:
            return SubtitleUpdate(phonetics=phonetics_auto(native),target_text=native,
                native_text=native,translation_status='transcribed',
                audio_overlap_seconds=overlap_seconds,overlap_previous_text=previous_native,
                source_language=source,target_language=source)
        target_code = target.value
        target_text = native
        if source != target_code:
            if self.activity_callback:
                self.activity_callback('Translation')
            target_text = self._translate(native, source, target, audio)

        remember=getattr(self._translator,'remember',None)
        if remember:
            remember(native,source)
        self.last_timings.update(mt_ms=(perf_counter() - stt_end) * 1000, total_ms=(perf_counter() - started) * 1000)
        status = "same_language" if source == target_code else "translated"
        if not target_text:
            status = "unavailable"
        return SubtitleUpdate(
            phonetics=phonetics_auto(target_text),
            target_text=target_text,
            native_text=native,
            native_phonetics=phonetics_auto(native),
            translation_status=status,
            source_language=source,
            target_language=target_code,
            audio_overlap_seconds=overlap_seconds,overlap_previous_text=previous_native,
        )

    def _translate(
        self,
        native: str,
        source: str,
        target: TargetLanguage,
        audio: np.ndarray,
    ) -> str:
        if self._translator is not None:
            try:
                translated = self._translator.translate(native, source, target.value)
                if translated:
                    return translated
            except InterruptedError:
                raise
            except Exception:
                pass
        if target is TargetLanguage.ENGLISH:
            fallback, _ = self._transcribe(audio, task="translate")
            return fallback
        return ""

    def _transcribe(self, audio: np.ndarray, task: str) -> tuple[str, str | None]:
        allowed = {"auto_trio": ("en", "zh", "th"),
                   "auto_four": ("en", "zh", "th", "id")}.get(self._config.source_language)
        if self._vulkan is not None:
            if allowed:
                return self._vulkan.transcribe(audio, None, task == "translate", allowed_languages=allowed)
            return self._vulkan.transcribe(audio, self._source_hint(), task == "translate")
        if self._model is None:
            raise RuntimeError("Whisper model is not loaded.")
        segments, info = self._model.transcribe(
            audio,
            language=self._source_hint(),
            task=task,
            beam_size=self._config.beam_size,
            vad_filter=self._config.vad_filter,
            without_timestamps=True,
            initial_prompt=self._config.speech_prompt or None,
        )
        # Inspect detection before consuming the lazy decoder. Normal trio speech
        # uses one transcription; only an outside-language detection needs a retry.
        if allowed and info.language not in allowed:
            ranked = [(code, score) for code, score in (info.all_language_probs or []) if code in allowed]
            if not ranked:
                raise RuntimeError("Could not detect a language in the selected auto group. Choose a spoken language manually.")
            language = max(ranked, key=lambda item: item[1])[0]
            segments, info = self._model.transcribe(
                audio, language=language, task=task, beam_size=self._config.beam_size,
                vad_filter=self._config.vad_filter, without_timestamps=True,
                initial_prompt=self._config.speech_prompt or None,
            )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        language = getattr(info, "language", None)
        return text, language

    def _source_hint(self) -> str | None:
        code = self._config.source_language
        if not code or code in ("auto", "auto_trio", "auto_four"):
            return None
        return code
