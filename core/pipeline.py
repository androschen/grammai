"""Capture and inference lifecycle managed without blocking the Qt UI."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from time import monotonic

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from audio.capture import LoopbackCapture, normalized_rms
from core.config import AppConfig
from core.events import EventBus
from ml.whisper_engine import WhisperEngine


class SpeechSegmenter:
    """Gate-based utterances with pre-roll and a silence tail; Whisper applies VAD."""
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pre = deque(maxlen=max(1, int(0.2 / config.capture_chunk_seconds)))
        self.parts: list[np.ndarray] = []
        self.samples = 0
        self.silence = 0

    def push(self, chunk: np.ndarray) -> np.ndarray | None:
        rate = self.config.sample_rate
        loud = normalized_rms(chunk, self.config.rms_full_scale) >= self.config.noise_threshold
        if not self.parts:
            if not loud:
                self.pre.append(chunk)
                return None
            self.parts.extend(self.pre)
            self.pre.clear()
            self.samples = sum(x.size for x in self.parts)
        self.parts.append(chunk)
        self.samples += chunk.size
        self.silence = 0 if loud else self.silence + chunk.size
        if self.samples < rate * 6 and self.silence < rate * 0.5:
            return None
        audio = np.concatenate(self.parts)
        voiced = self.samples - self.silence
        self.parts = []
        self.samples = self.silence = 0
        return audio if voiced >= rate * 0.4 else None


class InferenceWorker(QThread):
    subtitle = Signal(object)
    telemetry = Signal(object)

    def __init__(self, config, events, engine, audio_queue) -> None:
        super().__init__()
        self.config = config
        self.events = events
        self.engine = engine
        self.queue = audio_queue
        self.accepting_audio = False
        self.stop_requested = False

    def run(self) -> None:
        try:
            self._run()
        finally:
            close = getattr(self.engine, 'close', None)
            if close:
                close()

    def _run(self) -> None:
        # Only this worker accesses the engine; the controller serializes replacements.
        self.engine.configure(self.config)
        try:
            self.events.status_changed.emit(f"Loading Whisper {self.config.model_size} ({self.config.backend})…")
            self.engine.ensure_loaded()
        except Exception as exc:
            self.events.status_changed.emit(f"Whisper unavailable: {exc}. Use Retry models.")
            return
        if self.isInterruptionRequested():
            return
        try:
            self.engine.ensure_translator()
        except Exception as exc:
            self.events.status_changed.emit(f"Translation unavailable: {exc}. Transcription remains available.")
        else:
            self.events.status_changed.emit("Ready — listening for speech")
        # Audio collected during downloads/model loading is obsolete.
        while not self.isInterruptionRequested():
            try:
                self.queue.get_nowait()
            except Empty:
                break
        self.accepting_audio = True
        segment_started = None
        segmenter = SpeechSegmenter(self.config)
        previous = None
        while not self.isInterruptionRequested():
            try:
                chunk = self.queue.get(timeout=0.1)
            except Empty:
                continue
            if isinstance(chunk, tuple):
                chunk, captured_at = chunk
            else:
                captured_at = monotonic()
            if not segmenter.parts:
                segment_started = captured_at - len(chunk) / self.config.sample_rate - .2
            audio = segmenter.push(chunk)
            if audio is None:
                continue
            try:
                self.events.status_changed.emit("Transcribing / translating…")
                update = self.engine.process(audio, self.config.target_language)
                self.telemetry.emit(dict(self.engine.last_timings, kind="inference",
                                         backend=self.engine.active_backend,
                                         subtitle_delay_ms=(monotonic() - segment_started) * 1000))
                if self.isInterruptionRequested():
                    return
                key = (update.native_text.strip(), update.target_text.strip()) if update else None
                if update is not None and key != previous:
                    previous = key
                    self.subtitle.emit(update)
                self.events.status_changed.emit("Translation unavailable — Retry models" if update and update.translation_status == "unavailable" else "Listening for speech")
            except Exception as exc:
                self.events.status_changed.emit(f"Inference failed: {exc}. Use Retry models.")
                return

    def stop(self) -> None:
        self.stop_requested = True
        self.requestInterruption()


class TranslationPipeline(QObject):
    shutdown_finished = Signal()
    inference_failed = Signal()

    def __init__(self, config: AppConfig, events: EventBus, engine: WhisperEngine) -> None:
        super().__init__()
        self._config, self._events, self._engine = config, events, engine
        self._queue = Queue(maxsize=50)
        self._capture = None
        self._worker = None
        self._want_capture = False
        self._want_inference = False
        self._closing = False
        self._retry_pending = False
        self._benchmark = None
        self._benchmark_pending = None
        events.benchmark_requested.connect(self.request_benchmark)
        self._state = config.snapshot()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._reconcile)
        self._timer.start()

    @property
    def inference_requested(self):
        return self._want_inference

    @property
    def processing_live(self):
        return self.running and self._benchmark is None and not self._worker.stop_requested and self._worker.accepting_audio

    @property
    def active_backend(self):
        if self._benchmark is not None:
            return "Benchmark running"
        return getattr(self._engine, 'active_backend', 'Not loaded') if self.running else "Stopped"

    @property
    def active_model(self):
        if not self._worker:
            return ""
        config = self._worker.config
        return config.model_size if config.backend == "cpu" else Path(config.vulkan_model).name

    @property
    def backlog_seconds(self):
        return self._queue.qsize() * self._config.capture_chunk_seconds if self.processing_live else 0.

    @property
    def sample_rate(self):
        return self._config.sample_rate

    @Slot(object)
    def request_benchmark(self, config):
        if self._closing or self._benchmark is not None or self._benchmark_pending is not None:
            return
        self._benchmark_pending = replace(config)
        self._events.setProperty("benchmark_busy", True)
        self._events.benchmark_busy.emit(True)
        self._events.benchmark_progress.emit("Waiting for current inference to finish...")
        if self._worker:
            self._worker.stop()

    @property
    def capturing(self):
        return self._capture is not None and self._capture.isRunning()

    @property
    def running(self):
        return self._worker is not None and self._worker.isRunning()

    @Slot(object)
    def _device_resolved(self, source):
        if self.sender() is not self._capture or getattr(self._capture, "stop_requested", False):
            return
        self._config.audio_device_id = source.device_id
        self._config.audio_device_name = source.name
        self._config.audio_device_kind = source.kind
        # Resolution confirms the current capture; it does not request a restart.
        self._state = self._config.snapshot()
        self._events.state_changed.emit(self._state)

    def start_capture(self):
        self._want_capture = True

    def start_inference(self):
        self._want_capture = self._want_inference = True

    def start(self):
        self.start_inference()

    def stop_inference(self):
        self._want_inference = False
        if self._worker:
            self._worker.stop()
        self._events.status_changed.emit("Volume meter on — subtitles off")

    def restart_capture(self):
        if self._worker:
            self._worker.stop()
        if self._capture:
            self._capture.stop()

    def apply_state(self, state):
        old = self._state
        self._state = state
        if self._worker:
            self._worker.config.noise_threshold = state.noise_threshold
        if old.device_id != state.device_id:
            self.restart_capture()
        elif (old.source_language, old.target_language, old.inference_key) != (state.source_language, state.target_language, state.inference_key):
            if self._worker:
                self._worker.stop()

    def retry(self):
        self._retry_pending = True
        self.start_inference()
        if self._worker:
            self._worker.stop()

    def stop(self):
        if self._benchmark:
            self._benchmark.requestInterruption()
        self._benchmark_pending = None
        self._closing = True
        self._want_capture = self._want_inference = False
        self.restart_capture()

    @Slot(object)
    def _publish(self, update):
        if self.sender() is self._worker and self._want_inference and not self._worker.stop_requested:
            self._events.subtitle_ready.emit(update)

    @Slot(object)
    def _metrics(self, metrics):
        if self.sender() is self._worker and not self._worker.stop_requested:
            self._events.metrics_changed.emit(metrics)

    @Slot(object)
    def _benchmark_result(self, result):
        self._events.benchmark_finished.emit(result)

    @Slot(str)
    def _benchmark_progress(self, message):
        self._events.benchmark_progress.emit(message)

    def _reconcile(self):
        if self._benchmark is not None:
            if not self._benchmark.isFinished():
                return
            self._benchmark.deleteLater()
            self._benchmark = None
            self._events.setProperty("benchmark_busy", False)
            self._events.benchmark_busy.emit(False)
        if self._worker is not None:
            if self._worker.isFinished():
                interrupted = self._worker.stop_requested
                self._worker.deleteLater()
                self._worker = None
                if not interrupted:
                    self._want_inference = False
                    self.inference_failed.emit()
            elif self._worker.stop_requested:
                return
        if self._capture is not None:
            if self._capture.isFinished():
                interrupted = getattr(self._capture, "stop_requested", False)
                self._capture.deleteLater()
                self._capture = None
                if not interrupted:
                    self._want_capture = self._want_inference = False
                    self.inference_failed.emit()
                    if self._worker:
                        self._worker.stop()
            elif getattr(self._capture, "stop_requested", False):
                return
        if self._closing:
            if self._worker is None and self._capture is None:
                self._timer.stop()
                self.shutdown_finished.emit()
            return
        if self._want_capture and self._capture is None:
            self._queue = Queue(maxsize=50)
            self._capture = LoopbackCapture(self._config, self._events, self._queue)
            self._capture.device_resolved.connect(self._device_resolved)
            self._capture.start()
        if self._benchmark_pending is not None and self._worker is None:
            from core.benchmark import BenchmarkWorker
            self._benchmark = BenchmarkWorker(self._benchmark_pending)
            self._benchmark_pending = None
            self._benchmark.result.connect(self._benchmark_result)
            self._benchmark.progress.connect(self._benchmark_progress)
            self._benchmark.start()
            return
        if self._want_inference and self._worker is None:
            if self._retry_pending:
                self._engine.reset_failures()
                self._retry_pending = False
            self._worker = InferenceWorker(replace(self._config), self._events, self._engine, self._queue)
            self._worker.subtitle.connect(self._publish)
            self._worker.telemetry.connect(self._metrics)
            self._worker.start()
