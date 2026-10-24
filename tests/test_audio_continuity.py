"""Regression checks for missing audio and context isolation, without model inference."""
import unittest
from queue import Queue, Empty
from unittest.mock import Mock, patch
import numpy as np
from audio.capture import LoopbackCapture, CapturedAudio
from core.config import AppConfig
from core.events import EventBus
from core.pipeline import InferenceWorker
from ml.whisper_engine import WhisperEngine
from ml.live_translator import LiveTranslator

class AudioContinuityTests(unittest.TestCase):
    def test_overflow_retains_sequence_gap_and_reports_loss(self):
        queue=Queue(maxsize=2)
        events=EventBus()
        lost=[]
        events.audio_dropped.connect(lost.append)
        capture=LoopbackCapture(AppConfig(),events,queue)
        samples=np.ones(640,dtype=np.float32)
        capture._push(samples)
        first=queue.get_nowait()
        for _ in range(3):
            capture._push(samples)
        self.assertEqual(first.sequence,0)
        self.assertEqual([queue.get_nowait().sequence,queue.get_nowait().sequence],[2,3])
        self.assertEqual(lost,[640])

    def test_worker_discards_partial_segment_at_sequence_gap(self):
        config=AppConfig(speech_detection=False)
        events=EventBus()
        engine=Mock()
        queue=Mock()
        queue.get_nowait.side_effect=Empty
        worker=InferenceWorker(config,events,engine,queue)
        worker.isInterruptionRequested=Mock(return_value=False)
        packets=iter([CapturedAudio(np.ones(640),1.,0),CapturedAudio(np.ones(640),1.04,1),
                      CapturedAudio(np.ones(640),1.20,5)])
        def next_chunk(**kwargs):
            try:
                return next(packets)
            except StopIteration:
                worker.isInterruptionRequested.return_value=True
                raise Empty
        queue.get.side_effect=next_chunk
        first=Mock(); first.push.return_value=None
        second=Mock(); second.push.return_value=None
        with patch('core.pipeline.SpeechSegmenter',side_effect=[first,second]) as factory:
            worker._run()
        self.assertEqual(factory.call_count,2)
        self.assertEqual(first.push.call_count,2)
        self.assertEqual(second.push.call_count,1)
        engine.reset_context.assert_called_once()
        engine.process.assert_not_called()

    def test_reset_forgets_overlap_and_dialogue_without_unloading_model(self):
        fallback=Mock(); runtime=Mock()
        translator=LiveTranslator(AppConfig(),fallback,runtime,EventBus())
        translator.remember('old conversation','en')
        engine=WhisperEngine(AppConfig(),translator)
        engine._model=Mock()
        loaded=engine._model
        engine._previous_native='old words'
        engine._previous_language='en'
        engine.set_audio_overlap(.32)
        engine.reset_context()
        self.assertEqual(list(translator.context),[])
        self.assertEqual(engine._previous_native,'')
        self.assertIsNone(engine._previous_language)
        self.assertEqual(engine._overlap_seconds,0)
        self.assertIs(engine._model,loaded)
        runtime.close.assert_not_called()
        fallback.close.assert_not_called()
