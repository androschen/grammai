"""Low-frequency process monitoring and inference counters."""
from __future__ import annotations
from PySide6.QtCore import QObject, QTimer, Slot


class PerformanceMonitor(QObject):
    def __init__(self, events, pipeline, parent=None):
        super().__init__(parent)
        self.events, self.pipeline = events, pipeline
        self.latest = {}
        self.dropped_samples = 0
        self._children = {}
        try:
            import psutil
            self._psutil = psutil
            self._process = psutil.Process()
            self._process.cpu_percent(None)
        except ImportError:
            self._process = None
        events.audio_dropped.connect(self._drop)
        events.metrics_changed.connect(self._record)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.sample)
        self.timer.start()

    @Slot(int)
    def _drop(self, samples):
        if self.pipeline.processing_live:
            self.dropped_samples += samples

    @Slot(object)
    def _record(self, metrics):
        if metrics.get("kind") == "inference":
            self.latest = dict(metrics)

    def sample(self):
        metrics = dict(self.latest)
        metrics["kind"] = "live"
        metrics["running"] = self.pipeline.inference_requested
        metrics["backlog_seconds"] = self.pipeline.backlog_seconds
        metrics["dropped_seconds"] = self.dropped_samples / self.pipeline.sample_rate
        metrics["gpu_percent"] = None
        metrics["gpu_memory_mb"] = None
        metrics["backend"] = self.pipeline.active_backend
        metrics["model"] = self.pipeline.active_model
        if self._process is not None:
            try:
                children = {p.pid: self._children.get(p.pid, p) for p in self._process.children(recursive=True)}
                self._children = children
                processes = [self._process, *children.values()]
                cpu = sum(p.cpu_percent(None) for p in processes)
                memory = sum(p.memory_info().rss for p in processes)
                metrics["cpu_percent"] = cpu / (self._psutil.cpu_count() or 1)
                metrics["memory_mb"] = memory / 1024 ** 2
            except self._psutil.Error:
                metrics["cpu_percent"] = metrics["memory_mb"] = None
        self.events.metrics_changed.emit(metrics)
