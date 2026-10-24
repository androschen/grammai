import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.phrasebook import Phrasebook
from ui.panel import ControlPanel
APP=QApplication.instance() or QApplication([])


class SingleWindowDeckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook();self.book.save(SubtitleUpdate('','Halo','Hello',source_language='en',target_language='id'),'Original note',reviewed=True)
        self.book.save(SubtitleUpdate('','Terima kasih','谢谢',source_language='zh',target_language='id'),reviewed=True)
        self.events=EventBus();self.signals=[];self.events.subtitles_toggled.connect(self.signals.append)
        with patch('ui.panel.list_audio_sources',return_value=[]):self.panel=ControlPanel(AppConfig(),self.events)
        self.panel.resize(1040,800);self.panel.show();QTest.qWait(15)
    def tearDown(self):
        self.panel.mark_quitting();self.panel.close();self.panel.deleteLater();QTest.qWait(5);self.env.stop();self.temp.cleanup()
    def open(self):
        self.panel._nav_deck.click();QTest.qWait(15);return self.panel._deck_page

    def test_sidebar_reuses_inline_page_and_does_not_toggle_recording(self):
        self.panel.set_subtitles_on(True);initial=self.panel.size();deck=self.open()
        self.assertFalse(deck.isWindow());self.assertFalse(deck.editor.isWindow());self.assertIs(deck.editor.window(),self.panel)
        self.assertEqual(self.panel._pages.count(),2);self.assertEqual(self.signals,[]);self.assertEqual(self.panel.size(),initial)
        self.assertTrue(self.panel._toggle.isChecked());self.assertTrue(self.panel._nav_deck.isChecked())
        for _ in range(3):self.panel._nav_conversation.click();self.panel._nav_deck.click()
        self.assertIs(self.panel._deck_page,deck);self.assertEqual(self.panel._pages.count(),2)
        self.assertFalse(any(w.isVisible() and isinstance(w,QDialog) and w.windowTitle() in ('Learning deck','Learning card') for w in APP.topLevelWidgets()))

    def test_search_notes_and_practice_reveal_survive_navigation(self):
        deck=self.open();deck.search.setText('Hello');deck.notes.setPlainText('Unsaved reminder')
        self.panel._nav_conversation.click();self.panel._nav_deck.click()
        self.assertEqual(deck.search.text(),'Hello');self.assertEqual(deck.notes.toPlainText(),'Unsaved reminder')
        deck.search.clear();deck.start_review();deck.tabs.setCurrentIndex(1);deck.reveal_answer()
        self.panel._nav_conversation.click();self.panel._nav_deck.click()
        self.assertEqual(deck.tabs.currentIndex(),1);self.assertTrue(deck.revealed);self.assertFalse(deck.answer.isHidden())
        deck.skip_card();position=deck.index
        self.panel._nav_conversation.click();self.panel._nav_deck.click();self.assertEqual(deck.index,position)

    def test_compact_back_and_wide_split_use_the_same_card_widget(self):
        deck=self.open();self.assertFalse(deck.browser.isHidden());self.assertFalse(deck.editor.isHidden())
        editor=deck.editor;self.panel.resize(660,700);QTest.qWait(20);deck.back_to_cards()
        self.assertTrue(deck._compact);self.assertFalse(deck.browser.isHidden());self.assertTrue(editor.isHidden())
        deck.edit_selected();self.assertTrue(deck.browser.isHidden());self.assertFalse(editor.isHidden());self.assertTrue(editor.back.isVisibleTo(deck))
        editor.back.click();self.assertFalse(deck.browser.isHidden());self.assertTrue(editor.isHidden())
        self.panel.resize(1040,800);QTest.qWait(20)
        self.assertIs(deck.editor,editor);self.assertFalse(deck.browser.isHidden());self.assertFalse(editor.isHidden());self.assertTrue(editor.back.isHidden())

    def test_new_saved_cards_refresh_without_discarding_note_drafts(self):
        deck=self.open();identifier=deck._loaded_card_id;deck.notes.setPlainText('Keep my unsaved draft')
        self.panel._nav_conversation.click()
        self.book.save(SubtitleUpdate('','Sampai jumpa','Bye',source_language='en',target_language='id'),reviewed=True)
        self.panel._nav_deck.click();self.assertEqual(deck.list.count(),3)
        self.assertEqual(deck._loaded_card_id,identifier);self.assertEqual(deck.notes.toPlainText(),'Keep my unsaved draft')
        self.assertEqual(next(x for x in self.book.items() if x['id']==identifier)['notes'],'Original note')

    def test_card_selection_preserves_separate_note_drafts(self):
        deck=self.open();deck.notes.setPlainText('First draft');deck.list.setCurrentRow(1);deck.notes.setPlainText('Second draft');deck.list.setCurrentRow(0)
        self.assertEqual(deck.notes.toPlainText(),'First draft');deck.list.setCurrentRow(1);self.assertEqual(deck.notes.toPlainText(),'Second draft')

    def test_hidden_conversation_keeps_receiving_history(self):
        self.open();self.events.subtitle_ready.emit(SubtitleUpdate('','Meaning','Original',source_language='en'))
        self.assertEqual(len(self.panel._history.items()),1);self.assertEqual(self.panel._history_panel._card_count(),1)
        self.panel._nav_conversation.click();self.assertTrue(self.panel._history_panel._follow.isChecked());self.assertEqual(self.signals,[])

    def test_theme_and_global_controls_work_from_the_deck(self):
        deck=self.open();self.panel._theme_button.click();QTest.qWait(10)
        self.assertEqual(self.panel._config.theme,'light');self.assertEqual(deck.styleSheet(),'');self.assertFalse(self.panel.grab().isNull())
        self.panel._toggle.click();self.assertEqual(self.signals,[True]);self.assertIn('Listening',self.panel._status.text())
        self.panel._nav_conversation.click();self.assertTrue(self.panel._toggle.isChecked())
