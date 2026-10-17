"""Qt event bus and subtitle payload shared across UI, audio, and ML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class SubtitleUpdate:
    phonetics: str
    target_text: str
    native_text: str
    native_phonetics: str = ""
    translation_status: str = "translated"
    created_at: datetime = field(default_factory=datetime.now)
    uid: str = field(default_factory=lambda:uuid4().hex)
    audio_id: str = ""
    source_language: str = "unknown"
    target_language: str = "en"
    original_native_text: str | None = None
    original_target_text: str | None = None
    revision_count: int = 0
    audio_overlap_seconds: float = 0.
    overlap_previous_text: str = ""


@dataclass(frozen=True)
class AppState:
    """Snapshot of HUD + backend routing. Emitted on device/language/threshold changes."""

    device_id: str
    device_name: str
    device_kind: str  # "loopback" | "mic"
    source_language: str  # "auto" or language code
    target_language: str
    noise_threshold: float  # 0.0â€“1.0, same scale as audio_level_changed
    quality_mode: str = "balanced"
    inference_key: tuple = ()
    translation_enabled: bool = True


class EventBus(QObject):
    """Queued signals so capture/inference threads never touch widgets."""

    subtitle_ready = Signal(object)  # SubtitleUpdate
    status_changed = Signal(str)
    pipeline_error = Signal(str)
    subtitles_toggled = Signal(bool)
    target_language_changed = Signal(str)
    quit_requested = Signal()
    retry_requested = Signal()
    overlay_toggled = Signal(bool)
    overlay_appearance_preview = Signal(object)  # AppConfig draft or None to restore applied preferences
    metrics_changed = Signal(object)
    activity_changed = Signal(str)
    audio_dropped = Signal(int)
    benchmark_requested = Signal(object)
    benchmark_progress = Signal(str)
    benchmark_finished = Signal(object)
    benchmark_busy = Signal(bool)
    learning_requested = Signal(object)
    review_requested = Signal(object)
    review_finished = Signal(object)
    review_busy = Signal(bool)
    subtitle_corrected = Signal(object)
    replay_requested = Signal(str, float)
    playback_active = Signal(bool)
    replay_clear_requested = Signal()

    # Fast path: RMS/peak level 0.0â€“1.0, ~20â€“30 Hz from the capture thread.
    audio_level_changed = Signal(float)
    # Device, language routing, and noise threshold for HUD + backend.
    state_changed = Signal(object)  # AppState
