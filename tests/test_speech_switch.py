"""Model icons, downloads, transactional switching and independent text translation."""
import os,tempfile,unittest,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.pipeline import TranslationPipeline
from core.speech_models import installed,configure,components
from ml.whisper_engine import WhisperEngine
APP=QApplication.instance() or QApplication([])

def settle(predicate):
 for _ in range(400):
  if predicate():return
  QTest.qWait(10)
 raise AssertionError('Timed out waiting for model task')

class SwitchEngine:
 def __init__(self):self.loaded=False;self.loads=[];self.config=None;self.fail=False
 def configure(self,config):self.config=config
 def ensure_loaded(self,**kwargs):
  assert not self.loaded,'Two speech models loaded together'
  self.loads.append(self.config.speech_model_id)
  if self.fail:raise RuntimeError('candidate cannot load')
  self.loaded=True
 def _transcribe(self,audio,task):return 'The meeting starts at three in the afternoon.','en'
 def close(self):self.loaded=False

class SpeechSwitchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
  self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start();self.pipeline=None
 def tearDown(self):
  if self.pipeline:
   self.pipeline.stop();settle(lambda:self.pipeline._switch is None);self.pipeline._timer.stop()
  self.env.stop();self.temp.cleanup()
 def file(self,name):
  p=self.folder/name;p.touch();return p
 def test_all_models_have_independent_components(self):
  self.assertEqual(components('speech-qwen'),('speech-qwen','qwen-asr-runtime'))
  self.assertEqual(components('speech-large'),('speech-large','speech-runtime'))
  c=AppConfig(analysis_gguf='original-text.gguf',translation_mode='context')
  with patch('core.components.resolve',side_effect=lambda key:self.file(key)):
   draft=configure(c,'speech-qwen')
  self.assertEqual(draft.backend,'qwen-asr');self.assertEqual(draft.analysis_gguf,c.analysis_gguf);self.assertEqual(draft.translation_mode,c.translation_mode)
 def test_missing_runtime_is_not_installed_and_cannot_be_saved(self):
  with patch('core.components.resolve',side_effect=lambda key:self.file('qwen.gguf') if key=='speech-qwen' else None):
   self.assertFalse(installed('speech-qwen'))
   with self.assertRaises(ValueError):configure(AppConfig(),'speech-qwen')
 def test_picker_icons_update_without_rebuilding_unchanged_popup(self):
  from ui.speech_models import SpeechModelCombo
  available={'speech-turbo':True}
  with patch('ui.speech_models.installed',side_effect=lambda key,c:available.get(key,False)):
   combo=SpeechModelCombo(AppConfig());q=combo.findData('speech-qwen');old=combo.model().item(q)
   self.assertFalse(combo.itemIcon(q).isNull());self.assertIn('Not downloaded',combo.itemData(q,Qt.ItemDataRole.AccessibleDescriptionRole))
   combo.refresh();self.assertIs(combo.model().item(q),old)
   combo.setCurrentIndex(q);available['speech-qwen']=True;combo.refresh();q=combo.findData('speech-qwen')
   self.assertEqual(combo.currentData(),'speech-qwen');self.assertIn('Installed',combo.itemData(q,Qt.ItemDataRole.AccessibleDescriptionRole))
   combo.running_id='speech-qwen';combo.refresh();self.assertIn('Running',combo.currentText());combo.close()
 def pipeline_case(self,fail=False):
  c=AppConfig(speech_model_id='speech-turbo',analysis_gguf='keep-text-model.gguf');e=EventBus();engine=SwitchEngine();engine.fail=fail
  self.pipeline=TranslationPipeline(c,e,engine);results=[];e.speech_switch_finished.connect(results.append)
  self.pipeline.request_speech_switch({'token':'switch','config':replace(c,speech_model_id='speech-qwen',backend='qwen-asr')})
  self.assertEqual(c.speech_model_id,'speech-turbo');settle(lambda:bool(results));return c,e,engine,results[0]
 def test_switch_commits_only_after_candidate_test(self):
  c,e,engine,result=self.pipeline_case();self.assertEqual(c.speech_model_id,'speech-qwen');self.assertNotIn('error',result)
  self.assertFalse(engine.loaded,'An idle app should not retain a tested speech model');self.assertEqual(c.analysis_gguf,'keep-text-model.gguf')
 def test_failed_switch_retains_previous_selection(self):
  c,e,engine,result=self.pipeline_case(True);self.assertEqual(c.speech_model_id,'speech-turbo');self.assertIn('candidate cannot load',result['error']);self.assertFalse(e.property('speech_switch_busy'))
 def test_switch_waits_for_previous_worker_to_release_engine(self):
  c=AppConfig();e=EventBus();engine=SwitchEngine();self.pipeline=TranslationPipeline(c,e,engine)
  old=Mock(stop_requested=True);old.isFinished.return_value=False;self.pipeline._worker=old
  self.pipeline.request_speech_switch({'token':'wait','config':replace(c,speech_model_id='speech-qwen')})
  self.pipeline._reconcile();self.assertEqual(engine.loads,[]);old.stop.assert_called_once()
  old.isFinished.return_value=True;settle(lambda:self.pipeline._switch is None and self.pipeline._switch_pending is None)
  self.assertEqual(engine.loads,['speech-qwen'])
 def test_download_is_explicit_and_can_run_while_whisper_listens(self):
  from ui.settings import SettingsDialog
  e=EventBus();e.setProperty('translation_running',True)
  with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsDialog(AppConfig(),e,page=3)
  d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-qwen'))
  with patch.object(d.speech_task,'start_job',return_value=True) as start:
   d._download_speech();start.assert_called_once();self.assertFalse(start.call_args.kwargs['requires_idle'])
  d.reject()
 def test_qwen_never_routes_audio_into_whisper_translation_fallback(self):
  from core.config import TargetLanguage
  engine=WhisperEngine(AppConfig(speech_model_id='speech-qwen'));engine._transcribe=Mock(side_effect=AssertionError('Unsupported audio translation'))
  self.assertEqual(engine._translate('hello','zh',TargetLanguage.ENGLISH,np.zeros(10)), '')
 def test_qwen_backend_runs_one_resident_runtime_and_preserves_text_model(self):
  c=AppConfig(speech_model_id='speech-qwen',processing_mode='gpu',analysis_gguf='keep.gguf')
  with patch('ml.qwen_asr.QwenASR') as runtime:
   engine=WhisperEngine(c);engine.ensure_loaded();engine.ensure_loaded();runtime.assert_called_once();runtime.return_value.start.assert_called_once();engine.close()
 def test_full_whisper_uses_existing_vulkan_backend(self):
  c=AppConfig(speech_model_id='speech-large',processing_mode='gpu')
  with patch('core.speech_models.paths',return_value={'speech-runtime':self.file('server.exe'),'speech-large':self.file('full.bin')}),patch('ml.vulkan_engine.VulkanWhisper') as runtime:
   engine=WhisperEngine(c);engine.ensure_loaded();self.assertEqual(runtime.call_args.args[0].vulkan_model,str(self.folder/'full.bin'));engine.close()

 def test_settings_waits_for_switch_and_updates_baseline_after_success(self):
  from ui.settings import SettingsPage
  config=AppConfig();events=EventBus();engine=SwitchEngine();self.pipeline=TranslationPipeline(config,events,engine)
  with patch('ui.settings.list_audio_sources',return_value=[]),patch('core.components.resolve',side_effect=lambda key:self.file(key)):
   d=SettingsPage(config,events,page=3);d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-qwen'))
   self.assertFalse(d.apply());self.assertEqual(config.speech_model_id,'external');self.assertFalse(d.tabs.isEnabled())
   settle(lambda:d._pending_switch is None)
   self.assertTrue(d.tabs.isEnabled());self.assertEqual(config.speech_model_id,'speech-qwen');self.assertEqual(d._baseline.speech_model_id,'speech-qwen');d.dispose();d.close()
 def test_failed_settings_switch_keeps_original_and_allows_retry(self):
  from ui.settings import SettingsPage
  config=AppConfig();events=EventBus();engine=SwitchEngine();engine.fail=True;self.pipeline=TranslationPipeline(config,events,engine)
  with patch('ui.settings.list_audio_sources',return_value=[]),patch('core.components.resolve',side_effect=lambda key:self.file(key)):
   d=SettingsPage(config,events,page=3);d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-qwen'));d.apply()
   settle(lambda:d._pending_switch is None);self.assertEqual(config.speech_model_id,'external');self.assertTrue(d.save_changes.isEnabled());self.assertIn('Previous speech model kept',d._feedback.text());d.dispose();d.close()
 def test_qwen_gpu_status_requires_both_backend_and_successful_model_load(self):
  from ml.qwen_asr import QwenASR
  self.assertFalse(QwenASR.gpu_allocated('Vulkan0: AMD GPU detected'))
  self.assertFalse(QwenASR.gpu_allocated('using preferred GPU backend: Vulkan0'))
  self.assertTrue(QwenASR.gpu_allocated('using preferred GPU backend: Vulkan0\nqwen3_asr: loaded model.gguf'))
 def test_component_catalog_pins_new_assets_with_full_integrity_metadata(self):
  from core.components import catalog
  specs=catalog()
  for key in ('speech-large','speech-qwen','qwen-asr-runtime'):
   for asset in specs[key].assets:
    self.assertEqual(len(asset.sha),64);self.assertGreater(asset.size,0);self.assertTrue(asset.url.startswith('https://'))

 def test_running_model_stays_distinct_from_pending_selection(self):
  from ui.settings import SettingsDialog
  with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsDialog(AppConfig(),EventBus(),page=3)
  d._model_metrics({'kind':'live','backend':'GPU / Vulkan','model':'Whisper large-v3-turbo','analysis_status':'Unloaded'})
  d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-qwen'))
  self.assertIn('Whisper large-v3-turbo',d._speech_running.text());self.assertEqual(d._speech_choice.currentData(),'speech-qwen');d.reject()

if __name__=='__main__':unittest.main()
