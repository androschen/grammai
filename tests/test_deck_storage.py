"""Saved data must never be mistaken for a successfully loaded empty deck."""
import os,json,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from core.preferences import data_dir
from core.phrasebook import Phrasebook,DeckReadError
from core.config import AppConfig
from core.events import SubtitleUpdate
from ui.deck import LearningDeckDialog
APP=QApplication.instance() or QApplication([])


class DeckStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook();self.book.save(SubtitleUpdate('','Meaning','Original'),reviewed=True)
        self.path=data_dir()/'phrases.json'
    def tearDown(self):self.env.stop();self.temp.cleanup()

    def test_read_failure_is_not_cached_or_silently_replaced(self):
        before=self.path.read_bytes();book=Phrasebook()
        with patch.object(Path,'read_text',side_effect=PermissionError('blocked')):
            with self.assertRaises(DeckReadError):book.items()
            with self.assertRaises(DeckReadError):book.save(SubtitleUpdate('','new','new'))
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(len(book.items()),1)

    def test_invalid_json_or_shape_does_not_allow_a_save(self):
        for text in ('not json','{}','[{}]'):
            self.path.write_text(text,encoding='utf8');book=Phrasebook()
            with self.assertRaises(DeckReadError):book.save(SubtitleUpdate('','new','new'))
            self.assertEqual(self.path.read_text(encoding='utf8'),text)

    def test_windows_bom_and_new_process_both_load_saved_cards(self):
        content=self.path.read_text(encoding='utf8');self.path.write_text(content,encoding='utf-8-sig')
        self.assertEqual(len(Phrasebook().items()),1)
        dialog=LearningDeckDialog(AppConfig(),Phrasebook())
        self.assertEqual(dialog.list.count(),1);self.assertIn(str(self.path),dialog.summary.toolTip());dialog.reject()

    def test_deck_shows_failure_and_retries_same_file_successfully(self):
        with patch.object(Path,'read_text',side_effect=PermissionError('blocked')):
            dialog=LearningDeckDialog(AppConfig(),Phrasebook())
            self.assertEqual(dialog.summary.text(),'Deck unavailable')
            self.assertFalse(dialog.retry.isHidden());self.assertFalse(dialog.start.isEnabled())
            self.assertIn('PermissionError',dialog.empty.text())
        dialog.retry.click();self.assertEqual(dialog.list.count(),1)
        self.assertTrue(dialog.retry.isHidden());self.assertEqual(dialog.summary.text(),'1 saved · 1 due');dialog.reject()

    def test_refresh_verifies_file_even_when_metadata_unchanged(self):
        dialog=LearningDeckDialog(AppConfig(),Phrasebook());self.assertEqual(dialog.list.count(),1)
        with patch.object(Path,'read_text',side_effect=PermissionError('blocked')):dialog.reload()
        self.assertEqual(dialog.summary.text(),'Deck unavailable')
        dialog.reload();self.assertEqual(dialog.list.count(),1);dialog.reject()
