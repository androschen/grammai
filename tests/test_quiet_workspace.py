"""Regression coverage for compact navigation and in-place review updates."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from dataclasses import replace
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication,QLabel
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.revisions import revised_update
from ui.panel import ControlPanel
from ui.history import HistoryPanel,HistoryCard
from ui.learning import StudyDialog
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])
class WorkspaceTests(unittest.TestCase):
    def test_compact_controls_and_theme_keep_accessible_names(self):
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(AppConfig(),EventBus())
        self.assertEqual(panel._workspace.count(),2)
        self.assertEqual(panel._toggle.text(),'')
        self.assertEqual(panel._toggle.accessibleName(),'Start translation')
        panel.set_subtitles_on(True);self.assertEqual(panel._toggle.accessibleName(),'Pause translation')
        for theme in ('dark','light'):
            panel._config.theme=theme;panel._on_app_state(panel._config.snapshot());panel.show();APP.processEvents();self.assertFalse(panel.grab().isNull())
        self.assertGreaterEqual(panel._route.width(),120)
        panel.mark_quitting();panel.close()
    def test_review_does_not_remove_selected_text_and_clear_discards_deferred_updates(self):
        history=HistoryPanel();value=SubtitleUpdate('', 'Old meaning','Original speech')
        history.append(value);card=history.findChild(HistoryCard);target=card.findChild(QLabel,'target');target.setSelection(0,3)
        history.replace_update(revised_update(value,target_text='New meaning'))
        self.assertEqual(target.selectedText(),'Old');self.assertEqual(len(history._deferred_updates),1)
        target.setSelection(0,0);history._flush_deferred();self.assertEqual(history._deferred_updates,{})
        self.assertEqual(history._list.itemAt(1).widget().subtitle.target_text,'New meaning')
        history.clear();self.assertFalse(history._selection_timer.isActive());history.close()
    def test_details_close_restores_conversation_without_resizing_window(self):
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(AppConfig(),EventBus())
        initial=panel.size();value=SubtitleUpdate('', 'Meaning','Original speech')
        dialog=StudyDialog(value,AppConfig(),EventBus(),ReplayStore(),Mock())
        panel.open_sentence_details(dialog);self.assertFalse(panel._details_host.isHidden());self.assertEqual(panel.size(),initial)
        dialog.reject();self.assertTrue(panel._details_host.isHidden());self.assertFalse(panel._history_panel.isHidden())
        panel.mark_quitting();panel.close()

    def test_overlay_control_explains_state_and_only_toggles_visibility(self):
        events=EventBus();visibility=[];capture=[]
        events.overlay_toggled.connect(visibility.append);events.subtitles_toggled.connect(capture.append)
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(AppConfig(),events)
        self.assertEqual(panel._overlay_toggle.text(),'')
        self.assertEqual(panel._overlay_toggle.width(),36)
        was=panel._overlay_toggle.isChecked();panel._overlay_toggle.click()
        self.assertEqual(visibility,[not was]);self.assertEqual(capture,[])
        self.assertEqual(panel._overlay_toggle.accessibleName(),'Show subtitles' if was else 'Hide subtitles')
        panel.mark_quitting();panel.close()
    def test_refinement_marker_is_icon_only_and_manual_revision_is_not_ai(self):
        original=SubtitleUpdate('', 'First meaning','Original speech')
        refined=revised_update(original,target_text='AI meaning',ai_refined=True)
        card=HistoryCard(refined);badge=card.findChild(QLabel,'revisionBadge')
        self.assertEqual(badge.text(),'');self.assertFalse(badge.pixmap().isNull());self.assertEqual(badge.accessibleName(),'AI refined')
        manual=revised_update(refined,target_text='My meaning');self.assertFalse(manual.ai_refined)
        untouched=HistoryCard(original);self.assertIsNone(untouched.findChild(QLabel,'revisionBadge'))
        card.close();untouched.close()
    def test_settings_category_selection_tracks_page_and_timing_is_collapsed(self):
        from ui.settings import SettingsDialog
        with patch('ui.settings.list_audio_sources',return_value=[]):dialog=SettingsDialog(AppConfig(),EventBus(),page=3)
        self.assertEqual(dialog.categories.currentRow(),3)
        dialog.categories.setCurrentRow(1);self.assertEqual(dialog.tabs.currentIndex(),1)
        dialog.tabs.setCurrentIndex(0);self.assertEqual(dialog.categories.currentRow(),0)
        self.assertTrue(dialog._speech_max.parentWidget().isHidden())
        dialog.reject()

    def test_theme_button_switches_immediately_and_updates_action(self):
        config=AppConfig(theme='dark');events=EventBus();states=[];events.state_changed.connect(states.append)
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(config,events)
        self.assertEqual(panel._theme_button.accessibleName(),'Switch to light mode')
        panel._theme_button.click();self.assertEqual(config.theme,'light');self.assertEqual(len(states),1)
        self.assertEqual(panel._theme_button.accessibleName(),'Switch to dark mode')
        panel._theme_button.click();self.assertEqual(config.theme,'dark')
        panel.mark_quitting();panel.close()
    def test_refinement_does_not_shift_original_text_column(self):
        value=SubtitleUpdate('', 'Meaning','Original',source_language='en')
        cards=[HistoryCard(value),HistoryCard(revised_update(value,target_text='Better meaning',ai_refined=True))]
        positions=[]
        for card in cards:
            card.resize(500,110);card.show();APP.processEvents()
            label=card.findChild(QLabel,'originalSpeech');positions.append(label.mapTo(card,label.rect().topLeft()).x())
        self.assertEqual(positions[0],positions[1])
        for card in cards:card.close()
    def test_selected_audio_name_remains_visible_and_updates_from_settings(self):
        config=AppConfig();events=EventBus()
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(config,events)
        config.audio_device_name='HyperX microphone';config.audio_device_kind='mic';events.state_changed.emit(config.snapshot());panel.show();APP.processEvents()
        self.assertTrue(panel._device.isVisibleTo(panel));self.assertEqual(panel._header_layout.indexOf(panel._toggle),3)
        self.assertIn('Mic',panel._device.accessibleName())
        self.assertIn(config.audio_device_name,panel._device.toolTip());self.assertIn(config.audio_device_name,panel._device.currentText())
        panel.mark_quitting();panel.close()

    def test_threshold_icon_displays_current_setting_and_opens_audio_settings(self):
        config=AppConfig(noise_threshold=.28);events=EventBus()
        with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(config,events)
        self.assertIn('28%',panel._threshold_button.toolTip())
        with patch.object(panel,'_open_settings') as settings:
            panel._threshold_button.click();settings.assert_called_once_with(0)
        config.noise_threshold=.15;events.state_changed.emit(config.snapshot())
        self.assertIn('15%',panel._threshold_button.toolTip())
        panel.mark_quitting();panel.close()
