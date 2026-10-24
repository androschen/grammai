"""Capture and inference lifecycle managed without blocking the Qt UI."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from time import monotonic
from threading import Event

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from audio.capture import CapturedAudio, LoopbackCapture, normalized_rms
from audio.replay import ReplayStore
from core.config import AppConfig
from core.events import EventBus
from ml.whisper_engine import WhisperEngine


from audio.segmentation import SpeechSegmenter, StreamingSpeechDetector


class InferenceWorker(QThread):
    subtitle = Signal(object,object,float)
    telemetry = Signal(object)

    def __init__(self, config, events, engine, audio_queue) -> None:
        super().__init__()
        self.config = config
        self.events = events
        self.engine = engine
        self.queue = audio_queue
        self.accepting_audio = False
        self.stop_requested = False
        self.pause_requested = Event()

    def run(self) -> None:
        try:
            self._run()
        finally:
            close = getattr(self.engine, 'close', None)
            if close:
                close()

    def _run(self) -> None:
        # Only this worker accesses the engine; the controller serializes replacements.
        if hasattr(getattr(self.engine,'_translator',None),'cancelled'):
            self.engine._translator.cancelled=self.isInterruptionRequested
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
        detector=None
        if self.config.speech_detection:
            try:
                detector=StreamingSpeechDetector()
            except Exception as exc:
                self.events.status_changed.emit(f'Speech detector unavailable; using volume gate: {exc}')
        segmenter = SpeechSegmenter(self.config,detector)
        was_paused=False
        previous_sequence = None
        while not self.isInterruptionRequested():
            if self.pause_requested.is_set():
                was_paused=True
                self.msleep(50)
                continue
            if was_paused:
                if detector is not None:
                    detector.reset()
                segmenter=SpeechSegmenter(self.config,detector)
                while True:
                    try:
                        self.queue.get_nowait()
                    except Empty:
                        break
                previous_sequence = None
                reset = getattr(self.engine, 'reset_context', None)
                if reset:
                    reset()
                was_paused=False
            try:
                chunk = self.queue.get(timeout=0.1)
            except Empty:
                continue
            if isinstance(chunk, CapturedAudio):
                if previous_sequence is not None and chunk.sequence != previous_sequence + 1:
                    # Never splice speech across a queue overflow. The unfinished
                    # fragment and overlap are incomplete evidence for recognition.
                    if detector is not None:
                        detector.reset()
                    segmenter = SpeechSegmenter(self.config, detector)
                    reset = getattr(self.engine, 'reset_context', None)
                    if reset:
                        reset()
                    self.telemetry.emit({'kind': 'audio_discontinuity',
                        'missing_chunks': max(0, chunk.sequence - previous_sequence - 1)})
                previous_sequence = chunk.sequence
                chunk, captured_at = chunk.samples, chunk.captured_at
            elif isinstance(chunk, tuple):
                chunk, captured_at = chunk
            else:
                captured_at = monotonic()
            audio = segmenter.push(chunk)
            if audio is None:
                continue
            try:
                self.events.status_changed.emit("Transcribing / translating…")
                overlap_setter=getattr(self.engine,'set_audio_overlap',None)
                if overlap_setter:
                    overlap_setter(segmenter.last_overlap_samples/self.config.sample_rate)
                update = self.engine.process(audio, self.config.target_language)
                self.telemetry.emit(dict(self.engine.last_timings, kind="inference",
                                         backend=self.engine.active_backend,
                                         subtitle_delay_ms=(monotonic() - captured_at + len(audio)/self.config.sample_rate) * 1000))
                if self.isInterruptionRequested():
                    return
                if self.pause_requested.is_set():
                    was_paused=True
                    continue
                if update is not None:
                    self.subtitle.emit(update,audio,captured_at)
                self.events.status_changed.emit("Translation unavailable — Retry models" if update and update.translation_status == "unavailable" else "Listening for speech")
            except Exception as exc:
                if self.isInterruptionRequested():
                    return
                self.events.status_changed.emit(f"Inference failed: {exc}. Use Retry models.")
                return

    def stop(self) -> None:
        self.stop_requested = True
        self.requestInterruption()
        translator=getattr(self.engine,'_translator',None)
        if getattr(translator,'claimed',False):
            translator.runtime.interrupt()


class TranslationPipeline(QObject):
    shutdown_finished = Signal()
    inference_failed = Signal()

    def __init__(self, config: AppConfig, events: EventBus, engine: WhisperEngine) -> None:
        super().__init__()
        self._config, self._events, self._engine = config, events, engine
        self._queue = Queue(maxsize=max(50,round(6/self._config.capture_chunk_seconds)))
        self._capture = None
        self._worker = None
        self._want_capture = False
        self._want_inference = False
        self._closing = False
        self._retry_pending = False
        self.replays = ReplayStore(config.sample_rate)
        self._next_replay_cleanup=monotonic()+1
        self._replay_active = False
        self._review = None
        self._review_pending = None
        events.review_requested.connect(self.request_review)
        events.playback_active.connect(self.pause_for_replay)
        events.replay_clear_requested.connect(self.replays.clear)
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
        return self.running and self._review is None and not self._replay_active and self._benchmark is None and not self._worker.stop_requested and self._worker.accepting_audio

    @property
    def active_backend(self):
        if self._review is not None:
            return "Retranslating text"
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

    @property
    def model_tasks_idle(self):
        return (not self._closing and not self._want_inference and self._worker is None
            and self._review is None and self._review_pending is None
            and self._benchmark is None and self._benchmark_pending is None)

    @Slot(object)
    def request_benchmark(self, config):
        if self._events.property('comparison_busy'):
            self._events.benchmark_progress.emit('Finish or cancel translator comparison first.')
            return
        if self._closing or self._review is not None or self._review_pending is not None or self._benchmark is not None or self._benchmark_pending is not None:
            return
        self._benchmark_pending = replace(config)
        self._events.setProperty("benchmark_busy", True)
        self._events.benchmark_busy.emit(True)
        self._events.benchmark_progress.emit("Waiting for current inference to finish...")
        if self._worker:
            self._worker.stop()

    @Slot(object)
    def request_review(self,request):
        if self._events.property('comparison_busy'):
            self._events.review_finished.emit({'id':request['update'].uid,'error':'Finish or cancel translator comparison first.'})
            return
        analysis=getattr(self._events,'analysis_service',None)
        if analysis is not None and analysis.busy:
            self._events.review_finished.emit({'id':request['update'].uid,'error':'Context analysis is finishing. Try Recheck again shortly.'})
            return
        if self._closing or self._review is not None or self._review_pending is not None or self._benchmark is not None or self._benchmark_pending is not None:
            self._events.review_finished.emit({'id':request['update'].uid,'error':'Another model task is running. Try again when it finishes.'})
            return
        self._review_pending=dict(request)
        if request.get('recheck'):
            # Snapshot the bounded clip before model shutdown; it may expire while waiting.
            self._review_pending['audio']=self.replays.get(request['update'].audio_id)
        self._events.setProperty('review_busy',True)
        self._events.review_busy.emit(True)
        self._events.activity_changed.emit('Manual sentence recheck' if request.get('recheck') else 'Text retranslation')
        if self._worker:
            self._worker.stop()

    @Slot(bool)
    def pause_for_replay(self,active):
        if self._closing:
            return
        self._replay_active=active
        if self._capture and hasattr(self._capture,'suppress_audio'):
            if active:
                self._capture.suppress_audio.set()
            else:
                self._capture.suppress_audio.clear()
        if self._worker:
            if active:
                self._worker.pause_requested.set()
            else:
                self._worker.pause_requested.clear()

    @Slot(object)
    def _review_result(self,result):
        if 'duration_ms' in result:
            self._events.setProperty('recheck_duration_ms',result['duration_ms'])
        self._events.activity_changed.emit('Sentence recheck failed' if 'error' in result else 'Sentence recheck complete')
        if 'update' in result and not result.get('requires_confirmation'):
            self._events.subtitle_corrected.emit(result['update'])
        self._events.review_finished.emit(result)

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
        if self._events.property('comparison_busy'):
            self._events.status_changed.emit('Finish or cancel translator comparison before starting live subtitles.')
            self.inference_failed.emit()
            return
        self._want_capture = self._want_inference = True

    def start(self):
        self.start_inference()

    def stop_inference(self):
        self._want_inference = False
        if self._worker:
            self._worker.stop()
        self._events.status_changed.emit("Volume meter on — subtitles off")

    def restart_capture(self):
        self.replays.clear()
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
        self.replays.clear()
        self._review_pending = None
        if self._review:
            self._review.requestInterruption()
        if self._benchmark:
            self._benchmark.requestInterruption()
        self._benchmark_pending = None
        self._closing = True
        self._want_capture = self._want_inference = False
        self.restart_capture()

    @Slot(object,object,float)
    def _publish(self, update,audio,captured_at):
        if self.sender() is self._worker and self._want_inference and not self._worker.stop_requested:
            key=self.replays.add(update.uid,audio,captured_at-len(audio)/self._config.sample_rate)
            self._events.subtitle_ready.emit(replace(update,audio_id=key))

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
        if monotonic()>=self._next_replay_cleanup:
            self.replays.stats()
            self._next_replay_cleanup=monotonic()+1
        if self._review is not None:
            if not self._review.isFinished():
                return
            self._review.deleteLater()
            self._review=None
            self._events.review_busy.emit(False)
            self._events.setProperty('review_busy',False)
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
                self._events.setProperty('local_translation_owned',False)
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
            self._queue = Queue(maxsize=max(50,round(6/self._config.capture_chunk_seconds)))
            self._capture = LoopbackCapture(self._config, self._events, self._queue)
            if self._replay_active and hasattr(self._capture,"suppress_audio"):
                self._capture.suppress_audio.set()
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
        if self._review_pending is not None and self._worker is None:
            from ml.review import ReviewWorker
            self._review=ReviewWorker(replace(self._config),self._review_pending)
            self._review_pending=None
            self._review.result.connect(self._review_result)
            self._review.start()
            return
        if self._want_inference and self._worker is None and not self._replay_active and not self._events.property('comparison_busy'):
            analysis=getattr(self._events,'analysis_service',None)
            if self._config.translation_enabled and self._config.translation_mode=='context' and analysis is not None and analysis.busy:
                return
            self._events.setProperty('local_translation_owned',self._config.translation_enabled and self._config.translation_mode=='context')
            if self._retry_pending:
                self._engine.reset_failures()
                self._retry_pending = False
            self._worker = InferenceWorker(replace(self._config), self._events, self._engine, self._queue)
            self._worker.subtitle.connect(self._publish)
            self._worker.telemetry.connect(self._metrics)
            self._worker.start()
