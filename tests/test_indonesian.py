"""Indonesian routing, persistence and four-language automatic detection."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from core.config import AppConfig, TargetLanguage, LANGUAGE_LABELS, SOURCE_LANGUAGE_LABELS
from core.preferences import save_config, load_config
from ml.translator import NllbTranslator
from ml.whisper_engine import WhisperEngine


class IndonesianTests(unittest.TestCase):
    def test_choices_and_preferences(self):
        self.assertIn(TargetLanguage.INDONESIAN, LANGUAGE_LABELS)
        self.assertIn('id', SOURCE_LANGUAGE_LABELS)
        self.assertIn('auto_four', SOURCE_LANGUAGE_LABELS)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder, patch.dict(os.environ, GRAMMAI_DATA_DIR=folder):
            save_config(AppConfig(source_language='auto_four', target_language=TargetLanguage.INDONESIAN))
            config=load_config()
            self.assertEqual(config.source_language,'auto_four')
            self.assertEqual(config.target_language,TargetLanguage.INDONESIAN)
            save_config(AppConfig(source_language='id'))
            self.assertEqual(load_config().source_language,'id')

    def test_indonesian_detection_and_fixed_hint(self):
        engine=WhisperEngine(AppConfig(source_language='auto_four'))
        engine._model=Mock()
        engine._model.transcribe.return_value=(iter([SimpleNamespace(text='Selamat pagi')]),SimpleNamespace(language='id'))
        self.assertEqual(engine._transcribe(np.zeros(16000),'transcribe'),('Selamat pagi','id'))
        engine._model.transcribe.assert_called_once()
        self.assertIsNone(engine._model.transcribe.call_args.kwargs['language'])
        self.assertEqual(WhisperEngine(AppConfig(source_language='id'))._source_hint(),'id')

    def test_translation_uses_indonesian_tokens_in_both_directions(self):
        engine=NllbTranslator(AppConfig())
        engine._translator=Mock()
        engine._tokenizer=Mock()
        engine._tokenizer.convert_ids_to_tokens.return_value=['input']
        for source,target,src_token,tgt_token in [('en','id','eng_Latn','ind_Latn'),('id','zh','ind_Latn','zho_Hans')]:
            engine._translator.translate_batch.return_value=[SimpleNamespace(hypotheses=[[tgt_token,'output']])]
            engine._tokenizer.decode.return_value='translated'
            self.assertEqual(engine.translate('hello',source,target),'translated')
            self.assertEqual(engine._tokenizer.src_lang,src_token)
            self.assertEqual(engine._translator.translate_batch.call_args.kwargs['target_prefix'],[[tgt_token]])
