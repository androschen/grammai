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

    def reset_failures(self) -> None:
        if self._translator is not None:
            self._translator.reset_failure()

    def ensure_translator(self) -> None:
        if self._translator is None:
            return
        self._translator.ensure_loaded()

    def process(self, audio: np.ndarray, target: TargetLanguage) -> SubtitleUpdate | None:
        started = perf_counter()
        native, source_lang = self._transcribe(audio, task="transcribe")
        stt_end = perf_counter()
        self.last_timings = {"stt_ms": (stt_end - started) * 1000,
                             "mt_ms": 0., "total_ms": (stt_end - started) * 1000,
                             "audio_seconds": len(audio) / self._config.sample_rate}
        if not native:
            return None

        source = whisper_to_short_code(source_lang, native)
        target_code = target.value
        target_text = native
        if source != target_code:
            target_text = self._translate(native, source, target, audio)

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
            except Exception:
                pass
        if target is TargetLanguage.ENGLISH:
            fallback, _ = self._transcribe(audio, task="translate")
            return fallback
        return ""

    def _transcribe(self, audio: np.ndarray, task: str) -> tuple[str, str | None]:
        if self._vulkan is not None:
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
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        language = getattr(info, "language", None)
        return text, language

    def _source_hint(self) -> str | None:
        code = self._config.source_language
        if not code or code == "auto":
            return None
        return code
