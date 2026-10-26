"""Behavioral checks for existing files, independent refinement and real model attribution."""
import os,json,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock,patch
from types import SimpleNamespace
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig,TargetLanguage
from core.events import EventBus,SubtitleUpdate
from core.components import ComponentManager,catalog
from core.preferences import load_config,save_config,write_json
from core.model_info import sentence_info,refinement_enabled
from core.history import SessionHistory
from core.live_review import LiveReview
from audio.replay import ReplayStore
from ui.learning import StudyDialog
from ui.settings import SettingsDialog
from ml.whisper_engine import WhisperEngine
from ml.live_translator import LiveTranslator
APP=QApplication.instance() or QApplication([])

class ModelTransparencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=str(self.folder/'profile'),GRAMMAI_MODELS_DIR=str(self.folder/'models'),HF_HUB_CACHE=str(self.folder/'cache'))
        self.specs=patch('core.components.catalog',return_value={key:replace(spec,assets=tuple(replace(a,size=7) for a in spec.assets)) if spec.kind!='runtime' else spec for key,spec in catalog().items()});self.specs.start()
        self.env.start();self.home=patch('pathlib.Path.home',return_value=self.folder);self.home.start()
    def tearDown(self):
        self.specs.stop();self.home.stop();self.env.stop();self.temp.cleanup()
    def dialog(self,config=None):
        with patch('ui.settings.list_audio_sources',return_value=[]):return SettingsDialog(config or AppConfig(),EventBus(),page=3)
    def cached_cpu(self,complete=True):
        spec=catalog()['speech-cpu'];folder=self.folder/'cache/models--Systran--faster-whisper-base/snapshots'/spec.version;folder.mkdir(parents=True)
        for asset in spec.assets if complete else [next(x for x in spec.assets if x.name=='model.bin')]:
            (folder/asset.name).write_bytes(b'fixture')
        return folder/'model.bin'
    def test_legacy_review_migrates_to_independent_controls_and_roundtrips(self):
        write_json('preferences.json',{'translation_mode':'review','backend':'qwen-asr','analysis_enabled':False})
        c=load_config();self.assertEqual(c.translation_mode,'fast');self.assertTrue(c.refinement_enabled);self.assertEqual(c.refinement_destination,'history');self.assertEqual(c.backend,'qwen-asr');self.assertFalse(c.analysis_enabled)
        c.refinement_destination='history_subtitles';save_config(c);self.assertEqual(load_config(),c)
    def test_existing_cache_appears_installed_without_registry_write_or_download(self):
        path=self.cached_cpu();manager=ComponentManager()
        with patch('core.components.fetch',side_effect=AssertionError('Must not download')):
            self.assertEqual(manager.path('speech-cpu'),path);self.assertEqual(manager.availability('speech-cpu'),'installed')
            d=self.dialog();i=d._speech_choice.findData('speech-cpu');self.assertEqual(d._speech_choice.itemData(i,256),'speech-cpu');d._speech_choice.setCurrentIndex(i)
            self.assertTrue(d.speech_download.isHidden());self.assertIn('Installed',d._role_detail['speech'].text());d.reject()
        self.assertFalse((self.folder/'profile/components.json').exists())
    def test_partial_cache_requires_repair_and_is_not_installed(self):
        self.cached_cpu(complete=False);manager=ComponentManager();self.assertEqual(manager.availability('speech-cpu'),'incomplete')
        from core.speech_models import installed,configure
        self.assertFalse(installed('speech-cpu',AppConfig()))
        with self.assertRaises(ValueError):configure(AppConfig(),'speech-cpu')
    def test_refinement_is_independent_of_live_translator_and_learning_toggle(self):
        config=AppConfig(analysis_enabled=False);d=self.dialog(config)
        d._refinement.setChecked(True);d._refinement_destination.setCurrentIndex(1);draft=d._draft()
        self.assertEqual(draft.translation_mode,'fast');self.assertTrue(refinement_enabled(draft));self.assertFalse(draft.analysis_enabled);self.assertEqual(draft.refinement_destination,'history_subtitles');self.assertFalse(config.refinement_enabled)
        d.reject()
    def test_live_qwen_does_not_offer_redundant_blocked_review_pass(self):
        d=self.dialog();d._refinement.setChecked(True);d._translation_mode.setCurrentIndex(d._translation_mode.findData('context'))
        self.assertFalse(d._refinement.isEnabled());self.assertFalse(d._draft(False).refinement_enabled);self.assertIn('Not needed',d._refinement_status.text());d.reject()
    def test_info_uses_result_metadata_after_settings_change_and_preserves_selection(self):
        value=SubtitleUpdate('','Meaning','Original',speech_model='Whisper large-v3-turbo',speech_backend='GPU / Vulkan',translation_model='NLLB-200 600M',translation_backend='CPU / int8')
        events=EventBus();d=StudyDialog(value,AppConfig(speech_model_id='speech-qwen'),events,ReplayStore(),Mock());d.source_display.setSelection(0,4)
        self.assertIn('Whisper large-v3-turbo',d.model_info.toolTip());self.assertNotIn('Qwen3-ASR',d.model_info.toolTip());self.assertTrue(d.review_status_label.isHidden());self.assertTrue(d.refined_icon.isHidden())
        events.review_state_changed.emit(replace(value,review_status='unchanged',refinement_model='Qwen3-4B',refinement_backend='GPU verified'))
        self.assertIn('wording kept',d.model_info.toolTip());self.assertEqual(d.source_display.selectedText(),'Orig');d.reject()
    def test_unknown_metadata_is_not_guessed_from_current_settings(self):
        info=sentence_info(SubtitleUpdate('','Meaning','Original'))
        self.assertIn('Speech: Not recorded',info);self.assertIn('Translation: Not recorded',info)
    def test_manual_edit_cannot_keep_previous_model_as_its_author(self):
        from core.revisions import revised_update
        u=SubtitleUpdate('','Before','Speech',translation_model='NLLB-200 600M',refinement_model='Qwen3-4B')
        v=revised_update(u,target_text='Manual wording')
        self.assertEqual(v.translation_model,'');self.assertEqual(v.refinement_model,'');self.assertIn('Not recorded',sentence_info(v))
    def test_same_language_and_transcript_only_do_not_claim_translation(self):
        self.assertIn('Not needed',sentence_info(SubtitleUpdate('','Hi','Hi',translation_status='same_language')))
        self.assertIn('Off (transcript only)',sentence_info(SubtitleUpdate('','Hi','Hi',translation_status='transcribed')))
    def test_whisper_audio_translation_fallback_records_actual_model(self):
        engine=WhisperEngine(AppConfig());engine.active_backend='CPU / int8';engine._transcribe=Mock(return_value=('Hello','en'))
        self.assertEqual(engine._translate('original','zh',TargetLanguage.ENGLISH,np.zeros(8)),'Hello');self.assertIn('audio translation',engine.last_translation_model);self.assertIn('Whisper',engine.last_translation_fallback)
    def test_context_failure_reports_nllb_not_qwen(self):
        runtime=Mock();runtime.complete_json.side_effect=RuntimeError('failed');fallback=Mock();fallback.translate.return_value='Meaning'
        t=LiveTranslator(AppConfig(translation_mode='context'),fallback,runtime,EventBus());self.assertEqual(t.translate('text','zh','en'),'Meaning');self.assertEqual(t.last_model,'NLLB-200 600M');self.assertIn('failed',t.last_fallback)
    def test_independent_refinement_still_uses_original_dialogue(self):
        from tests.test_translation_modes import FakeService
        config=AppConfig(translation_mode='fast',refinement_enabled=True);history=SessionHistory();service=FakeService();events=EventBus();review=LiveReview(config,events,service,history,lambda:True)
        try:
            first=SubtitleUpdate('','translated','earlier original',source_language='zh',target_language='en');history.append(first)
            current=SubtitleUpdate('','bad translation','current original',source_language='zh',target_language='en');history.append(current);review.enqueue(current)
            token,payload=service.calls[-1];self.assertEqual(payload['text'],'current original');self.assertEqual(payload['context'][0]['text'],'earlier original')
            review.completed(token,{'translation':'better translation','model':'Qwen3-4B','backend':'GPU verified'})
            updated=history.items()[-1];self.assertEqual(updated.refinement_model,'Qwen3-4B');self.assertEqual(updated.refinement_backend,'GPU verified');self.assertEqual(updated.original_target_text,'bad translation')
        finally:review.close()
    def test_same_language_speech_keeps_last_actual_translation_status(self):
        from core.pipeline import TranslationPipeline
        events=EventBus();worker=SimpleNamespace(stop_requested=False)
        fake=SimpleNamespace(sender=lambda:worker,_worker=worker,_want_inference=True,replays=Mock(),_events=events,_config=AppConfig())
        fake.replays.add.return_value='audio'
        translated=SubtitleUpdate('','meaning','speech',translation_model='NLLB-200 600M',translation_backend='CPU / int8')
        TranslationPipeline._publish(fake,translated,np.zeros(16),1.)
        TranslationPipeline._publish(fake,SubtitleUpdate('','Hi','Hi',translation_status='same_language'),np.zeros(16),2.)
        self.assertEqual(events.property('last_translation_info')['model'],'NLLB-200 600M')
    def test_overlay_history_only_and_subtitle_destination(self):
        from main import GrammAIApp
        value=SubtitleUpdate('','better','original',ai_refined=True)
        fake=SimpleNamespace(_last_update=value,_config=AppConfig(),_overlay=Mock())
        GrammAIApp._corrected_subtitle(fake,value);fake._overlay.apply_subtitle.assert_not_called()
        fake._config.refinement_destination='history_subtitles';GrammAIApp._corrected_subtitle(fake,value);fake._overlay.apply_subtitle.assert_called_once_with(value)
        fake._overlay.reset_mock();GrammAIApp._corrected_subtitle(fake,replace(value,uid='older'));fake._overlay.apply_subtitle.assert_not_called()
