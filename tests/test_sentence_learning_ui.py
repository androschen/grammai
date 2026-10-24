"""Sentence history, on-demand explanation and safe standalone save flow."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.revisions import revised_update
from audio.replay import ReplayStore
from ui.learning import StudyDialog
APP=QApplication.instance() or QApplication([])
class Service(QObject):
    completed=Signal(str,object)
    def __init__(self):super().__init__();self.request=Mock(return_value=True);self.cancel=Mock()
class SentenceLearningTests(unittest.TestCase):
    def make(self,value=None):
        self.events=EventBus();self.book=Mock();self.service=Service()
        self.value=value or SubtitleUpdate('', 'First meaning','Original speech',source_language='en',target_language='id')
        return StudyDialog(self.value,AppConfig(),self.events,ReplayStore(),self.book,analysis=self.service)
    def test_only_sentence_and_meaning_pages_opening_does_not_run_ai(self):
        d=self.make();self.assertEqual([d.pages.tabText(i) for i in range(d.pages.count())],['Sentence','Meaning & context'])
        d.pages.setCurrentIndex(1);self.service.request.assert_not_called();d.reject()
    def test_history_visible_only_for_changed_wording_and_is_copyable(self):
        value=SubtitleUpdate('', 'First meaning','Original speech',source_language='en',target_language='id')
        d=self.make(revised_update(value,target_text='Refined meaning',ai_refined=True));d.show();APP.processEvents()
        self.assertTrue(d.comparison.isVisible());self.assertIn('First meaning',d.comparison.toPlainText());self.assertIn('Refined meaning',d.comparison.toPlainText())
        self.assertIn('background-color:',d.comparison.toHtml());d.reject()
        d=self.make(value);self.assertTrue(d.comparison.isHidden());d.reject()
    def test_identical_source_and_translation_not_repeated(self):
        d=self.make(SubtitleUpdate('', 'Same sentence','Same sentence',source_language='en',target_language='en'))
        self.assertTrue(d.translation_display.isHidden());self.assertEqual(d.source_display.text(),'Same sentence');d.reject()
    def test_bookmark_opens_separate_popup_and_saves_reviewed_meaning_without_changing_session(self):
        d=self.make();d.show();d.bookmark.click();APP.processEvents()
        self.assertTrue(d.save_popup.isWindow());self.assertTrue(d.save_popup.isVisible());self.assertFalse(d.save.isEnabled())
        d.save_meaning.setPlainText('My checked meaning');d.reviewed.setChecked(True);d._save()
        saved=self.book.save.call_args.args[0];self.assertEqual(saved.target_text,'My checked meaning');self.assertEqual(d.subtitle.target_text,'First meaning')
        self.service.request.assert_not_called();d.reject();self.assertFalse(d.save_popup.isVisible())
    def test_live_change_invalidates_save_and_preserves_user_meaning(self):
        d=self.make();d.show();d.bookmark.click();APP.processEvents();d.save_meaning.setPlainText('My draft');d.reviewed.setChecked(True)
        self.events.subtitle_corrected.emit(revised_update(d.subtitle,target_text='New meaning',ai_refined=True));APP.processEvents()
        self.assertFalse(d.save.isEnabled());self.assertFalse(d.reviewed.isChecked());self.assertEqual(d.save_meaning.toPlainText(),'My draft')
        d.reviewed.setChecked(True);d._save();self.book.save.assert_not_called();d.reject()

    def test_sentence_sections_do_not_spread_when_panel_grows(self):
        first=SubtitleUpdate('', 'First meaning','Original speech',native_phonetics='pronunciation',source_language='zh',target_language='id')
        d=self.make(revised_update(first,target_text='Refined meaning',ai_refined=True));d.resize(440,600);d.show();APP.processEvents()
        def geometry():
            return [(w.y(),w.height()) for w in (d.reading_section,d.translation_section,d.history_section)]
        before=geometry();d.resize(440,1000);APP.processEvents();after=geometry()
        self.assertEqual(before,after)
        self.assertLess(d.source_display.height(),80);self.assertLess(d.translation_display.height(),80)
        self.assertGreater(d.translation_section.y(),d.reading_section.geometry().bottom())
        self.assertTrue(d.history_section.isVisible());d.reject()
    def test_wrapped_sentence_stays_readable_and_same_language_hides_whole_translation_section(self):
        d=self.make(SubtitleUpdate('', 'same sentence','same sentence',source_language='en',target_language='en'))
        self.assertTrue(d.translation_section.isHidden());self.assertEqual(d.review_status_label.text(),"Not reviewed");self.assertTrue(d.history_section.isHidden());d.reject()
        d=self.make(SubtitleUpdate('', 'Meaning '*80,'Original '*80,source_language='en',target_language='id'))
        d.resize(440,650);d.show();APP.processEvents()
        self.assertGreater(d.source_display.height(),50)
        self.assertGreater(d.translation_display.height(),50);d.reject()
