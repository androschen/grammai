"""Application settings for capture, inference, and UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.events import AppState


class TargetLanguage(str, Enum):
    ENGLISH = "en"
    CHINESE = "zh"
    THAI = "th"


class QualityMode(str, Enum):
    FAST = "fast"
    ACCURATE = "accurate"
    BALANCED = "balanced"


QUALITY_LABELS: dict[QualityMode, str] = {
    QualityMode.FAST: "Low resource",
    QualityMode.BALANCED: "Balanced",
    QualityMode.ACCURATE: "Best quality",
}


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
    cpu_threads: int = 4
    beam_size: int = 2
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
    quality_mode: QualityMode = QualityMode.BALANCED
    translation_threads: int = 2
    translation_beam_size: int = 2
    backend: str = "cpu"
    vulkan_executable: str = ""
    vulkan_model: str = ""
    theme: str = "dark"
    show_overlay: bool = True
    show_pronunciation: bool = True
    subtitle_font_size: int = 28
    overlay_opacity: int = 170
    overlay_position: str = "bottom"

    def apply_quality(self) -> None:
        if self.quality_mode is QualityMode.ACCURATE:
            self.model_size = "small"
            self.beam_size = 5
            self.translation_beam_size = 4
        elif self.quality_mode is QualityMode.BALANCED:
            self.model_size = "base"
            self.beam_size = 2
            self.translation_beam_size = 2
        else:
            self.model_size = "base"
            self.beam_size = 1
            self.translation_beam_size = 1

    def snapshot(self) -> AppState:
        return AppState(
            device_id=self.audio_device_id,
            device_name=self.audio_device_name,
            device_kind=self.audio_device_kind,
            source_language=self.source_language,
            target_language=self.target_language.value,
            noise_threshold=self.noise_threshold,
            quality_mode=self.quality_mode.value,
            inference_key=(self.backend, self.model_size, self.beam_size,
                           self.cpu_threads, self.translation_threads, self.translation_beam_size,
                           self.vulkan_executable, self.vulkan_model),
        )

    @property
    def buffer_samples(self) -> int:
        return int(self.sample_rate * self.buffer_seconds)

    @property
    def chunk_samples(self) -> int:
        return int(self.sample_rate * self.capture_chunk_seconds)
