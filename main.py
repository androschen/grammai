"""GrammAI entry point: wire config, event bus, pipeline, and UI."""

from __future__ import annotations

import argparse
import os
import sys

# Hugging Face on Windows without Developer Mode cannot use cache symlinks.
# This is harmless; disable the warning before any model libraries import.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from core.config import AppConfig, TargetLanguage
from core.events import EventBus
from core.pipeline import TranslationPipeline
from core.performance import PerformanceMonitor
from core.preferences import load_config, save_config
from ml.whisper_engine import WhisperEngine
from ml.translator import NllbTranslator
from ui.overlay import SubtitleOverlay
from ui.panel import ControlPanel, quit_application


class GrammAIApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._events = EventBus()
        config.apply_quality()
        self._translator = NllbTranslator(config, self._events)
        self._engine = WhisperEngine(config, self._translator)
        self._pipeline = TranslationPipeline(config, self._events, self._engine)
        self._monitor = PerformanceMonitor(self._events, self._pipeline)
        self._translation_enabled = False
        self._benchmark_active = False
        self._overlay = SubtitleOverlay(self._events, config)
        self._panel = ControlPanel(config, self._events)
        self._preference_timer = QTimer()
        self._preference_timer.setSingleShot(True)
        self._preference_timer.setInterval(300)
        self._preference_timer.timeout.connect(self._save_preferences)

        self._events.subtitles_toggled.connect(self._on_subtitles_toggled)
        self._events.subtitle_ready.connect(self._overlay.apply_subtitle)
        self._events.pipeline_error.connect(self._on_pipeline_error)
        self._events.state_changed.connect(self._on_state_changed)
        self._events.quit_requested.connect(self.shutdown)
        self._events.overlay_toggled.connect(self._on_overlay_toggled)
        self._events.benchmark_busy.connect(self._on_benchmark_busy)
        self._events.retry_requested.connect(self._retry_models)
        self._pipeline.shutdown_finished.connect(self._finish_shutdown)
        self._pipeline.inference_failed.connect(self._inference_failed)
        self._events.state_changed.emit(config.snapshot())

    def show(self) -> None:
        self._panel.show()
        self._pipeline.start_capture()

    def start_on(self) -> None:
        self._panel.set_subtitles_on(True)
        self._on_subtitles_toggled(True)

    def _on_subtitles_toggled(self, enabled: bool) -> None:
        self._translation_enabled = enabled
        self._panel.set_subtitles_on(enabled)
        if enabled:
            self._overlay.reset_text()
            self._pipeline.start_inference()
        else:
            self._pipeline.stop_inference()
        self._update_overlay_visibility()

    def _retry_models(self):
        self._on_subtitles_toggled(True)
        self._pipeline.retry()

    def _on_overlay_toggled(self, enabled):
        self._config.show_overlay = enabled
        self._preference_timer.start()
        self._update_overlay_visibility()

    def _on_benchmark_busy(self, busy):
        self._benchmark_active = busy
        self._update_overlay_visibility()

    def _update_overlay_visibility(self):
        self._overlay.setVisible(self._translation_enabled and self._config.show_overlay and not self._benchmark_active)

    def _save_preferences(self):
        try:
            save_config(self._config)
        except OSError as exc:
            self._panel.set_status(f"Could not save preferences: {exc}")

    def _on_pipeline_error(self, message: str) -> None:
        self._panel.set_status(message)

    def _on_state_changed(self, state) -> None:
        self._pipeline.apply_state(state)
        self._preference_timer.start()
        self._update_overlay_visibility()

    def _inference_failed(self) -> None:
        self._translation_enabled = False
        self._panel.set_subtitles_on(False)
        self._overlay.hide()

    def shutdown(self) -> None:
        self._preference_timer.stop()
        self._save_preferences()
        self._monitor.timer.stop()
        self._panel.setEnabled(False)
        self._panel.set_status("Stopping workers...")
        self._pipeline.stop()

    def _finish_shutdown(self) -> None:
        self._overlay.close()
        self._panel.mark_quitting()
        self._panel.close()
        quit_application()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GrammAI realtime translator")
    parser.add_argument(
        "--target",
        choices=[lang.value for lang in TargetLanguage],
        default=None,
    )
    parser.add_argument(
        "--model",
        default=None,
        help="faster-whisper model size (tiny, base, small, …).",
    )
    parser.add_argument("--start-on", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    config = load_config()
    if args.target:
        config.target_language = TargetLanguage(args.target)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("GrammAI")

    window = GrammAIApp(config)
    if args.model:
        config.model_size = args.model
    window.show()
    if args.start_on:
        window.start_on()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
