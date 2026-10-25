"""Translation routing, bounded automatic reviews and compact history behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,unittest
from dataclasses import replace
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication,QPushButton,QLabel
from core.config import AppConfig,TargetLanguage
from core.events import EventBus,SubtitleUpdate
from core.history import SessionHistory
from core.analysis import AnalysisService
from core.live_review import LiveReview
from ml.live_translator import LiveTranslator
from ml.qwen_translator import translation_body
from ui.history import HistoryPanel,HistoryCard
from ui.learning import StudyDialog
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])
class FakeService(QObject):
    translation_completed=Signal(str,object)
    def __init__(self):super().__init__();self.busy=False;self.calls=[];self.cancelled=[]
    def refine(self,token,config,payload):self.calls.append((token,payload));return True
    def cancel(self,token):self.cancelled.append(token)
class TranslationModeTests(unittest.TestCase):
    def test_context_is_bounded_original_dialogue_only(self):
        body=translation_body('current','en','id',[{'text':'x'*500,'language':'zh','translation':'must not leak'} for _ in range(6)])
        payload=json.loads(body['messages'][1]['content'])
        self.assertEqual(len(payload['earlier_original_dialogue']),3)
        self.assertTrue(all(len(x['text'])==240 for x in payload['earlier_original_dialogue']))
        self.assertNotIn('must not leak',json.dumps(body));self.assertEqual(payload['text'],'current')
    def test_fast_path_never_loads_qwen(self):
        fallback=Mock();runtime=Mock();translator=LiveTranslator(AppConfig(),fallback,runtime,EventBus())
        translator.ensure_loaded();translator.translate('hello','en','id');translator.close()
        runtime.ensure_loaded.assert_not_called();runtime.close.assert_not_called();fallback.translate.assert_called_once_with('hello','en','id')
    def test_context_route_falls_back_once_until_restart(self):
        fallback=Mock();fallback.translate.return_value='fallback';runtime=Mock();runtime.complete_json.side_effect=RuntimeError('failed')
        translator=LiveTranslator(AppConfig(translation_mode='context'),fallback,runtime,EventBus());translator.ensure_loaded()
        self.assertEqual(translator.translate('hello','en','id'),'fallback');self.assertEqual(translator.translate('again','en','id'),'fallback')
        self.assertEqual(runtime.complete_json.call_count,1);translator.close();runtime.close.assert_called_once();self.assertEqual(list(translator.context),[])
    def test_cancel_does_not_start_fallback(self):
        fallback=Mock();runtime=Mock();runtime.complete_json.side_effect=InterruptedError()
        translator=LiveTranslator(AppConfig(translation_mode='context'),fallback,runtime,EventBus())
        with self.assertRaises(InterruptedError):translator.translate('hello','en','id')
        fallback.translate.assert_not_called()
    def test_service_never_touches_runtime_while_live_translation_owns_it(self):
        events=EventBus();events.setProperty('local_translation_owned',True)
        service=AnalysisService(events=events,config=AppConfig());service.runtime=Mock(loaded=True,last_used=0)
        self.assertFalse(service.manage('unload',AppConfig()));self.assertFalse(service.request('manual',AppConfig(),{}));self.assertFalse(service.refine('review',AppConfig(),{}))
        service._idle_unload();service.shutdown();service.runtime.close.assert_not_called();service.timer.stop()
    def test_pipeline_waits_for_analysis_before_leasing_runtime(self):
        from core.pipeline import TranslationPipeline
        events=EventBus();events.analysis_service=Mock(busy=True);pipeline=TranslationPipeline(AppConfig(translation_mode='context'),events,Mock());pipeline._want_inference=True
        with patch('core.pipeline.InferenceWorker') as worker:
            pipeline._reconcile();worker.assert_not_called();events.analysis_service.busy=False;pipeline._reconcile();worker.return_value.start.assert_called_once()
            self.assertTrue(events.property('local_translation_owned'));pipeline._want_inference=False;worker.return_value.isFinished.return_value=True;worker.return_value.stop_requested=True;pipeline._reconcile();self.assertFalse(events.property('local_translation_owned'))
        pipeline._timer.stop()
    def test_automatic_revision_details_preserve_first_translation_without_apply(self):
        from core.revisions import revised_update
        update=SubtitleUpdate('', 'Old translation','original speech',source_language='en',target_language='id')
        value=revised_update(update,target_text='Better translation');dialog=StudyDialog(value,AppConfig(),EventBus(),ReplayStore(),Mock())
        self.assertEqual(dialog.translation_display.text(),'Better translation');self.assertEqual(dialog.subtitle.original_target_text,'Old translation');self.assertEqual(dialog.subtitle.native_text,'original speech')
        self.assertFalse(any(b.text() in ('Use suggestion','Dismiss') for b in dialog.findChildren(QPushButton)))
        self.assertIn('Old translation',dialog.comparison.toPlainText());dialog.reject()
    def test_settings_mode_survives_draft_and_advanced_starts_hidden(self):
        from ui.settings import SettingsDialog
        with patch('ui.settings.list_audio_sources',return_value=[]):dialog=SettingsDialog(AppConfig(),EventBus())
        dialog._refinement.setChecked(True);self.assertEqual(dialog._draft().translation_mode,'fast');self.assertTrue(dialog._draft().refinement_enabled);self.assertEqual(dialog.tabs.tabText(1),'Languages');self.assertEqual(dialog.tabs.tabText(5),'Understanding');dialog.reject()
    def test_compact_history_keeps_original_pronunciation_and_copyable_translation(self):
        update=SubtitleUpdate('', 'I will buy food first.','original speech',native_phonetics='pronunciation',source_language='zh',target_language='en')
        card=HistoryCard(update);original=card.findChild(QLabel,'originalSpeech');target=card.findChild(QLabel,'target')
        self.assertEqual(original.text(),update.native_text);self.assertEqual(card.findChild(QLabel,'phonetic').text(),update.native_phonetics)
        target.copy();self.assertEqual(APP.clipboard().text(),update.target_text);self.assertEqual(card.details_button.text(),'');self.assertEqual(card.details_button.accessibleName(),'Understand this sentence')
        selected=[];card.explain_requested.connect(selected.append);original.explain_handler('original');self.assertEqual(selected[0]['text_role'],'original');self.assertEqual(selected[0]['language'],'zh');card.close()
    def test_history_without_suggestion_does_not_add_preview(self):
        from ui.history import SuggestionPreview
        card=HistoryCard(SubtitleUpdate('', 'normal translation','original'));self.assertIsNone(card.findChild(SuggestionPreview));card.close()
    def test_history_search_uses_original_and_language(self):
        panel=HistoryPanel();panel.append(SubtitleUpdate('', 'Rice','original A',source_language='zh'));panel.append(SubtitleUpdate('', 'Bread','original B',source_language='en'))
        panel.search.setText('original');panel.language_filter.setCurrentIndex(panel.language_filter.findData('zh'));cards=panel.findChildren(HistoryCard)
        self.assertEqual([c.subtitle.source_language for c in cards if not c.isHidden()],['zh']);panel.search.setText('missing');self.assertTrue(all(c.isHidden() for c in cards));self.assertEqual(panel._empty.text(),'No matching sentences.');panel.close()
class LiveReviewTests(unittest.TestCase):
    def setUp(self):
        self.config=AppConfig(translation_mode='review',target_language=TargetLanguage.ENGLISH);self.events=EventBus();self.service=FakeService();self.history=SessionHistory();self.review=LiveReview(self.config,self.events,self.service,self.history,lambda:True);self.results=[];self.events.subtitle_corrected.connect(self.results.append)
    def tearDown(self):self.review.close()
    def add(self,text):
        update=SubtitleUpdate('',text+' translated',text,source_language='id',target_language='en');self.history.append(update);self.review.enqueue(update);return update
    def test_only_latest_pending_sentence_is_kept(self):
        first=self.add('one');self.add('two');last=self.add('three');self.assertEqual(len(self.service.calls),1);token=self.service.calls[0][0];self.review.completed(token,{'translation':'new version'})
        self.assertEqual(self.results[0].target_text,'new version');self.assertEqual(self.results[0].original_target_text,first.target_text);self.assertEqual(self.results[0].native_text,first.native_text);self.assertEqual(self.results[0].revision_count,1)
        self.review.pump();self.assertEqual(self.service.calls[-1][1]['text'],last.native_text);self.assertEqual(len(self.service.calls),2)
    def test_late_results_after_clear_or_edits_are_ignored(self):
        original=self.add('one');token=self.service.calls[0][0];self.history.replace(replace(original,target_text='manual change'));self.review.completed(token,{'translation':'stale'});self.assertEqual(self.results,[])
        self.add('two');token=self.service.calls[-1][0];self.history.clear();self.review.completed(token,{'translation':'stale'});self.assertEqual(self.results,[])
    def test_errors_back_off_and_mode_change_cancels(self):
        self.add('one');token=self.service.calls[0][0];self.review.completed(token,{'error':'unavailable'});self.add('two');self.assertEqual(len(self.service.calls),1)
        self.review.retry_after=0;self.review.pump();self.config.translation_mode='fast';self.review.reset_if_changed(None);self.assertTrue(self.service.cancelled);self.assertIsNone(self.review.pending)
