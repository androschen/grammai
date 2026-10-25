"""Save is available only for unsaved configuration edits, not UI activity."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from ui.settings import SettingsPage
APP=QApplication.instance() or QApplication([])
class SettingsDirtyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
  self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name,GRAMMAI_MODELS_DIR=str(self.folder/'models'),HF_HUB_CACHE=str(self.folder/'cache'));self.env.start()
  self.config=AppConfig();self.events=EventBus()
  with patch('ui.settings.list_audio_sources',return_value=[]):self.page=SettingsPage(self.config,self.events)
 def tearDown(self):
  self.page.dispose();self.page.close();self.page.deleteLater();QTest.qWait(5);self.env.stop();self.temp.cleanup()
 def test_initial_navigation_metrics_and_component_refresh_remain_clean(self):
  d=self.page;self.assertFalse(d.save_changes.isEnabled())
  for i in range(d.tabs.count()):d.tabs.setCurrentIndex(i)
  d._model_metrics({'kind':'live','backend':'Stopped','analysis_status':'Unloaded'})
  d._show_components(True);d._show_components(False)
  self.assertFalse(d.save_changes.isEnabled())
 def test_edit_and_revert_for_each_configuration_area(self):
  d=self.page
  for widget,new in ((d._source,d._source.findData('zh')),(d._threads,2),(d.appearance.opacity,0),(d.storage.audio_limit,0),(d.analysis_settings.gguf,'different.gguf')):
   if hasattr(widget,'currentIndex'):old=widget.currentIndex();widget.setCurrentIndex(new);restore=lambda w=widget,v=old:w.setCurrentIndex(v)
   elif hasattr(widget,'value'):old=widget.value();widget.setValue(new);restore=lambda w=widget,v=old:w.setValue(v)
   else:old=widget.text();widget.setText(new);restore=lambda w=widget,v=old:w.setText(v)
   self.assertTrue(d.save_changes.isEnabled(),type(widget).__name__);restore();self.assertFalse(d.save_changes.isEnabled(),type(widget).__name__)
 def test_refinement_toggle_and_destination(self):
  d=self.page;d._refinement.setChecked(True);self.assertTrue(d.save_changes.isEnabled());d._refinement.setChecked(False);self.assertFalse(d.save_changes.isEnabled())
  d._refinement_destination.setCurrentIndex(1);self.assertTrue(d.save_changes.isEnabled());d._refinement_destination.setCurrentIndex(0);self.assertFalse(d.save_changes.isEnabled())
 def test_save_resets_baseline_and_new_edits_enable_again(self):
  d=self.page;d._threads.setValue(2);self.assertTrue(d.save_changes.isEnabled());self.assertTrue(d.apply());self.assertEqual(self.config.cpu_threads,2);self.assertFalse(d.save_changes.isEnabled())
  d._threads.setValue(3);self.assertTrue(d.save_changes.isEnabled());d._threads.setValue(2);self.assertFalse(d.save_changes.isEnabled())
 def test_live_noise_preview_revert_and_page_switch_preserve_dirty_state(self):
  d=self.page;d.activate();d._gate._apply_preset(28);self.assertTrue(d.save_changes.isEnabled());d.suspend();self.assertEqual(self.config.noise_threshold,.12)
  d.activate();self.assertTrue(d.save_changes.isEnabled());d._gate._apply_preset(12);self.assertFalse(d.save_changes.isEnabled())
 def test_invalid_edit_enables_save_without_applying_it(self):
  d=self.page;d.analysis_settings.enabled.setChecked(True);d.analysis_settings.provider.setCurrentIndex(d.analysis_settings.provider.findData('online'));d.analysis_settings.endpoint.setText('bad endpoint')
  self.assertTrue(d.save_changes.isEnabled());self.assertFalse(d.apply());self.assertEqual(self.config.analysis_provider,'local');self.assertTrue(d.save_changes.isEnabled())
 def test_pending_switch_success_and_failure_restore_correct_save_state(self):
  d=self.page;self.events.setProperty('speech_switch_available',True);requests=[];self.events.speech_switch_requested.connect(requests.append)
  d._threads.setValue(2);self.assertFalse(d.apply());self.assertFalse(d.save_changes.isEnabled());token=requests[-1]['token']
  self.events.speech_switch_finished.emit({'token':token,'error':'Test failure'});self.assertTrue(d.save_changes.isEnabled());self.assertEqual(self.config.cpu_threads,4)
  d.apply();token=requests[-1]['token'];self.config.cpu_threads=2
  self.events.speech_switch_finished.emit({'token':token});self.assertFalse(d.save_changes.isEnabled())
 def test_external_theme_refresh_is_not_an_unsaved_edit(self):
  d=self.page;self.config.theme='light';d.activate();self.assertEqual(d._theme.currentData(),'light');self.assertFalse(d.save_changes.isEnabled())

 def test_setup_applied_updates_its_baseline_but_preserves_other_drafts(self):
  d=self.page;d.appearance.opacity.setValue(0);self.config.translation_mode='context';d._setup_applied()
  self.assertTrue(d.save_changes.isEnabled());d.appearance.opacity.setValue(round(self.config.overlay_opacity*100/255));self.assertFalse(d.save_changes.isEnabled())
