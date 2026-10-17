"""Targeted CPU experiment: skip translation and retain models across replay."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.pipeline import TranslationPipeline
from core.preferences import save_config,load_config
from ml.whisper_engine import WhisperEngine
from tests_fakes import FakeCapture
APP=QApplication.instance() or QApplication([])


class TranscriptionModeTests(unittest.TestCase):
    def test_translation_model_is_not_loaded_or_called(self):
        translator=Mock()
        config=AppConfig(translation_enabled=False)
        engine=WhisperEngine(config,translator)
        engine._transcribe=Mock(return_value=('Hello, world.','en'))
        engine.ensure_translator()
        result=engine.process(np.zeros(16000),config.target_language)
        translator.ensure_loaded.assert_not_called()
        translator.translate.assert_not_called()
        self.assertEqual(result.translation_status,'transcribed')
        self.assertEqual(result.target_text,'Hello, world.')
        self.assertEqual(result.target_language,'en')
        self.assertEqual(engine.last_timings['mt_ms'],0.)
        self.assertEqual(engine._transcribe.call_count,1)

    def test_preference_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            save_config(AppConfig(translation_enabled=False,source_language='th'))
            config=load_config()
            self.assertFalse(config.translation_enabled)
            self.assertEqual(config.source_language,'th')

    def test_replay_reuses_worker_and_models_until_shutdown(self):
        class Engine:
            active_backend='CPU / int8'
            def __init__(self):
                self.loads=0
                self.closes=0
            def configure(self,config):
                pass
            def ensure_loaded(self):
                self.loads+=1
            def ensure_translator(self):
                pass
            def close(self):
                self.closes+=1
        engine=Engine()
        with patch('core.pipeline.LoopbackCapture',FakeCapture):
            pipeline=TranslationPipeline(AppConfig(speech_detection=False),EventBus(),engine)
            pipeline.start()
            for _ in range(100):
                if pipeline.processing_live:
                    break
                QTest.qWait(20)
            original=pipeline._worker
            self.assertIsNotNone(original)
            pipeline.pause_for_replay(True)
            QTest.qWait(150)
            self.assertIs(pipeline._worker,original)
            self.assertTrue(original.isRunning())
            self.assertEqual(engine.closes,0)
            self.assertEqual(engine.loads,1)
            pipeline.pause_for_replay(False)
            QTest.qWait(150)
            self.assertIs(pipeline._worker,original)
            self.assertEqual(engine.loads,1)
            finished=[]
            pipeline.shutdown_finished.connect(lambda:finished.append(True))
            pipeline.stop()
            for _ in range(100):
                if finished:
                    break
                QTest.qWait(20)
            self.assertTrue(finished)
            self.assertEqual(engine.closes,1)


if __name__=='__main__':
    unittest.main()
