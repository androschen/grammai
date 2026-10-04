"""Qt event bus and subtitle payload shared across UI, audio, and ML."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class SubtitleUpdate:
    phonetics: str
    target_text: str
    native_text: str
    native_phonetics: str = ""


@dataclass(frozen=True)
class AppState:
    """Snapshot of HUD + backend routing. Emitted on device/language/threshold changes."""

    device_id: str
    device_name: str
    device_kind: str  # "loopback" | "mic"
    source_language: str  # "auto" or language code
    target_language: str
    noise_threshold: float  # 0.0–1.0, same scale as audio_level_changed


class EventBus(QObject):
    """Queued signals so capture/inference threads never touch widgets."""

    subtitle_ready = Signal(object)  # SubtitleUpdate
    status_changed = Signal(str)
    pipeline_error = Signal(str)
    subtitles_toggled = Signal(bool)
    target_language_changed = Signal(str)
    quit_requested = Signal()

    # Fast path: RMS/peak level 0.0–1.0, ~20–30 Hz from the capture thread.
    audio_level_changed = Signal(float)
    # Device, language routing, and noise threshold for HUD + backend.
    state_changed = Signal(object)  # AppState
