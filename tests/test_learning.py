"""Learning features stay bounded, explicit, and serialized with live inference."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,Mock
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread,Signal
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.phrasebook import Phrasebook
from core.preferences import data_dir
from core.pipeline import TranslationPipeline
from audio.replay import ReplayStore
from ml.review import ReviewWorker
from ui.learning import StudyDialog
from tests_fakes import FakeCapture,SlowEngine
APP=QApplication.instance() or QApplication([])


class ReplayTests(unittest.TestCase):
    def test_expiry_budget_and_copy_isolation(self):
        now=[0.]
        store=ReplayStore(sample_rate=10,seconds=2,clock=lambda:now[0])
        audio=np.ones(12,dtype=np.float32)
        store.add('a',audio)
        audio[:]=0
        self.assertTrue(np.all(store.get('a')==1))
        store.add('b',np.ones(12,dtype=np.float32))
        self.assertIsNone(store.get('a'))
        self.assertLessEqual(store.stats()['bytes'],80)
        now[0]=3.
        self.assertIsNone(store.get('b'))
        self.assertEqual(store.stats()['bytes'],0)

    def test_captured_audio_already_expired_is_rejected(self):
        store=ReplayStore(sample_rate=10,seconds=2,clock=lambda:10.)
        self.assertEqual(store.add('old',np.ones(10),captured_at=1.),'')


class PhrasebookTests(unittest.TestCase):
    def test_text_only_idempotent_save_delete(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            book=Phrasebook()
            update=SubtitleUpdate('pinyin','target','original',audio_id='do-not-persist',source_language='en',target_language='zh')
            saved=book.save(update,'my note')
            book.save(update,'updated note')
            items=book.items()
            self.assertEqual(len(items),1)
            self.assertEqual(items[0]['notes'],'updated note')
            self.assertNotIn('audio_id',items[0])
            self.assertNotIn('do-not-persist',(data_dir()/'phrases.json').read_text())
            self.assertEqual(list(data_dir().glob('*.wav')),[])
            book.delete(saved['id'])
            self.assertEqual(book.stats()['count'],0)

    def test_quota_failure_preserves_existing_data(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            book=Phrasebook()
            book.save(SubtitleUpdate('','a','b'))
            before=(data_dir()/'phrases.json').read_bytes()
            with patch('core.phrasebook.MAX_BYTES',20):
                with self.assertRaises(ValueError):
                    book.save(SubtitleUpdate('','c','d'))
            self.assertEqual(before,(data_dir()/'phrases.json').read_bytes())


class ReviewTests(unittest.TestCase):
    def test_text_only_worker_preserves_sentence_and_audio_identity(self):
        original=SubtitleUpdate('','old','wrong',audio_id='clip',source_language='en',target_language='zh')
        request={'update':original,'text':'Hello','source':'en','target':'zh'}
        results=[]
        with patch('ml.review.NllbTranslator') as cls:
            cls.return_value.translate.return_value='\u4f60\u597d'
            worker=ReviewWorker(AppConfig(),request)
            worker.result.connect(results.append)
            worker.run()
        result=results[0]['update']
        self.assertEqual(result.uid,original.uid)
        self.assertEqual(result.audio_id,'clip')
        self.assertEqual(result.native_text,'Hello')
        self.assertEqual(result.phonetics,'n\u01d0 h\u01ceo')
        cls.return_value.close.assert_called_once()

    def test_edit_cannot_be_saved_with_stale_translation(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            original=SubtitleUpdate('','Hello','Original',source_language='en',target_language='zh')
            dialog=StudyDialog(original,AppConfig(),EventBus(),ReplayStore(),Phrasebook())
            dialog.text.setPlainText('Corrected')
            dialog._save()
            self.assertFalse((data_dir()/'phrases.json').exists())
            self.assertIn('Translate',dialog.feedback.text())
            dialog.reject()


class FakeReview(QThread):
    result=Signal(object)
    overlap=False
    def __init__(self,config,request):
        super().__init__()
        self.request=request
    def run(self):
        type(self).overlap=SlowEngine.active>0
        self.msleep(30)
        self.result.emit({'id':self.request['update'].uid,'update':self.request['update']})


class LearningLifecycleTests(unittest.TestCase):
    def test_retranslation_waits_then_resumes_live(self):
        SlowEngine.active=SlowEngine.maximum=0
        events=EventBus()
        with patch('core.pipeline.LoopbackCapture',FakeCapture),patch('ml.review.ReviewWorker',FakeReview):
            pipeline=TranslationPipeline(AppConfig(),events,SlowEngine())
            results=[]
            events.review_finished.connect(results.append)
            pipeline.start()
            QTest.qWait(70)
            pipeline.request_review({'update':SubtitleUpdate('','target','native')})
            for _ in range(100):
                if results and pipeline._review is None:
                    break
                QTest.qWait(20)
            self.assertTrue(results)
            self.assertFalse(FakeReview.overlap)
            self.assertTrue(pipeline.inference_requested)
            finished=[]
            pipeline.shutdown_finished.connect(lambda:finished.append(True))
            pipeline.stop()
            for _ in range(100):
                if finished:
                    break
                QTest.qWait(20)
            self.assertTrue(finished)

    def test_playback_suppresses_capture_without_changing_start_stop_choice(self):
        events=EventBus()
        pipeline=TranslationPipeline(AppConfig(),events,SlowEngine())
        pipeline._want_inference=True
        pipeline._capture=Mock()
        pipeline.pause_for_replay(True)
        pipeline._capture.suppress_audio.set.assert_called_once()
        self.assertTrue(pipeline.inference_requested)
        pipeline.pause_for_replay(False)
        pipeline._capture.suppress_audio.clear.assert_called_once()
        pipeline._capture=None
        pipeline._timer.stop()

class CaptureToReplayTests(unittest.TestCase):
    def test_finalized_subtitle_is_linked_to_bounded_audio(self):
        import time
        from queue import Full
        class Capture(FakeCapture):
            def __init__(self,config,events,queue):
                super().__init__()
                self.queue=queue
            def run(self):
                self.msleep(200)
                for value in [.1]*25+[0.]*15:
                    if self.isInterruptionRequested():
                        return
                    try:
                        self.queue.put_nowait((np.full(640,value,dtype=np.float32),time.monotonic()))
                    except Full:
                        pass
                    self.msleep(2)
                while not self.isInterruptionRequested():
                    self.msleep(5)
        class Engine(SlowEngine):
            active_backend='CPU / int8'
            last_timings={'stt_ms':1.,'mt_ms':1.,'total_ms':2.}
            def ensure_loaded(self):
                pass
            def process(self,audio,target):
                return SubtitleUpdate('','target','original',source_language='en',target_language='zh')
        events=EventBus()
        with patch('core.pipeline.LoopbackCapture',Capture):
            # Synthetic constant-amplitude samples exercise plumbing, not speech VAD.
            pipeline=TranslationPipeline(AppConfig(speech_detection=False),events,Engine())
            subtitles=[]
            events.subtitle_ready.connect(subtitles.append)
            pipeline.start()
            for _ in range(100):
                if subtitles:
                    break
                QTest.qWait(20)
            self.assertTrue(subtitles)
            self.assertTrue(subtitles[0].audio_id)
            self.assertIsNotNone(pipeline.replays.get(subtitles[0].audio_id))
            self.assertLessEqual(pipeline.replays.stats()['bytes'],3840000)
            finished=[]
            pipeline.shutdown_finished.connect(lambda:finished.append(True))
            pipeline.stop()
            for _ in range(100):
                if finished:
                    break
                QTest.qWait(20)
            self.assertTrue(finished)
            self.assertEqual(pipeline.replays.stats()['bytes'],0)


if __name__=='__main__':
    unittest.main()
