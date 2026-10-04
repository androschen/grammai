"""Audio buffer + Whisper inference thread."""

from __future__ import annotations

from queue import Empty, Queue

import numpy as np
from PySide6.QtCore import QThread

from audio.capture import LoopbackCapture, normalized_rms
from core.config import AppConfig
from core.events import EventBus
from ml.whisper_engine import WhisperEngine


class _RingBuffer:
    def __init__(self, size: int) -> None:
        self._data = np.zeros(size, dtype=np.float32)
        self._size = size
        self._n = 0
        self._write = 0

    def push(self, chunk: np.ndarray) -> None:
        n = int(chunk.size)
        if n <= 0:
            return
        if n >= self._size:
            self._data[:] = chunk[-self._size :]
            self._n = self._size
            self._write = 0
            return
        end = self._write + n
        if end <= self._size:
            self._data[self._write : end] = chunk
        else:
            first = self._size - self._write
            self._data[self._write :] = chunk[:first]
            self._data[: n - first] = chunk[first:]
        self._write = (self._write + n) % self._size
        self._n = min(self._size, self._n + n)

    @property
    def filled(self) -> bool:
        return self._n >= self._size

    def latest(self) -> np.ndarray:
        if self._n < self._size:
            return self._data[: self._n].copy()
        return np.concatenate((self._data[self._write :], self._data[: self._write]))


class InferenceWorker(QThread):
    """Pulls the latest loopback window and runs faster-whisper."""

    def __init__(
        self,
        config: AppConfig,
        events: EventBus,
        engine: WhisperEngine,
        audio_queue: Queue,
    ) -> None:
        super().__init__()
        self._config = config
        self._events = events
        self._engine = engine
        self._audio_queue = audio_queue

    def run(self) -> None:
        ring = _RingBuffer(self._config.buffer_samples)
        hop = max(int(self._config.sample_rate * 2.0), 1)
        new_samples = 0
        try:
            self._events.status_changed.emit(
                f"Loading Whisper {self._config.model_size} "
                f"({self._config.device}/{self._config.compute_type})…"
            )
            self._engine.ensure_loaded()
            self._events.status_changed.emit("Listening to system audio.")
        except Exception as exc:
            self._events.status_changed.emit(f"Whisper unavailable: {exc}")
            return

        while not self.isInterruptionRequested():
            new_samples += self._drain_into(ring)
            if not ring.filled or new_samples < hop:
                self.msleep(40)
                continue
            audio = ring.latest()
            new_samples = 0
            if normalized_rms(audio, self._config.rms_full_scale) < self._config.noise_threshold:
                continue
            try:
                update = self._engine.process(audio, self._config.target_language)
            except Exception as exc:
                self._events.status_changed.emit(f"Inference error: {exc}")
                self.msleep(500)
                continue
            if update is not None:
                self._events.subtitle_ready.emit(update)

    def _drain_into(self, ring: _RingBuffer) -> int:
        added = 0
        while not self.isInterruptionRequested():
            try:
                chunk = self._audio_queue.get_nowait()
            except Empty:
                break
            ring.push(chunk)
            added += int(chunk.size)
        return added

    def stop(self) -> None:
        self.requestInterruption()


class TranslationPipeline:
    """Owns capture + inference threads; UI only toggles this on and off."""

    def __init__(self, config: AppConfig, events: EventBus, engine: WhisperEngine) -> None:
        self._config = config
        self._events = events
        self._engine = engine
        self._queue: Queue = Queue(maxsize=256)
        self._capture: LoopbackCapture | None = None
        self._worker: InferenceWorker | None = None

    @property
    def capturing(self) -> bool:
        return self._capture is not None and self._capture.isRunning()

    @property
    def running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start_capture(self) -> None:
        if self.capturing:
            return
        self._stop_capture()
        self._queue = Queue(maxsize=256)
        self._capture = LoopbackCapture(self._config, self._events, self._queue)
        self._capture.start()

    def restart_capture(self) -> None:
        infer = self.running
        self._stop_worker()
        self._stop_capture()
        self.start_capture()
        if infer:
            self.start_inference()

    def start_inference(self) -> None:
        if not self.capturing:
            self.start_capture()
        self._stop_worker()
        self._worker = InferenceWorker(self._config, self._events, self._engine, self._queue)
        self._worker.start()

    def start(self) -> None:
        self.start_capture()
        self.start_inference()

    def stop_inference(self) -> None:
        self._stop_worker()
        self._events.status_changed.emit("Volume meter on — subtitles off")

    def stop(self) -> None:
        self._stop_worker()
        self._stop_capture()
        self._events.status_changed.emit("Listening for volume (subtitles off)")

    def _stop_capture(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is not None:
            capture.stop()
            capture.wait(2000)

    def _stop_worker(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.stop()
            worker.wait(8000)
