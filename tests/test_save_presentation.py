"""The shared save layout must keep its source, notes and confirmation guarantees."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.analysis import AnalysisService
from core.phrasebook import Phrasebook
from ui.phrase_explain import PhraseExplanationDialog
from ui.learning import StudyDialog
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])
PAYLOAD=dict(phrase='gua',sentence='gua beli nasi dulu',language='id',original_text='gua beli nasi dulu',original_language='id',text_role='original',context=[])
VALUE=dict(meaning='I / me',usage='Informal',usage_note='',uncertainty='')


class SavePresentationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start();self.book=Phrasebook();self.events=EventBus();self.service=AnalysisService(events=self.events)
 def tearDown(self):
  self.service.shutdown();self.service.timer.stop();QTest.qWait(5);self.env.stop();self.temp.cleanup()
 def test_selected_phrase_heads_form_and_expanding_details_never_repeats_ai(self):
  with patch.object(self.service,'explain',return_value=True) as run:
   d=PhraseExplanationDialog(AppConfig(),self.events,self.service,PAYLOAD,self.book);d.show();QTest.qWait(20);d.completed(d.token,VALUE)
   self.assertEqual(d.form.expression.text(),'gua');self.assertEqual(d.form.example.original_text,PAYLOAD['sentence']);self.assertLessEqual(d.meaning.height(),44)
   d.notes.setPlainText('My reminder');d.explanation_toggle.click();d.explanation_toggle.click();self.assertEqual(run.call_count,1)
   self.assertFalse(d.save.isEnabled());d.checked.setChecked(True);self.assertTrue(d.save.isEnabled())
   d.meaning.setPlainText('An informal I');self.assertFalse(d.checked.isChecked());d.checked.setChecked(True);d._save()
   item=self.book.items()[0];self.assertEqual(item['native_text'],'gua');self.assertEqual(item['example_sentence'],PAYLOAD['sentence']);self.assertEqual(item['notes'],'My reminder');d.reject()
 def test_translation_selection_keeps_original_evidence_and_labels_example(self):
  payload=dict(PAYLOAD,phrase='I',sentence='I buy rice first',language='en',text_role='translation')
  with patch.object(self.service,'explain',return_value=True):
   d=PhraseExplanationDialog(AppConfig(),self.events,self.service,payload,self.book);QTest.qWait(10);d.completed(d.token,VALUE)
   self.assertEqual(d.form.example_caption.text(),'SELECTED TRANSLATION EXAMPLE');self.assertEqual(d.form.example.original_text,payload['sentence'])
   d.checked.setChecked(True);d._save();item=self.book.items()[0];self.assertEqual(item['original_speech'],PAYLOAD['original_text']);self.assertEqual(item['original_language'],'id');self.assertEqual(item['example_role'],'translation');d.reject()
 def test_sentence_popup_does_not_spread_fields_and_rejects_empty_meaning(self):
  d=StudyDialog(SubtitleUpdate('','Hello','Halo',source_language='id',target_language='en'),AppConfig(),self.events,ReplayStore(),self.book);d.show();d.bookmark.click();QTest.qWait(20)
  before=(d.save_fields.expression.height(),d.save_fields.pronunciation.height(),d.save_fields.notes_section.height())
  d.save_popup.resize(460,800);QTest.qWait(20);after=(d.save_fields.expression.height(),d.save_fields.pronunciation.height(),d.save_fields.notes_section.height())
  self.assertEqual(before,after);self.assertTrue(d.save_fields.example_section.isHidden())
  d.save_meaning.clear();d.reviewed.setChecked(True);self.assertFalse(d.save.isEnabled())
  d.save_meaning.setPlainText('Hello there');self.assertFalse(d.reviewed.isChecked());d.notes.setPlainText('Keep this note');d.reviewed.setChecked(True);d._save()
  self.assertEqual(self.book.items()[0]['notes'],'Keep this note');self.assertEqual(d.subtitle.target_text,'Hello');d.reject()
