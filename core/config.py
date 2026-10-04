"""Application settings for capture, inference, and UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.events import AppState


class TargetLanguage(str, Enum):
    ENGLISH = "en"
    CHINESE = "zh"
    THAI = "th"


LANGUAGE_LABELS: dict[TargetLanguage, str] = {
    TargetLanguage.ENGLISH: "English",
    TargetLanguage.CHINESE: "Chinese",
    TargetLanguage.THAI: "Thai",
}

SOURCE_LANGUAGE_LABELS: dict[str, str] = {
    "auto": "Auto-Detect",
    "en": "English",
    "zh": "Chinese",
    "th": "Thai",
}

LANGUAGE_HUD: dict[str, str] = {
    "auto": "🌐 Auto-Detect",
    "en": "🇬🇧 English",
    "zh": "🇨🇳 Chinese",
    "th": "🇹🇭 Thai",
}


@dataclass
class AppConfig:
    """Tuned for Ryzen 7 5700X + Radeon RX 7700 XT on Windows.

    faster-whisper runs on CPU with int8: CTranslate2 has no stable
    ROCm/DirectML path for this AMD GPU on Windows.
    """

    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 8
    beam_size: int = 1
    vad_filter: bool = True
    sample_rate: int = 16000
    buffer_seconds: float = 3.5
    capture_chunk_seconds: float = 0.04  # ~25 Hz for the volume HUD
    target_language: TargetLanguage = TargetLanguage.CHINESE
    source_language: str = "auto"
    audio_device_id: str = ""
    audio_device_name: str = "Desktop Audio"
    audio_device_kind: str = "loopback"
    noise_threshold: float = 0.12
    rms_full_scale: float = 0.12

    def snapshot(self) -> AppState:
        return AppState(
            device_id=self.audio_device_id,
            device_name=self.audio_device_name,
            device_kind=self.audio_device_kind,
            source_language=self.source_language,
            target_language=self.target_language.value,
            noise_threshold=self.noise_threshold,
        )

    @property
    def buffer_samples(self) -> int:
        return int(self.sample_rate * self.buffer_seconds)

    @property
    def chunk_samples(self) -> int:
        return int(self.sample_rate * self.capture_chunk_seconds)
