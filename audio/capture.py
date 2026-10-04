"""WASAPI loopback / microphone capture via soundcard."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Full, Queue

import numpy as np
import soundcard as sc
from PySide6.QtCore import QThread

from core.config import AppConfig
from core.events import EventBus


@dataclass(frozen=True)
class AudioSource:
    device_id: str
    name: str
    kind: str  # "loopback" | "mic"


def _mic_id(mic) -> str:
    identifier = getattr(mic, "id", None)
    if identifier is None:
        return mic.name
    return str(identifier)


def list_audio_sources() -> list[AudioSource]:
    sources: list[AudioSource] = []
    seen: set[str] = set()
    for mic in sc.all_microphones(include_loopback=True):
        kind = "loopback" if getattr(mic, "isloopback", False) else "mic"
        source = AudioSource(device_id=_mic_id(mic), name=mic.name, kind=kind)
        if source.device_id in seen:
            continue
        seen.add(source.device_id)
        sources.append(source)
    return sources


def find_loopback_microphone():
    """Prefer the default speaker's loopback so we hear system audio, not the mic."""
    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("No default playback device found.")

    loopbacks = [
        mic
        for mic in sc.all_microphones(include_loopback=True)
        if getattr(mic, "isloopback", False)
    ]
    speaker_name = (speaker.name or "").lower()
    for mic in loopbacks:
        if speaker_name and speaker_name in (mic.name or "").lower():
            return mic
    if loopbacks:
        return loopbacks[0]

    try:
        return sc.get_microphone(id=speaker.id, include_loopback=True)
    except Exception:
        return sc.get_microphone(speaker.name, include_loopback=True)


def resolve_microphone(config: AppConfig):
    if config.audio_device_id:
        for mic in sc.all_microphones(include_loopback=True):
            if _mic_id(mic) == config.audio_device_id:
                return mic
        for mic in sc.all_microphones(include_loopback=True):
            if mic.name == config.audio_device_name:
                return mic
    return find_loopback_microphone()


def to_mono_float32(frames: np.ndarray) -> np.ndarray:
    data = np.asarray(frames, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)
    return np.ascontiguousarray(data, dtype=np.float32)


def normalized_rms(samples: np.ndarray, full_scale: float = 0.25) -> float:
    """Map chunk loudness onto 0–1 for the HUD meter. Mix RMS + peak so the bar bounces."""
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    peak = float(np.max(np.abs(samples)))
    scale = full_scale if full_scale > 1e-6 else 0.25
    mixed = 0.65 * (rms / scale) + 0.35 * (peak / max(scale, 1e-6))
    return min(1.0, mixed)


class LoopbackCapture(QThread):
    """Records short chunks, emits RMS on the fast path, then queues audio for Whisper."""

    def __init__(self, config: AppConfig, events: EventBus, queue: Queue) -> None:
        super().__init__()
        self._config = config
        self._events = events
        self._queue = queue

    def run(self) -> None:
        try:
            mic = resolve_microphone(self._config)
        except Exception as exc:
            self._events.pipeline_error.emit(f"Audio device error: {exc}")
            return

        kind = "loopback" if getattr(mic, "isloopback", False) else "mic"
        self._config.audio_device_id = _mic_id(mic)
        self._config.audio_device_name = mic.name
        self._config.audio_device_kind = kind
        self._events.state_changed.emit(self._config.snapshot())
        self._events.status_changed.emit(f"Capturing: {mic.name}")

        chunk = max(self._config.chunk_samples, 320)
        try:
            with self._open_recorder(mic) as recorder:
                while not self.isInterruptionRequested():
                    frames = recorder.record(numframes=chunk)
                    mono = to_mono_float32(frames)
                    if mono.size == 0:
                        continue
                    # Fast path: RMS only. Emit is queued to the UI thread; do not wait.
                    level = normalized_rms(mono, self._config.rms_full_scale)
                    self._events.audio_level_changed.emit(level)
                    self._push(mono)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self._events.pipeline_error.emit(f"Capture failed: {exc}")

    def _open_recorder(self, mic):
        rate = self._config.sample_rate
        try:
            return mic.recorder(samplerate=rate, channels=1)
        except Exception:
            return mic.recorder(samplerate=rate, channels=2)

    def _push(self, chunk: np.ndarray) -> None:
        try:
            self._queue.put_nowait(chunk)
        except Full:
            try:
                self._queue.get_nowait()
            except Exception:
                pass
            try:
                self._queue.put_nowait(chunk)
            except Full:
                pass

    def stop(self) -> None:
        self.requestInterruption()
