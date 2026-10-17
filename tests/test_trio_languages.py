"""Restricted auto detection uses one decoder for ordinary trio speech."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from core.config import AppConfig, SOURCE_LANGUAGE_LABELS
from core.preferences import load_config, save_config
from ml.whisper_engine import WhisperEngine


class TrioLanguageTests(unittest.TestCase):
    def test_supported_languages_do_not_retry(self):
        engine = WhisperEngine(AppConfig(source_language="auto_trio"))
        engine._model = Mock()
        for code in ("en", "zh", "th"):
            with self.subTest(language=code):
                engine._model.reset_mock()
                engine._model.transcribe.return_value = (
                    iter([SimpleNamespace(text=" sentence ")]), SimpleNamespace(language=code))
                self.assertEqual(engine._transcribe(np.zeros(16000), "transcribe"), ("sentence", code))
                engine._model.transcribe.assert_called_once()
                self.assertIsNone(engine._model.transcribe.call_args.kwargs["language"])

    def test_outside_detection_chooses_best_allowed_before_decoding(self):
        engine = WhisperEngine(AppConfig(source_language="auto_trio"))
        engine._model = Mock()
        discarded = Mock()
        engine._model.transcribe.side_effect = [
            (discarded, SimpleNamespace(language="ja", all_language_probs=[("ja", .6), ("th", .3), ("en", .1)])),
            (iter([SimpleNamespace(text="Thai sentence")]), SimpleNamespace(language="th")),
        ]
        self.assertEqual(engine._transcribe(np.zeros(16000), "transcribe"), ("Thai sentence", "th"))
        self.assertEqual(engine._model.transcribe.call_args.kwargs["language"], "th")
        discarded.assert_not_called()

    def test_fixed_and_general_modes_are_preserved(self):
        for code, hint in (("auto", None), ("en", "en"), ("zh", "zh"), ("th", "th")):
            self.assertEqual(WhisperEngine(AppConfig(source_language=code))._source_hint(), hint)

    def test_preference_roundtrip(self):
        self.assertIn("auto_trio", SOURCE_LANGUAGE_LABELS)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder, patch.dict(os.environ, GRAMMAI_DATA_DIR=folder):
            save_config(AppConfig(source_language="auto_trio"))
            self.assertEqual(load_config().source_language, "auto_trio")
