"""Progress and highlighted examples must preserve recall, clipboard and storage."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import SubtitleUpdate
from core.phrasebook import Phrasebook
from ui.deck import LearningDeckDialog
from ui.deck_card import ConversationExample
APP=QApplication.instance() or QApplication([])


class LearningPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook()
        for text in ('Hello','Goodbye'):
            self.book.save(SubtitleUpdate('','Meaning',text,source_language='en',target_language='id'),reviewed=True)
        self.deck=LearningDeckDialog(AppConfig(),self.book)

    def tearDown(self):
        self.deck.reject();self.deck.deleteLater();QTest.qWait(5);self.env.stop();self.temp.cleanup()

    def test_progress_counts_completed_cards_and_skip_keeps_schedule(self):
        self.deck.start_review();self.assertEqual(self.deck.progress_bar.maximum(),2);self.assertEqual(self.deck.progress_bar.value(),0)
        self.deck.grade(True);self.assertEqual(self.deck.progress_bar.value(),0)
        self.deck.reveal_answer();self.assertEqual(self.deck.progress_bar.value(),0)
        self.deck.grade(True);self.assertEqual(self.deck.progress_bar.value(),1)
        before=Path(self.temp.name,'phrases.json').read_bytes()
        self.deck.skip_card();self.assertEqual(self.deck.progress_bar.value(),2)
        self.assertEqual(Path(self.temp.name,'phrases.json').read_bytes(),before)
        self.assertIn('unchanged',self.deck.practice_feedback.text())
        self.deck.start_review();self.assertEqual(self.deck.progress_bar.value(),0)

    def test_highlight_handles_markup_word_boundaries_and_plain_clipboard(self):
        label=ConversationExample('A snack & a <bite>','a')
        doc=QTextDocument();doc.setHtml(label.text())
        self.assertEqual(doc.toPlainText(),'A snack & a <bite>')
        self.assertEqual(label.text().count('<span'),1)
        label.copy();self.assertEqual(APP.clipboard().text(),'A snack & a <bite>')
        label.select_all();label.copy();self.assertEqual(APP.clipboard().text(),'A snack & a <bite>')
        label.deleteLater()

    def test_browsing_and_revealing_never_load_models_or_write_cards(self):
        before=Path(self.temp.name,'phrases.json').read_bytes()
        with patch('core.analysis.AnalysisService.explain',side_effect=AssertionError('Unexpected model task')):
            self.deck.start_review();self.deck.reveal_answer()
            self.deck.mode.setCurrentIndex(self.deck.mode.findData('recall'))
            self.assertTrue(self.deck.answer.isHidden());self.assertTrue(self.deck.focus_expression.isHidden())
            self.assertTrue(self.deck.practice_explanation.reading.isHidden())
            self.deck.search.setText('Hello');self.deck.select(0)
        self.assertEqual(Path(self.temp.name,'phrases.json').read_bytes(),before)
