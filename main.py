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
from core.phrasebook import Phrasebook
from audio.playback import AudioReplay
from ml.whisper_engine import WhisperEngine
from ml.translator import NllbTranslator
from ui.overlay import SubtitleOverlay
from ui.panel import ControlPanel, quit_application


class GrammAIApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._events = EventBus()
        config.apply_quality()
        from core.analysis import AnalysisService
        from ml.live_translator import LiveTranslator
        self._analysis = AnalysisService(events=self._events,config=config)
        self._events.analysis_service = self._analysis
        self._translator = LiveTranslator(config,NllbTranslator(config,self._events),self._analysis.runtime,self._events)
        self._engine = WhisperEngine(config,self._translator)
        self._engine.activity_callback = self._events.activity_changed.emit
        self._pipeline_finished = False
        self._analysis.idle.connect(self._analysis_idle)
        self._pipeline = TranslationPipeline(config, self._events, self._engine)
        self._events.comparison_allowed=lambda:self._pipeline.model_tasks_idle
        self._player = AudioReplay(self._events,self._pipeline.replays)
        self._phrasebook = Phrasebook()
        self._learning_active = False
        self._playback_active = False
        self._last_update = None
        self._phrase_dialog = None
        self._monitor = PerformanceMonitor(self._events, self._pipeline)
        self._translation_enabled = False
        self._benchmark_active = False
        self._overlay = SubtitleOverlay(self._events, config)
        self._panel = ControlPanel(config, self._events,replays=self._pipeline.replays)
        from core.live_review import LiveReview
        self._live_review=LiveReview(config,self._events,self._analysis,self._panel._history,lambda:self._pipeline.inference_requested)
        self._preference_timer = QTimer()
        self._preference_timer.setSingleShot(True)
        self._preference_timer.setInterval(300)
        self._preference_timer.timeout.connect(self._save_preferences)

        self._events.subtitles_toggled.connect(self._on_subtitles_toggled)
        self._events.subtitle_ready.connect(self._overlay.apply_subtitle)
        self._events.subtitle_ready.connect(self._remember_subtitle)
        self._events.subtitle_corrected.connect(self._corrected_subtitle)
        self._events.learning_requested.connect(self._open_study)
        self._events.phrase_explain_requested.connect(self._open_phrase)
        self._events.review_busy.connect(self._on_review_busy)
        self._events.playback_active.connect(self._on_playback_active)
        self._events.replay_clear_requested.connect(self._player.stop)
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
        if enabled and not self._translation_enabled:
            self._panel._history.begin_context()
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

    def _remember_subtitle(self,update):
        self._last_update=update

    def _corrected_subtitle(self,update):
        if self._last_update and self._last_update.uid==update.uid:
            self._last_update=update
            # History revisions should not rewrite a subtitle already being read.

    def _open_phrase(self,payload):
        from ui.phrase_explain import PhraseExplanationDialog
        from ui.analysis import preceding_context
        if self._phrase_dialog is not None:
            self._phrase_dialog.close()
        self._live_review.defer_for_explanation()
        data=dict(payload,example_translation=payload['update'].target_text if payload.get('text_role')!='translation' else '',
            original_text=payload['update'].native_text,
            original_language=payload['update'].source_language,
            audio_id=payload['update'].audio_id,
            context=preceding_context(self._panel._history,payload['update'],2))
        try:
            dialog=PhraseExplanationDialog(self._config,self._events,self._analysis,data,self._phrasebook,self._panel,replays=self._pipeline.replays)
        except ValueError as exc:
            self._panel.set_status(str(exc));return
        self._events.setProperty('phrase_explanation_open',True)
        self._phrase_dialog=dialog
        def finished(result):
            if self._phrase_dialog is dialog:
                self._phrase_dialog=None;self._events.setProperty('phrase_explanation_open',False)
            dialog.deleteLater()
        dialog.finished.connect(finished);dialog.show()

    def _open_study(self,update):
        from ui.learning import StudyDialog
        dialog=StudyDialog(update,self._config,self._events,self._pipeline.replays,self._phrasebook,self._panel,
            analysis=self._analysis,history=self._panel._history)
        self._panel.open_sentence_details(dialog)

    def _on_review_busy(self,busy):
        self._learning_active=busy
        self._panel.set_status("Rechecking sentence..." if busy else ("Resuming live translation..." if self._translation_enabled else "Ready. Translation is stopped."))
        self._update_overlay_visibility()

    def _on_playback_active(self,active):
        self._playback_active=active
        if not active:
            self._panel.set_status("Resuming live translation..." if self._translation_enabled else "Replay finished. Translation is stopped.")
        self._update_overlay_visibility()

    def _update_overlay_visibility(self):
        self._overlay.setVisible(self._translation_enabled and self._config.show_overlay and not self._benchmark_active and not self._learning_active and not self._playback_active)

    def _save_preferences(self):
        try:
            save_config(self._config)
        except OSError as exc:
            self._panel.set_status(f"Could not save preferences: {exc}")

    def _on_pipeline_error(self, message: str) -> None:
        self._panel.set_status(message)

    def _on_state_changed(self, state) -> None:
        route=(state.device_id,state.source_language)
        if getattr(self,'_context_route',None)!=route:
            self._panel._history.begin_context()
            self._context_route=route
        self._pipeline.apply_state(state)
        self._preference_timer.start()
        self._update_overlay_visibility()

    def _inference_failed(self) -> None:
        self._translation_enabled = False
        self._panel.set_subtitles_on(False)
        self._overlay.hide()

    def shutdown(self) -> None:
        self._live_review.close()
        if self._phrase_dialog is not None:
            self._phrase_dialog.close()
        self._panel.dispose_learning()
        self._analysis.shutdown()
        self._player.stop()
        speech=getattr(self._events,'pronunciation_service',None)
        if speech is not None:speech.stop()
        self._preference_timer.stop()
        self._save_preferences()
        self._monitor.timer.stop()
        self._monitor.gpu.close()
        self._panel.setEnabled(False)
        self._panel.set_status("Stopping workers...")
        self._pipeline.stop()

    def _finish_shutdown(self) -> None:
        self._pipeline_finished = True
        if self._analysis.busy:
            self._panel.set_status('Waiting for the analysis connection to finish...')
            return
        self._overlay.close()
        self._panel.mark_quitting()
        self._panel.close()
        quit_application()

    def _analysis_idle(self):
        if self._pipeline_finished:
            self._finish_shutdown()


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
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--smoke-report',default=None,help=argparse.SUPPRESS)
    parser.add_argument('--verify-models',action='store_true',help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    config = load_config()
    if args.target:
        config.target_language = TargetLanguage(args.target)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("GrammAI")
    from core.version import APP_VERSION
    from PySide6.QtGui import QIcon
    from pathlib import Path
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent/'ui'/'assets'/'grammai.svg')))
    if args.smoke_test:
        from core.packaging_check import smoke_check
        return smoke_check(args.smoke_report,args.verify_models)
    from core.desktop import SingleInstance,configure_logging
    configure_logging()
    instance=SingleInstance()
    if not instance.acquire():
        return 0
    # Recover only an absent deck. A deliberately cleared [] deck stays cleared.
    from core.preferences import data_dir
    if not (data_dir()/'phrases.json').exists():
        from core.deck_recovery import recover_deck
        try:
            recovery=recover_deck()
            if recovery['recovered']:
                import logging
                logging.getLogger(__name__).warning('Recovered %s cards from redirected launcher storage',recovery['recovered'])
        except (OSError,ValueError):
            import logging
            logging.exception('Saved-card recovery failed; source files were retained')
    from core.paths import register_existing_models
    register_existing_models()

    window = GrammAIApp(config)
    instance.on_activate(window._panel.reveal)
    if args.model:
        config.model_size = args.model
    window.show()
    if args.start_on:
        window.start_on()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
