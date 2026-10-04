"""GrammAI entry point: wire config, event bus, pipeline, and UI."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from core.config import AppConfig, TargetLanguage
from core.events import EventBus
from core.pipeline import TranslationPipeline
from ml.whisper_engine import WhisperEngine
from ui.overlay import SubtitleOverlay
from ui.panel import ControlPanel, quit_application


class GrammAIApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._events = EventBus()
        self._engine = WhisperEngine(config)
        self._pipeline = TranslationPipeline(config, self._events, self._engine)
        self._overlay = SubtitleOverlay(self._events, config)
        self._panel = ControlPanel(config, self._events)
        self._last_device_id = config.audio_device_id

        self._events.subtitles_toggled.connect(self._on_subtitles_toggled)
        self._events.subtitle_ready.connect(self._overlay.apply_subtitle)
        self._events.pipeline_error.connect(self._on_pipeline_error)
        self._events.state_changed.connect(self._on_state_changed)
        self._events.quit_requested.connect(self.shutdown)
        self._events.state_changed.emit(config.snapshot())

    def show(self) -> None:
        self._panel.show()
        self._pipeline.start_capture()

    def start_on(self) -> None:
        self._panel.set_subtitles_on(True)
        self._on_subtitles_toggled(True)

    def _on_subtitles_toggled(self, enabled: bool) -> None:
        self._panel.set_subtitles_on(enabled)
        if enabled:
            self._overlay.reset_text()
            self._overlay.show()
            self._pipeline.start_inference()
        else:
            self._pipeline.stop_inference()
            self._overlay.hide()

    def _on_pipeline_error(self, message: str) -> None:
        self._panel.set_status(message)

    def _on_state_changed(self, state) -> None:
        previous = self._last_device_id
        if previous == state.device_id:
            return
        self._last_device_id = state.device_id
        if previous and self._pipeline.capturing:
            self._pipeline.restart_capture()

    def shutdown(self) -> None:
        self._pipeline.stop()
        self._overlay.close()
        self._panel.mark_quitting()
        self._panel.close()
        quit_application()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GrammAI realtime translator")
    parser.add_argument(
        "--target",
        choices=[lang.value for lang in TargetLanguage],
        default=TargetLanguage.CHINESE.value,
    )
    parser.add_argument(
        "--model",
        default="base",
        help="faster-whisper model size (tiny, base, small, …).",
    )
    parser.add_argument("--start-on", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    config = AppConfig(
        model_size=args.model,
        target_language=TargetLanguage(args.target),
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("GrammAI")

    window = GrammAIApp(config)
    window.show()
    if args.start_on:
        window.start_on()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
