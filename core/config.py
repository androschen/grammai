"""Application settings for capture, inference, and UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.events import AppState


class TargetLanguage(str, Enum):
    ENGLISH = "en"
    CHINESE = "zh"
    THAI = "th"
    INDONESIAN = "id"


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
    TargetLanguage.INDONESIAN: "Indonesian (Bahasa Indonesia)",
}

SOURCE_LANGUAGE_LABELS: dict[str, str] = {
    "auto": "Auto-Detect",
    "auto_trio": "Auto: English / Chinese / Thai",
    "auto_four": "Auto: English / Chinese / Thai / Indonesian",
    "en": "English",
    "zh": "Chinese",
    "th": "Thai",
    "id": "Indonesian (Bahasa Indonesia)",
}

LANGUAGE_HUD: dict[str, str] = {
    "auto_trio": "Auto: EN / ZH / TH",
    "auto_four": "Auto: EN / ZH / TH / ID",
    "id": "Indonesian",
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
    speech_detection: bool = True
    speech_max_seconds: float = 6.0
    speech_silence_seconds: float = 0.5
    speech_overlap_seconds: float = 0.32
    speech_prompt: str = ""
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
    translation_enabled: bool = True
    translation_threads: int = 2
    translation_beam_size: int = 2
    backend: str = "cpu"
    vulkan_executable: str = ""
    vulkan_model: str = ""
    theme: str = "dark"
    show_overlay: bool = True
    show_pronunciation: bool = True
    subtitle_font_size: int = 28
    overlay_opacity: int = 140
    overlay_position: str = "bottom"
    overlay_hud_opacity: int = 75
    overlay_show_hud: bool = True
    overlay_show_original: bool = True
    overlay_text_outline: bool = True
    overlay_text_shadow: bool = True
    overlay_padding: int = 18
    overlay_corner_radius: int = 16
    overlay_max_width: int = 72
    analysis_enabled: bool = False
    analysis_endpoint: str = ""
    analysis_model: str = ""
    analysis_key_env: str = "GRAMMAI_ANALYSIS_API_KEY"
    analysis_provider: str = "local"
    analysis_executable: str = ""
    analysis_gguf: str = ""
    analysis_context_tokens: int = 4096
    analysis_context_sentences: int = 3
    analysis_idle_minutes: int = 5
    analysis_speech_style: str = "everyday"
    analysis_translation_style: str = "preserve_tone"
    analysis_explanation_language: str = "id"
    analysis_explain_slang: bool = True
    analysis_reasoning: bool = True
    analysis_glossary: str = ""
    analysis_examples: str = "[]"

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
            translation_enabled=self.translation_enabled,
            inference_key=(self.backend, self.model_size, self.beam_size,
                           self.cpu_threads, self.translation_threads, self.translation_beam_size,
                           self.vulkan_executable, self.vulkan_model, self.translation_enabled,
                           self.speech_detection,self.speech_max_seconds,self.speech_silence_seconds,
                           self.speech_overlap_seconds,self.speech_prompt),
        )

    @property
    def buffer_samples(self) -> int:
        return int(self.sample_rate * self.buffer_seconds)

    @property
    def chunk_samples(self) -> int:
        return int(self.sample_rate * self.capture_chunk_seconds)
