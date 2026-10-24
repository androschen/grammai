"""Source grounding, restart persistence and reveal-only local tutoring."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.analysis import AnalysisService
from core.phrasebook import Phrasebook
from core.preferences import data_dir
from ml.card_explanation import validate_learning
from ml.phrase_explanation import explain
from ui.deck import LearningDeckDialog
from ui.card_explanation import CardExplanationWidget

APP=QApplication.instance() or QApplication([])
PAYLOAD=dict(phrase='gua',sentence='gua beli nasi dulu',language='id',original_text='gua beli nasi dulu',original_language='id',text_role='original')
VALUE=dict(meaning='Saya / aku',usage='Informal',usage_note='Kata ganti informal.',uncertainty='',
    sentence_meaning='Aku mau beli nasi dulu.',why='Gua merujuk pembicara; dulu menunjukkan urutan tindakan.',
    words=[dict(text=text,pronunciation='',meaning=meaning,reason=reason) for text,meaning,reason in [
        ('gua','aku','Kata ganti orang pertama.'),('beli','membeli','Tindakan yang akan dilakukan.'),
        ('nasi','nasi matang','Objek yang dibeli.'),('dulu','terlebih dahulu','Urutan tindakan, bukan waktu lampau.')]])


class CardExplanations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def save(self,value=VALUE):return self.book.save_vocabulary(PAYLOAD,value,VALUE['meaning'],'Personal notes',reviewed=True)

    def test_explanation_survives_restart_and_reveal_needs_no_inference(self):
        self.save();book=Phrasebook();item=book.items()[0]
        self.assertEqual(item['learning_explanation']['words'],VALUE['words'])
        with patch.object(AnalysisService,'explain',side_effect=AssertionError('Reveal must not run AI')):
            deck=LearningDeckDialog(AppConfig(),book);deck.start_review()
            self.assertTrue(deck.answer.isHidden());self.assertIsNone(deck.practice_explanation.value)
            deck.reveal_answer();self.assertEqual(deck.practice_explanation.value['why'],VALUE['why'])
            self.assertIn('Personal notes',deck.practice_notes.text())
            deck.mode.setCurrentIndex(deck.mode.findData('recall'));self.assertIsNone(deck.practice_explanation.value)
            self.assertTrue(deck.answer.isHidden());deck.reject()

    def test_notes_preserve_explanation_but_text_edits_invalidate_it(self):
        item=self.save();self.book.grade(item['id'],True)
        self.book.update_card(item['id'],'gua',VALUE['meaning'],'New note',True)
        self.assertIn('learning_explanation',self.book.items()[0]);self.assertIn('due_at',self.book.items()[0])
        self.book.update_card(item['id'],'gua','Edited meaning','New note',True)
        self.assertNotIn('learning_explanation',self.book.items()[0])

    def test_wrong_or_incomplete_source_breakdown_rejected_without_overwrite(self):
        self.save();before=(data_dir()/'phrases.json').read_bytes()
        for words in ([dict(VALUE['words'][0],text='cave')],VALUE['words'][:1],list(reversed(VALUE['words']))):
            with self.assertRaises(ValueError):self.save(dict(VALUE,words=words))
            self.assertEqual((data_dir()/'phrases.json').read_bytes(),before)
        with self.assertRaises(ValueError):validate_learning(dict(VALUE,source='fake'),PAYLOAD)

    def test_original_speech_used_for_translation_selection(self):
        payload=dict(PAYLOAD,phrase='I',sentence='I will buy rice first.',language='en',text_role='translation')
        runtime=Mock();runtime.complete_json.return_value=dict(VALUE,usage='casual')
        result=explain(AppConfig(),payload,runtime)
        self.assertEqual(result['source'],PAYLOAD['original_text'])
        self.assertEqual(result['words'][0]['text'],'gua')
        body=runtime.complete_json.call_args.args[0]
        self.assertIn('original_text',body['messages'][1]['content'])

    def test_legacy_explanation_save_keeps_notes_and_schedule_and_quota(self):
        old={key:VALUE[key] for key in ('meaning','usage','usage_note','uncertainty')}
        item=self.save(old);self.book.grade(item['id'],True)
        before=self.book.items()[0]
        updated=self.book.save_explanation(item['id'],VALUE,'id')
        self.assertEqual(updated['due_at'],before['due_at']);self.assertEqual(updated['notes'],before['notes'])
        raw=(data_dir()/'phrases.json').read_bytes()
        with patch('core.phrasebook.MAX_BYTES',10):
            with self.assertRaises(ValueError):self.book.save_explanation(item['id'],VALUE,'id')
        self.assertEqual((data_dir()/'phrases.json').read_bytes(),raw)

    def test_on_demand_followup_and_cancel_ignore_stale_completion(self):
        events=EventBus();service=AnalysisService(events=events);widget=CardExplanationWidget(AppConfig(),events,service)
        widget.set_data(VALUE,PAYLOAD)
        with patch.object(service,'explain',return_value=True) as inference:
            inference.assert_not_called();widget.question.setText('Why dulu?');widget.ask_question()
            self.assertEqual(inference.call_args.args[2]['question'],'Why dulu?')
            token=widget.token;widget.completed(token,{'answer':'It marks order.'})
            self.assertIn('It marks order.',widget.response.text());self.assertFalse(events.property('learning_explanation_pending'))
            widget.ask_question();stale=widget.token;widget.set_data(None,None)
            widget.completed(stale,{'answer':'stale'});self.assertTrue(widget.response.isHidden())
        widget.dispose();service.shutdown();service.timer.stop()

    def test_local_translation_is_not_interrupted_by_followup(self):
        events=EventBus();events.setProperty('local_translation_owned',True);service=AnalysisService(events=events)
        widget=CardExplanationWidget(AppConfig(),events,service);widget.set_data(VALUE,PAYLOAD)
        with patch.object(service,'explain') as inference:
            widget.question.setText('Why?');widget.ask_question();inference.assert_not_called()
            self.assertIn('Pause live translation',widget.status.text())
        widget.dispose();service.shutdown();service.timer.stop()

    def test_short_context_excerpt_is_saved_and_invalid_questions_rejected(self):
        payload=dict(PAYLOAD,sentence='gua '+'beli '*60+'nasi dulu')
        runtime=Mock();snippet=payload['sentence'][:240]
        runtime.complete_json.return_value=dict(VALUE,usage='casual',words=[dict(text=snippet,pronunciation='',meaning='Kalimat panjang.',reason='Cuplikan percakapan.')])
        result=explain(AppConfig(analysis_context_tokens=2048),payload,runtime)
        saved=self.book.save_vocabulary(payload,result,'Saya','',reviewed=True)
        self.assertEqual(saved['learning_explanation']['source'],snippet)
        with self.assertRaises(ValueError):explain(AppConfig(),dict(PAYLOAD,question='x'*401),runtime)


    def test_incomplete_model_draft_gets_only_one_correction(self):
        runtime=Mock();bad=dict(VALUE,usage='casual',words=VALUE['words'][:1]);good=dict(VALUE,usage='casual')
        runtime.complete_json.side_effect=[bad,good]
        result=explain(AppConfig(),PAYLOAD,runtime)
        self.assertEqual(result['words'],VALUE['words']);self.assertEqual(runtime.complete_json.call_count,2)
        runtime.reset_mock();runtime.complete_json.side_effect=[bad,bad]
        with self.assertRaises(ValueError):explain(AppConfig(),PAYLOAD,runtime)
        self.assertEqual(runtime.complete_json.call_count,2)

    def test_selected_clause_preserves_separate_model_word_rows(self):
        payload=dict(phrase='如果你叫',sentence='如果你叫',language='zh',original_text='如果你叫',original_language='zh')
        words=[dict(text=t,pronunciation='',meaning=m,reason=r) for t,m,r in [('如果','jika','kondisi'),('你','kamu','subjek'),('叫','memanggil','kata kerja')]]
        runtime=Mock();runtime.complete_json.return_value=dict(VALUE,usage='neutral',words=words)
        result=explain(AppConfig(),payload,runtime)
        self.assertEqual([word['text'] for word in result['words']],['如果','你','叫'])

    def test_missing_original_is_not_replaced_by_selected_translation(self):
        from ml.card_explanation import card_payload,learning_source
        payload=card_payload(dict(native_text='cave',example_sentence='Cave buys rice.',source_language='en',example_role='translation'))
        self.assertEqual(learning_source(payload),'')


    def test_reading_card_notes_save_does_not_change_review_or_explanation(self):
        item=self.save();self.book.grade(item['id'],True);before=self.book.items()[0]
        deck=LearningDeckDialog(AppConfig(),self.book);deck.editor.show();QTest.qWait(5)
        self.assertFalse(deck.original.isVisibleTo(deck.editor));self.assertTrue(deck.checked.isHidden())
        self.assertFalse(deck.editor.expression_text.isHidden())
        deck.notes.setPlainText('New note without reconfirming meaning')
        self.assertTrue(deck.save.isEnabled());deck.save_card()
        after=self.book.items()[0]
        self.assertEqual(after['notes'],'New note without reconfirming meaning')
        for key in ('native_text','target_text','due_at','interval_days','reviewed_at','learning_explanation'):
            self.assertEqual(after[key],before[key])
        deck.editor.edit.click();self.assertTrue(deck.original.isVisibleTo(deck.editor));self.assertFalse(deck.checked.isHidden())
        deck.meaning.setPlainText('Edited meaning');self.assertFalse(deck.save.isEnabled())
        deck.checked.setChecked(True);self.assertTrue(deck.save.isEnabled());deck.save_card()
        self.assertEqual(self.book.items()[0]['target_text'],'Edited meaning');deck.reject()

    def test_refresh_bypasses_cached_explanation(self):
        service=AnalysisService();config=AppConfig()
        with patch.object(service,'_start') as start:
            service.explain('first',config,PAYLOAD);key=start.call_args.args[4]
            service._result('first',key,'explain',VALUE)
            service.explain('cached',config,PAYLOAD);self.assertEqual(start.call_count,1)
            service.explain('fresh',config,dict(PAYLOAD,refresh=True));self.assertEqual(start.call_count,2)
        service.shutdown();service.timer.stop()

    def test_draft_refresh_updates_the_value_that_is_saved(self):
        from ui.phrase_explain import PhraseExplanationDialog
        events=EventBus();service=AnalysisService(events=events)
        with patch.object(service,'explain',return_value=True):
            draft=PhraseExplanationDialog(AppConfig(),events,service,PAYLOAD,self.book);QTest.qWait(10)
            draft.completed(draft.token,VALUE);old=draft.value
            draft.notes.setPlainText('Keep this note')
            draft.explanation.refresh.click();self.assertIsNone(draft.value)
            changed=dict(VALUE,why='New contextual reason.')
            draft.completed(draft.token,changed);draft.checked.setChecked(True);draft._save()
            item=self.book.items()[0];self.assertEqual(item['learning_explanation']['why'],'New contextual reason.')
            self.assertEqual(item['notes'],'Keep this note');draft.reject()
        service.shutdown();service.timer.stop()
