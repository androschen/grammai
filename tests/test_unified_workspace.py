"""Persistent navigation must preserve drafts, previews, capture and saved learning."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig,TargetLanguage
from core.events import EventBus,SubtitleUpdate
from core.revisions import revised_update
from core.phrasebook import Phrasebook
from ui.panel import ControlPanel
from ui.learning import StudyDialog
from ui.history import HistoryCard
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])


class UnifiedWorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
  self.config=AppConfig();self.events=EventBus();self.capture=[];self.events.subtitles_toggled.connect(self.capture.append)
  self.audio=patch('ui.settings.list_audio_sources',return_value=[]);self.audio.start()
  with patch('ui.panel.list_audio_sources',return_value=[]):self.panel=ControlPanel(self.config,self.events,ReplayStore())
  self.panel.resize(1040,800);self.panel.show();QTest.qWait(10)
 def tearDown(self):
  self.panel.mark_quitting();self.panel.close();self.panel.deleteLater();QTest.qWait(10);self.audio.stop();self.env.stop();self.temp.cleanup()
 def settings(self):
  self.panel._open_settings(0);return self.panel._settings_page
 def test_settings_and_resources_are_reused_without_toggling_capture(self):
  page=self.settings();self.assertFalse(page.isWindow());self.assertIs(page.window(),self.panel)
  for _ in range(3):self.panel._show_page('resources');self.panel._open_settings(None)
  self.assertIs(page,self.panel._settings_page);self.assertEqual(self.panel._pages.count(),3);self.assertEqual(self.capture,[])
  self.assertFalse(self.panel._resources_page.isWindow());self.assertTrue(self.panel._toggle.isVisibleTo(self.panel))
 def test_pending_model_draft_survives_navigation_and_requires_save(self):
  page=self.settings();page._threads.setValue(2);self.panel._show_page('conversation')
  self.assertEqual(self.config.cpu_threads,4);self.panel._open_settings(None);self.assertEqual(page._threads.value(),2)
  self.assertTrue(page.apply());self.assertEqual(self.config.cpu_threads,2)
 def test_gate_preview_reverts_on_leave_but_pending_value_can_be_saved(self):
  page=self.settings();page._gate._apply_preset(28);self.assertEqual(self.config.noise_threshold,.28)
  self.panel._show_page('conversation');self.assertEqual(self.config.noise_threshold,.12)
  self.panel._open_settings(None);self.assertEqual(page._gate.meter.threshold,28);self.assertEqual(self.config.noise_threshold,.12)
  page.apply();self.assertEqual(self.config.noise_threshold,.28)
  self.panel._show_page('resources');self.assertEqual(self.config.noise_threshold,.28)
 def test_leaving_settings_cancels_appearance_preview_without_losing_draft(self):
  values=[];self.events.overlay_appearance_preview.connect(values.append);page=self.settings();page.appearance.opacity.setValue(0)
  for _ in range(30):
   QTest.qWait(10)
   if values:break
  self.assertTrue(values);self.assertEqual(values[-1].overlay_opacity,0);self.panel._show_page('deck');self.assertIsNone(values[-1]);self.assertNotEqual(self.config.overlay_opacity,0)
  self.panel._open_settings(None);self.assertEqual(page.appearance.opacity.value(),0)
 def test_save_merges_untouched_external_changes_and_preserves_device_identity(self):
  page=self.settings();page._threads.setValue(2);self.panel._show_page('conversation')
  self.config.target_language=TargetLanguage.THAI;self.config.translation_mode='review';self.config.audio_device_id='unavailable-device';self.config.audio_device_name='My microphone'
  self.panel._theme_button.click();self.panel._open_settings(None);self.assertTrue(page.apply())
  self.assertEqual(self.config.theme,'light');self.assertEqual(self.config.target_language,TargetLanguage.THAI);self.assertEqual(self.config.translation_mode,'review');self.assertEqual(self.config.audio_device_id,'unavailable-device');self.assertEqual(self.config.audio_device_name,'My microphone');self.assertEqual(self.config.cpu_threads,2)
 def test_discard_recreates_settings_from_saved_configuration(self):
  page=self.settings();page._threads.setValue(2);page._gate._apply_preset(28);page.reject();new=self.panel._settings_page
  self.assertIsNot(page,new);self.assertEqual(new._threads.value(),4);self.assertEqual(self.config.noise_threshold,.12);self.assertFalse(new._disposed)
 def test_compact_sentence_navigation_and_refinement_keep_selected_row(self):
  original=SubtitleUpdate('','Meaning','Original',source_language='en',target_language='id');self.panel._on_subtitle(original)
  study=StudyDialog(original,self.config,self.events,ReplayStore(),Phrasebook());self.panel.open_sentence_details(study)
  self.panel.resize(660,720);QTest.qWait(15);self.assertTrue(self.panel._history_panel.isHidden());self.assertFalse(self.panel._details_host.isHidden())
  updated=revised_update(original,target_text='Better meaning',ai_refined=True);self.panel._on_corrected(updated)
  card=next(x for x in self.panel._history_panel.findChildren(HistoryCard) if x.subtitle.uid==original.uid and not x.isHidden())
  self.assertTrue(card.property('selected'));study.close_button.click();QTest.qWait(10);self.assertFalse(self.panel._history_panel.isHidden());self.assertIsNone(self.panel._details_view)
 def test_page_navigation_does_not_write_cards_or_start_inference(self):
  book=Phrasebook();book.save(SubtitleUpdate('','Halo','Hello',source_language='en',target_language='id'),reviewed=True)
  path=Path(self.temp.name,'phrases.json');before=path.read_bytes()
  with patch('core.analysis.AnalysisService.explain',side_effect=AssertionError('Unexpected inference')):
   self.settings();self.panel._show_page('resources');self.panel._show_page('deck');self.panel._deck_page.start_review();self.panel._deck_page.reveal_answer()
  self.assertEqual(path.read_bytes(),before);self.assertEqual(self.capture,[])
