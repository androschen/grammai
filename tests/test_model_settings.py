import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from core.config import AppConfig
from core.events import EventBus
from ui.settings import SettingsDialog
APP=QApplication.instance() or QApplication([])

class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.config=AppConfig()
        self.events=EventBus()
        with patch('ui.settings.list_audio_sources',return_value=[]):
            self.dialog=SettingsDialog(self.config,self.events,page=3)
    def tearDown(self):
        self.dialog.reject()
    def test_one_model_page_hides_technical_controls(self):
        d=self.dialog
        self.assertEqual(d.tabs.tabText(3),'Models')
        self.assertTrue(d._model_advanced.isHidden())
        self.assertTrue(d._model_advanced.isAncestorOf(d.analysis_settings.files))
        self.assertTrue(d._model_advanced.isAncestorOf(d._threads))
    def test_gpu_description_does_not_claim_cpu_model_size(self):
        d=self.dialog
        d._backend.setCurrentIndex(d._backend.findData('vulkan'))
        self.assertNotIn('base speech model',d._preset_help.text())
        self.assertIn('Files missing',d._selected_models.text())
        d._model_metrics({'kind':'live','backend':'CPU / int8','model':'small','analysis_status':'Unloaded'})
        self.assertIn('CPU / int8',d._runtime_models.text())
        self.assertIn('Radeon GPU',d._selected_models.text())
    def test_draft_and_live_status_never_apply_pending_selection(self):
        d=self.dialog
        d._translation_mode.setCurrentIndex(d._translation_mode.findData('review'))
        self.assertEqual(d._draft().translation_mode,'review')
        self.assertEqual(self.config.translation_mode,'fast')
        self.assertNotIn('compare and apply',d._mode_hint.text())
        d._model_metrics({'kind':'live','backend':'Stopped','analysis_status':'Unloaded'})
        self.assertEqual(self.config.translation_mode,'fast')
