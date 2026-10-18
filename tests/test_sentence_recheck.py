"""Revisions preserve evidence; only manual rechecks spend inference work."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from core.config import AppConfig
from core.events import EventBus, SubtitleUpdate
from core.revisions import revised_update, revision_label
from core.analysis import AnalysisService
from core.pipeline import TranslationPipeline
from audio.replay import ReplayStore
from audio.segmentation import SpeechSegmenter
from ml.review import ReviewWorker
from ui.history import HistoryCard
from ui.learning import StudyDialog

APP = QApplication.instance() or QApplication([])


class RevisionTests(unittest.TestCase):
    def test_first_version_survives_multiple_revisions_and_noop(self):
        first=SubtitleUpdate('', 'first translation', 'first transcript', audio_id='clip')
        second=revised_update(first, native_text='corrected', target_text='revised')
        third=revised_update(second, target_text='revised again')
        self.assertEqual(third.original_native_text,first.native_text)
        self.assertEqual(third.original_target_text,first.target_text)
        self.assertEqual(third.revision_count,2)
        self.assertEqual(third.uid,first.uid)
        self.assertEqual(third.audio_id,'clip')
        self.assertEqual(revised_update(third,target_text=third.target_text),third)
        self.assertEqual(revision_label(first),'')
        self.assertIn('Transcript corrected',revision_label(third))

    def test_translation_only_badge_and_single_details_action(self):
        first=SubtitleUpdate('', 'old', 'source')
        update=revised_update(first,target_text='new')
        card=HistoryCard(update)
        self.assertEqual(revision_label(update),'Translation revised')
        self.assertEqual([b.accessibleName() for b in card.findChildren(QPushButton)],['Understand this sentence'])
        self.assertEqual(card.findChild(QLabel,'revisionBadge').accessibleName(),'Translation revised')
        events=EventBus()
        dialog=StudyDialog(update,AppConfig(),events,ReplayStore(),Mock())
        self.assertIn('first translation',dialog.original.toPlainText().lower())
        self.assertIn('old',dialog.original.toPlainText())
        self.assertFalse(dialog.save.isEnabled())
        self.assertFalse(dialog.reviewed.isChecked())
        dialog.reject()
        card.deleteLater()


class RecheckTests(unittest.TestCase):
    def execute(self, request):
        results=[]
        worker=ReviewWorker(AppConfig(),request)
        worker.result.connect(results.append)
        worker.run()
        return results[0]

    def test_audio_recheck_then_translation_preserves_first_version(self):
        original=SubtitleUpdate('', 'old', 'wrong',source_language='zh',target_language='en')
        with patch('ml.whisper_engine.WhisperEngine') as engine,patch('ml.review.NllbTranslator') as translator:
            engine.return_value._transcribe.return_value=('correct','zh')
            translator.return_value.translate.return_value='new translation'
            result=self.execute(dict(update=original,text='wrong',source='zh',target='en',recheck=True,audio=np.ones(16000,dtype=np.float32)))
            self.assertEqual(result['mode'],'audio')
            self.assertEqual(result['update'].original_native_text,'wrong')
            self.assertEqual(translator.return_value.translate.call_args.args[0],'correct')
            self.assertEqual(engine.call_args.args[0].source_language,'zh')
            engine.return_value.close.assert_called_once()

    def test_expired_audio_uses_text_only_and_noop_has_no_badge(self):
        original=SubtitleUpdate('', 'translation', 'source',source_language='en',target_language='id')
        with patch('ml.whisper_engine.WhisperEngine') as engine,patch('ml.review.NllbTranslator') as translator:
            translator.return_value.translate.return_value='translation'
            result=self.execute(dict(update=original,text='source',source='en',target='id',recheck=True,audio=None))
            engine.assert_not_called()
            self.assertEqual(result['mode'],'text')
            self.assertEqual(result['update'].revision_count,0)

    def test_recheck_failure_leaves_original_untouched_and_closes_model(self):
        original=SubtitleUpdate('', 'old', 'source')
        with patch('ml.whisper_engine.WhisperEngine') as engine,patch('ml.review.NllbTranslator'):
            engine.return_value._transcribe.side_effect=RuntimeError('failed')
            result=self.execute(dict(update=original,text='source',source='en',target='id',recheck=True,audio=np.ones(16000)))
            self.assertIn('error',result)
            self.assertNotIn('update',result)
            self.assertEqual(original.revision_count,0)
            engine.return_value.close.assert_called_once()

    def test_context_analysis_cannot_start_during_recheck(self):
        events=EventBus()
        service=AnalysisService(events=events)
        events.setProperty('review_busy',True)
        self.assertFalse(service.request('token',AppConfig(),{}))
        self.assertFalse(service.manage('load',AppConfig()))
        service.shutdown()

    def test_suggestion_requires_apply_and_preserves_original(self):
        events=EventBus()
        first=SubtitleUpdate('', 'old translation', 'old transcript',source_language='en',target_language='id')
        proposal=revised_update(first,native_text='correct transcript',target_text='new translation')
        dialog=StudyDialog(first,AppConfig(),events,ReplayStore(),Mock())
        changed=[]
        events.subtitle_corrected.connect(changed.append)
        dialog._finished(dict(id=first.uid,update=proposal,mode='audio',requires_confirmation=True))
        self.assertEqual(changed,[])
        self.assertEqual(dialog.subtitle,first)
        self.assertFalse(dialog.apply_recheck.isHidden())
        self.assertIn('old transcript',dialog.original.toPlainText())
        dialog._apply_recheck()
        self.assertEqual(changed,[proposal])
        self.assertEqual(dialog.subtitle.original_native_text,'old transcript')
        dialog.reject()

    def test_edited_suggestion_cannot_apply_stale_translation(self):
        first=SubtitleUpdate('', 'old', 'source',source_language='en',target_language='id')
        dialog=StudyDialog(first,AppConfig(),EventBus(),ReplayStore(),Mock())
        dialog._finished(dict(id=first.uid,update=revised_update(first,target_text='new'),requires_confirmation=True))
        dialog.text.setPlainText('a different sentence')
        dialog._apply_recheck()
        self.assertEqual(dialog.subtitle,first)
        self.assertIn('changed',dialog.feedback.text())
        dialog.reject()

    def test_pipeline_does_not_publish_unaccepted_recheck(self):
        events=EventBus()
        pipeline=TranslationPipeline(AppConfig(),events,Mock())
        changed=[]
        events.subtitle_corrected.connect(changed.append)
        pipeline._review_result(dict(update=SubtitleUpdate('', 'new', 'source'),requires_confirmation=True))
        self.assertEqual(changed,[])
        pipeline._timer.stop()

    def test_audio_is_snapshotted_before_expiry_and_only_one_review_accepted(self):
        events=EventBus()
        pipeline=TranslationPipeline(AppConfig(),events,Mock())
        first=SubtitleUpdate('', 'old', 'source',audio_id='clip')
        pipeline.replays.add('clip',np.ones(16000,dtype=np.float32))
        pipeline.request_review(dict(update=first,recheck=True))
        pending=pipeline._review_pending
        pipeline.replays.clear()
        self.assertEqual(pending['audio'].size,16000)
        pipeline.request_review(dict(update=first,recheck=True))
        self.assertIs(pipeline._review_pending,pending)
        pipeline._timer.stop()

    def test_analysis_result_also_records_first_wording(self):
        from tests.test_source_analysis import RESULT
        service=AnalysisService()
        service.request=Mock(return_value=True)
        first=SubtitleUpdate('', 'old', 'original',source_language='en',target_language='id')
        dialog=StudyDialog(first,AppConfig(analysis_enabled=True),EventBus(),ReplayStore(),Mock(),analysis=service)
        widget=dialog.analysis_widget
        widget._run()
        widget._finished(widget.token,RESULT)
        widget._apply()
        self.assertEqual(dialog.subtitle.original_target_text,'old')
        self.assertEqual(dialog.subtitle.original_native_text,'original')
        self.assertEqual(dialog.subtitle.revision_count,1)
        dialog.reject()
        service.shutdown()

    def test_endpoint_grace_keeps_short_tail_with_long_phrase(self):
        config=AppConfig(speech_max_seconds=4.,speech_silence_seconds=.4)
        detector=Mock(return_value=.9)
        segmenter=SpeechSegmenter(config,detector)
        speech=np.full(640,.1,dtype=np.float32)
        for _ in range(105):
            self.assertIsNone(segmenter.push(speech))
        detector.return_value=0.
        result=None
        for _ in range(10):
            result=segmenter.push(np.zeros(640,dtype=np.float32))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(len(result)/16000,4.6)
        # Continuous speech still has a bounded hard cut.
        detector.return_value=.9
        segmenter=SpeechSegmenter(config,detector)
        for _ in range(119):
            self.assertIsNone(segmenter.push(speech))
        self.assertIsNotNone(segmenter.push(speech))


if __name__=='__main__':
    unittest.main()
