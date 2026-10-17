"""Regression checks for routing, lifecycle, segmentation and session history."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.config import AppConfig, QualityMode, TargetLanguage
from core.events import EventBus, SubtitleUpdate
from core.history import SessionHistory
from core.pipeline import SpeechSegmenter, TranslationPipeline
from ml.phonetics import phonetics_auto
from ml.translator import NllbTranslator, whisper_to_short_code
from ml.whisper_engine import WhisperEngine
from ui.history import HistoryPanel
from ui.overlay import SubtitleOverlay

APP = QApplication.instance() or QApplication([])


class RoutingTests(unittest.TestCase):
    def test_translation_failure_does_not_masquerade_as_target(self):
        translator = Mock()
        translator.translate.side_effect = RuntimeError("offline")
        engine = WhisperEngine(AppConfig(), translator)
        engine._transcribe = Mock(return_value=("Hello", "en"))
        result = engine.process(np.ones(16000), TargetLanguage.CHINESE)
        self.assertEqual(result.target_text, "")
        self.assertEqual(result.native_text, "Hello")
        self.assertEqual(result.translation_status, "unavailable")

    def test_chinese_translation_has_pinyin(self):
        translator = Mock()
        translator.translate.return_value = "\u4f60\u597d"
        engine = WhisperEngine(AppConfig(), translator)
        engine._transcribe = Mock(return_value=("Hello", "en"))
        result = engine.process(np.ones(16000), TargetLanguage.CHINESE)
        self.assertEqual(result.phonetics, "n\u01d0 h\u01ceo")
        self.assertEqual(result.translation_status, "translated")

    def test_same_language_skips_translation(self):
        translator = Mock()
        engine = WhisperEngine(AppConfig(), translator)
        engine._transcribe = Mock(return_value=("\u4f60\u597d", "zh"))
        result = engine.process(np.ones(16000), TargetLanguage.CHINESE)
        translator.translate.assert_not_called()
        self.assertEqual(result.translation_status, "same_language")
        self.assertTrue(result.native_phonetics)

    def test_retry_clears_cached_failure(self):
        translator = NllbTranslator(AppConfig())
        with patch.object(translator, '_load', side_effect=RuntimeError('offline')) as load:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    translator.ensure_loaded()
            self.assertEqual(load.call_count, 1)
            translator.reset_failure()
            with self.assertRaises(RuntimeError):
                translator.ensure_loaded()
            self.assertEqual(load.call_count, 2)

    def test_unknown_language_is_not_english(self):
        self.assertEqual(whisper_to_short_code('ja', 'hello'), 'ja')
        self.assertEqual(whisper_to_short_code('ja', '\u65e5\u672c'), 'ja')

    def test_thai_pronunciation(self):
        self.assertTrue(phonetics_auto('\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e04\u0e23\u0e31\u0e1a').isascii())


class SegmentTests(unittest.TestCase):
    def test_silence_tail_finalizes_once(self):
        config = AppConfig()
        segmenter = SpeechSegmenter(config)
        quiet = np.zeros(config.chunk_samples, dtype=np.float32)
        speech = np.full(config.chunk_samples, 0.1, dtype=np.float32)
        outputs = []
        for chunk in [quiet] * 10 + [speech] * 25 + [quiet] * 30:
            result = segmenter.push(chunk)
            if result is not None:
                outputs.append(result)
        self.assertEqual(len(outputs), 1)
        self.assertGreater(outputs[0].size, config.sample_rate)


class UITests(unittest.TestCase):
    def test_history_limit_clear_and_repeat(self):
        model = SessionHistory()
        panel = HistoryPanel()
        for index in range(90):
            item = SubtitleUpdate('', str(index), str(index))
            if model.append(item):
                panel.append(item)
        self.assertEqual(len(model), 80)
        self.assertEqual(panel._card_count(), 80)
        self.assertFalse(model.append(item))
        panel.cleared.connect(model.clear)
        panel._on_clear_clicked()
        self.assertEqual(len(model), 0)
        self.assertEqual(panel._card_count(), 0)
        self.assertTrue(model.append(item))
        panel.deleteLater()

    def test_overlay_long_text_resizes(self):
        overlay = SubtitleOverlay(EventBus(), AppConfig())
        overlay.show()
        item = SubtitleUpdate('pinyin ' * 35, '\u4f60\u597d' * 35, 'source ' * 35)
        overlay.apply_subtitle(item)
        QTest.qWait(50)
        self.assertGreaterEqual(overlay.height(), 210)
        self.assertEqual(overlay._stack.target.text(), item.target_text)
        overlay.close()


from tests_fakes import FakeCapture, SlowEngine


class LifecycleTests(unittest.TestCase):
    def test_rapid_restart_and_shutdown_keep_ui_responsive(self):
        SlowEngine.active = SlowEngine.maximum = 0
        config = AppConfig()
        with patch('core.pipeline.LoopbackCapture', FakeCapture):
            pipeline = TranslationPipeline(config, EventBus(), SlowEngine())
            finished = []
            pipeline.shutdown_finished.connect(lambda: finished.append(True))
            pipeline.start()
            QTest.qWait(80)
            pipeline.stop_inference()
            pipeline.start_inference()
            config.quality_mode = QualityMode.FAST
            config.apply_quality()
            pipeline.apply_state(config.snapshot())
            QTest.qWait(300)
            pipeline.stop()
            for _ in range(30):
                if finished:
                    break
                QTest.qWait(30)
            self.assertTrue(finished)
            self.assertLessEqual(SlowEngine.maximum, 1)
            self.assertIsNone(pipeline._worker)
            self.assertIsNone(pipeline._capture)


if __name__ == '__main__':
    unittest.main()
