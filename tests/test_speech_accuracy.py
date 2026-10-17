"""Speech boundary, overlap, vocabulary, and benchmark normalization checks."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import importlib.util
import numpy as np
from audio.segmentation import SpeechSegmenter,StreamingSpeechDetector
from core.config import AppConfig,TargetLanguage
from ml.transcript import trim_overlap
from ml.whisper_engine import WhisperEngine


class SpeechAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.config=AppConfig(speech_max_seconds=2.,speech_silence_seconds=.4)
        self.speech=np.full(640,.1,dtype=np.float32)
        self.quiet=np.zeros(640,dtype=np.float32)

    def test_loud_non_speech_does_not_trigger_vad_segmenter(self):
        segmenter=SpeechSegmenter(self.config,lambda chunk:0.)
        for _ in range(100):
            self.assertIsNone(segmenter.push(self.speech))

    def test_quiet_syllables_are_kept_after_speech_onset(self):
        detector=Mock(return_value=.9)
        segmenter=SpeechSegmenter(self.config,detector)
        for _ in range(5):
            segmenter.push(self.speech)
        soft=np.full(640,.0001,dtype=np.float32)
        for _ in range(15):
            self.assertIsNone(segmenter.push(soft))
        detector.return_value=0.
        output=None
        for _ in range(10):
            output=segmenter.push(self.quiet)
        self.assertIsNotNone(output)
        self.assertEqual(np.count_nonzero(output==np.float32(.0001)),15*640)

    def test_short_reply_survives_minimum_duration(self):
        detector=Mock(return_value=.9)
        segmenter=SpeechSegmenter(self.config,detector)
        for _ in range(4):
            segmenter.push(self.speech)
        detector.return_value=0.
        output=None
        for _ in range(10):
            output=segmenter.push(self.quiet)
        self.assertIsNotNone(output)

    def test_forced_cut_preserves_overlap_but_never_replays_carry_alone(self):
        detector=Mock(return_value=.9)
        segmenter=SpeechSegmenter(self.config,detector)
        first=None
        for _ in range(50):
            first=segmenter.push(self.speech)
        self.assertIsNotNone(first)
        self.assertEqual(segmenter.last_overlap_samples,0)
        overlap=round(16000*self.config.speech_overlap_seconds)
        for _ in range(5):
            segmenter.push(self.speech)
        detector.return_value=0.
        second=None
        for _ in range(10):
            second=segmenter.push(self.quiet)
        self.assertEqual(segmenter.last_overlap_samples,overlap)
        np.testing.assert_array_equal(first[-overlap:],second[:overlap])
        segmenter=SpeechSegmenter(self.config,detector)
        detector.return_value=.9
        for _ in range(50):
            segmenter.push(self.speech)
        detector.return_value=0.
        for _ in range(15):
            self.assertIsNone(segmenter.push(self.quiet))

    def test_overlap_dedup_is_conservative_and_never_affects_independent_replies(self):
        self.assertEqual(trim_overlap('我们今天去公园','去公园散步吧',.32),'散步吧')
        self.assertEqual(trim_overlap('对对','对对',.32),'对对')
        self.assertEqual(trim_overlap('我们今天去公园','去公园散步吧',0),'去公园散步吧')
        self.assertEqual(trim_overlap('we can go home','go home and rest',.32),'and rest')

    def test_lingering_vad_probability_does_not_turn_carry_into_fresh_speech(self):
        detector=Mock(return_value=.9)
        segmenter=SpeechSegmenter(self.config,detector)
        for _ in range(50):
            segmenter.push(self.speech)
        for _ in range(60):
            self.assertIsNone(segmenter.push(self.quiet))

    def test_overlap_is_removed_before_translation(self):
        translator=Mock()
        translator.translate.return_value='translation'
        engine=WhisperEngine(self.config,translator)
        engine._transcribe=Mock(side_effect=[('我们今天去公园','zh'),('去公园散步吧','zh')])
        engine.process(np.zeros(16000),TargetLanguage.ENGLISH)
        engine.set_audio_overlap(.32)
        result=engine.process(np.zeros(16000),TargetLanguage.ENGLISH)
        self.assertEqual(result.native_text,'散步吧')
        self.assertEqual(translator.translate.call_args.args[0],'散步吧')

    def test_vocabulary_hint_reaches_recognizer(self):
        config=AppConfig(source_language='zh',speech_prompt='简体中文，王小明。')
        engine=WhisperEngine(config)
        engine._model=Mock()
        engine._model.transcribe.return_value=(iter([SimpleNamespace(text='王小明')]),SimpleNamespace(language='zh'))
        engine._transcribe(np.zeros(16000),'transcribe')
        self.assertEqual(engine._model.transcribe.call_args.kwargs['initial_prompt'],config.speech_prompt)

    def test_real_bundled_vad_is_bounded_and_rejects_silence(self):
        detector=StreamingSpeechDetector()
        for _ in range(25):
            self.assertLess(detector(self.quiet),.5)
            self.assertLess(detector.pending.size,512)
        detector.reset()
        self.assertEqual(detector.probability,0)

    @unittest.skipUnless(importlib.util.find_spec('opencc'),'optional benchmark normalization')
    def test_mandarin_scoring_does_not_confuse_script_with_recognition(self):
        from scripts.benchmark_speech import character_errors
        self.assertEqual(character_errors('台湾天气很好。','臺灣天氣很好！')[0],0)
        self.assertGreater(character_errors('台湾天气很好。','臺灣天氣很好！',False)[0],0)
