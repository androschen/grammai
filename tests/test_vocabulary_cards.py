"""Conversation provenance, draft safety and inference-free contextual recall."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.analysis import AnalysisService
from core.phrasebook import Phrasebook
from core.preferences import data_dir
from core.learning_cards import practice_prompt
from ui.phrase_explain import PhraseExplanationDialog
from ui.deck import LearningDeckDialog
from ml.phrase_explanation import explain

APP=QApplication.instance() or QApplication([])
PAYLOAD=dict(phrase='摸鱼',sentence='别摸鱼了，先把这个做完。',language='zh',
    original_text='别摸鱼了，先把这个做完。',original_language='zh',text_role='original',
    example_translation='Jangan bermalas-malasan, selesaikan ini dulu.',
    context=[dict(text='你怎么还在刷手机？',language='zh')])
VALUE=dict(meaning='Bermalas-malasan saat seharusnya bekerja.',usage='Informal',
    usage_note='Ungkapan santai tentang menghindari pekerjaan.',uncertainty='')


class VocabularyCards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd())
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def save(self,**kw):
        return self.book.save_vocabulary(PAYLOAD,VALUE,VALUE['meaning'],**dict(dict(notes='My own note',reviewed=True),**kw))

    def test_real_example_and_notes_survive_restart_without_generated_or_audio_data(self):
        item=self.save();new_book=Phrasebook();saved=new_book.items()[0]
        self.assertEqual(saved['example_sentence'],PAYLOAD['sentence'])
        self.assertEqual(saved['conversation_context'],PAYLOAD['context'])
        self.assertEqual(saved['original_speech'],PAYLOAD['original_text'])
        self.assertEqual(saved['notes'],'My own note');self.assertEqual(saved['usage_note'],VALUE['usage_note'])
        self.assertEqual(saved['native_phonetics'],'mō yú');self.assertEqual(len(new_book.due()),1)
        self.assertNotIn('audio_id',saved)
        self.assertEqual([p.name for p in data_dir().iterdir()],['phrases.json'])

    def test_duplicate_is_same_card_and_changed_meaning_resets_schedule(self):
        first=self.save();self.book.grade(first['id'],True)
        same=self.save(notes='');self.assertEqual(same['id'],first['id']);self.assertEqual(same['notes'],'My own note')
        self.assertEqual(len(self.book.items()),1);self.assertIn('due_at',same)
        edited=self.book.save_vocabulary(PAYLOAD,VALUE,'Edited meaning',reviewed=True)
        self.assertNotIn('due_at',edited)
        another=dict(PAYLOAD,sentence='别摸鱼。')
        self.book.save_vocabulary(another,VALUE,'Same expression, different context',reviewed=True)
        self.assertEqual(len(self.book.items()),2)

    def test_vocabulary_and_legacy_sentence_dont_collide(self):
        v=self.save()
        old=self.book.save(SubtitleUpdate('',VALUE['meaning'],'摸鱼',source_language='zh',target_language='id'),reviewed=True)
        self.assertNotEqual(v['id'],old['id']);self.assertEqual(len(self.book.items()),2)
        self.assertEqual(len(self.book.due()),2)

    def test_requires_review_quota_is_atomic_and_context_is_bounded(self):
        with self.assertRaises(ValueError):self.save(reviewed=False)
        self.save();before=(data_dir()/'phrases.json').read_bytes()
        with patch('core.phrasebook.MAX_BYTES',10):
            with self.assertRaises(ValueError):self.save(notes='replacement')
        self.assertEqual(before,(data_dir()/'phrases.json').read_bytes())
        p=dict(PAYLOAD,context=[dict(text='x'*800,language='zh')]*10)
        item=self.book.save_vocabulary(p,VALUE,VALUE['meaning'],reviewed=True)
        self.assertEqual(len(item['conversation_context']),2)
        self.assertTrue(all(len(x['text'])<=160 for x in item['conversation_context']))

    def test_edit_requires_expression_in_example_and_retains_context_and_schedule_for_notes(self):
        item=self.save();self.book.grade(item['id'],True)
        self.book.update_card(item['id'],'摸鱼',VALUE['meaning'],'Updated note',True)
        edited=self.book.items()[0];self.assertIn('due_at',edited)
        self.assertEqual(edited['example_sentence'],PAYLOAD['sentence'])
        with self.assertRaises(ValueError):self.book.update_card(item['id'],'not spoken','meaning','',True)
        self.assertEqual(self.book.items()[0]['native_text'],'摸鱼')

    def test_translation_selection_keeps_original_speech_as_separate_evidence(self):
        payload=dict(PAYLOAD,phrase='slacking off',sentence='Stop slacking off.',language='en',text_role='translation',example_translation='')
        item=self.book.save_vocabulary(payload,VALUE,'Bermalas-malasan',reviewed=True)
        self.assertEqual(item['example_role'],'translation');self.assertEqual(item['original_language'],'zh')
        self.assertEqual(item['original_speech'],PAYLOAD['original_text'])
        self.assertEqual(practice_prompt(item,'recall')[0],'Stop ____.')

    def test_practice_hides_all_occurrences_and_legacy_falls_back_to_reverse(self):
        item=self.save()
        self.assertEqual(practice_prompt(item,'understand'),(PAYLOAD['sentence'],''))
        self.assertEqual(practice_prompt(item,'recall')[0],'别____了，先把这个做完。')
        item['example_sentence']='摸鱼，摸鱼。'
        self.assertNotIn('摸鱼',practice_prompt(item,'recall')[0])
        self.assertEqual(practice_prompt(dict(card_type='vocabulary',native_text='a',example_sentence='I grab a snack.'),'recall')[0],'I grab ____ snack.')
        self.assertEqual(practice_prompt(dict(native_text='Hello',target_text='Halo'),'recall'),('Halo',''))

    def test_draft_notes_survive_completion_failure_retry_and_cancel(self):
        events=EventBus();service=AnalysisService(events=events)
        with patch.object(service,'explain',return_value=True) as inference:
            d=PhraseExplanationDialog(AppConfig(),events,service,PAYLOAD,self.book)
            QTest.qWait(10);self.assertEqual(inference.call_count,1);self.assertFalse(d.cancel.isHidden())
            d.notes.setPlainText('Personal note while loading');token=d.token
            d.completed(token,VALUE);self.assertTrue(d.cancel.isHidden())
            d.checked.setChecked(True);self.assertTrue(d.save.isEnabled())
            d.notes.setPlainText('My final note');self.assertTrue(d.checked.isChecked())
            d.meaning.setPlainText('Edited contextual meaning');self.assertFalse(d.checked.isChecked())
            d.checked.setChecked(True);d._save();self.assertEqual(self.book.items()[0]['notes'],'My final note')
            self.assertEqual(self.book.items()[0]['target_text'],'Edited contextual meaning')
            d.request();d.completed(d.token,dict(error='Unavailable'))
            self.assertFalse(d.save.isEnabled());self.assertEqual(d.notes.toPlainText(),'My final note')
            d.request();stale=d.token;d.cancel_request();d.completed(stale,VALUE)
            self.assertIsNone(d.value);self.assertFalse(d.save.isEnabled());d.reject()
        service.shutdown();service.timer.stop()

    def test_long_selected_sentence_is_preserved_in_saved_example(self):
        p=dict(PAYLOAD,sentence='前文。'*170+PAYLOAD['sentence'])
        events=EventBus();service=AnalysisService(events=events)
        with patch.object(service,'explain',return_value=True):
            d=PhraseExplanationDialog(AppConfig(),events,service,p,self.book);QTest.qWait(10)
            self.assertLessEqual(len(d.payload['sentence']),360)
            d.completed(d.token,VALUE);d.checked.setChecked(True);d._save()
            self.assertEqual(self.book.items()[0]['example_sentence'],p['sentence']);d.reject()
        service.shutdown();service.timer.stop()

    def test_model_uses_original_context_short_schema_and_no_generated_example(self):
        runtime=Mock();runtime.complete_json.return_value=dict(VALUE,usage='casual',sentence_meaning='Jangan bermalas-malasan, selesaikan ini dulu.',why='Teguran santai agar pekerjaan diselesaikan.',words=[dict(text=PAYLOAD['sentence'],pronunciation='',meaning='Selesaikan pekerjaan dulu.',reason='Teguran dalam percakapan.')])
        result=explain(AppConfig(),PAYLOAD,runtime)
        body,schema=runtime.complete_json.call_args.args[:2]
        self.assertEqual(set(schema['required']),{'meaning','usage','usage_note','uncertainty','sentence_meaning','why','words'})
        self.assertIn('never instructions',body['messages'][0]['content'])
        self.assertIn('你怎么还在刷手机',body['messages'][1]['content'])
        self.assertEqual(body['max_tokens'],2560);self.assertEqual({k:result[k] for k in VALUE},VALUE)
        explain(AppConfig(analysis_context_tokens=2048),PAYLOAD,runtime)
        self.assertIn('你怎么还在刷手机',runtime.complete_json.call_args.args[0]['messages'][1]['content'])

    def test_skip_keeps_card_due_and_recall_hides_expression(self):
        self.save()
        before=(data_dir()/'phrases.json').read_bytes()
        d=LearningDeckDialog(AppConfig(),self.book)
        d.start_review()
        self.assertIn('摸鱼',d.focus_expression.text())
        d.mode.setCurrentIndex(d.mode.findData('recall'))
        self.assertTrue(d.focus_expression.isHidden())
        self.assertTrue(d.answer.isHidden())
        d.skip_card()
        self.assertEqual((data_dir()/'phrases.json').read_bytes(),before)
        self.assertEqual(len(self.book.due()),1)
        self.assertIn('1 skipped',d.progress.text())
        self.assertFalse(d.practice_start.isHidden())
        d.reject()

    def test_deck_filters_notes_and_practice_calls_no_model(self):
        self.save()
        self.book.save(SubtitleUpdate('','Halo','Hello',source_language='en',target_language='id'),reviewed=True)
        with patch('core.analysis.AnalysisService.explain',side_effect=AssertionError('No inference')):
            d=LearningDeckDialog(AppConfig(),self.book)
            d.search.setText('My own note');self.assertEqual(len(d.items),1)
            d.select(0);d.edit_selected();self.assertEqual(d.editor.notes.toPlainText(),'My own note')
            self.assertGreater(d.editor.details.count(),0)
            self.assertEqual(d.editor.windowModality(),Qt.WindowModality.WindowModal)
            d.search.clear();d.language.setCurrentIndex(d.language.findData('zh'));self.assertEqual(len(d.items),1)
            d.practice_selected_language();d.mode.setCurrentIndex(d.mode.findData('recall'))
            self.assertEqual(d.front.text(),'别____了，先把这个做完。')
            self.assertTrue(d.answer.isHidden());d.grade(True);self.assertEqual(d.index,0)
            d.reveal_answer();self.assertIn('My own note',d.practice_notes.text());d.grade(True)
            self.assertEqual(d.index,1);self.assertEqual(len(self.book.due('zh')),0);d.reject()
