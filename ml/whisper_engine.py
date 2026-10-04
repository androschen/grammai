"""Local faster-whisper inference on CPU (int8)."""

from __future__ import annotations

import numpy as np

from core.config import AppConfig, TargetLanguage
from core.events import SubtitleUpdate
from ml.phonetics import phonetics_auto


def _looks_like(language: str | None, prefix: str) -> bool:
    return bool(language) and language.lower().startswith(prefix)


class WhisperEngine:
    """Loads once, then transcribes/translates float32 mono 16 kHz buffers."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self._config.model_size,
            device=self._config.device,
            compute_type=self._config.compute_type,
            cpu_threads=self._config.cpu_threads,
        )

    def process(self, audio: np.ndarray, target: TargetLanguage) -> SubtitleUpdate | None:
        native, source_lang = self._transcribe(audio, task="transcribe")
        if not native:
            return None

        target_text, _ = self._target_line(audio, native, source_lang, target)
        return SubtitleUpdate(
            phonetics=phonetics_auto(target_text),
            target_text=target_text,
            native_text=native,
            native_phonetics=phonetics_auto(native),
        )

    def _transcribe(self, audio: np.ndarray, task: str) -> tuple[str, str | None]:
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

    def _target_line(
        self,
        audio: np.ndarray,
        native: str,
        source_lang: str | None,
        target: TargetLanguage,
    ) -> tuple[str, str]:
        if target is TargetLanguage.ENGLISH:
            if _looks_like(source_lang, "en"):
                return native, ""
            translated, _ = self._transcribe(audio, task="translate")
            return translated or native, ""
        return native, ""
