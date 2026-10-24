"""On-demand explanation caching, review gating, quotas and CPU-only practice."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.analysis import AnalysisService
from core.phrasebook import Phrasebook
from core.preferences import data_dir
from ml.phrase_explanation import explanation_input,explain
from ui.copyable_text import CopyableLabel
from ui.deck import LearningDeckDialog
from ui.learning import StudyDialog
from audio.replay import ReplayStore

APP=QApplication.instance() or QApplication([])
PAYLOAD={'phrase':'gua','sentence':'gua beli nasi dulu','language':'id','original_text':'gua beli nasi dulu','original_language':'id','text_role':'original'}
VALUE={'meaning':'saya (informal)','usage':'Informal','usage_note':'An informal way to refer to yourself.','uncertainty':'Depends on context.'}


class PhraseExplanationTests(unittest.TestCase):
    def test_input_and_output_are_bounded_and_translation_is_not_evidence(self):
        value=explanation_input(dict(PAYLOAD,context=[{'text':'x'*800,'language':'en'}]*6))
        self.assertEqual(len(value['context']),2)
        self.assertTrue(all(len(x['text'])<=160 for x in value['context']))
        with self.assertRaises(ValueError):explanation_input(dict(PAYLOAD,phrase='x'*121))
        with self.assertRaises(ValueError):explanation_input(dict(PAYLOAD,phrase='not present'))
        runtime=Mock();runtime.complete_json.return_value=dict(VALUE,usage='casual',sentence_meaning='Saya mau beli nasi dulu.',why='Gua adalah kata ganti informal.',words=[dict(text=PAYLOAD['sentence'],pronunciation='',meaning='Saya mau beli nasi dulu.',reason='Rencana tindakan selanjutnya.')])
        result=explain(AppConfig(),dict(PAYLOAD,text_role='translation'),runtime)
        body=runtime.complete_json.call_args.args[0]
        self.assertEqual(body['max_tokens'],2560)
        self.assertTrue(body['chat_template_kwargs']['enable_thinking'])
        self.assertIn('not evidence',body['messages'][0]['content'])
        self.assertEqual({k:result[k] for k in VALUE},VALUE)

    def test_same_request_uses_session_cache_and_forces_local_provider(self):
        events=EventBus();service=AnalysisService(events=events,config=AppConfig())
        results=[];service.phrase_completed.connect(lambda token,value:results.append((token,value)))
        config=AppConfig(analysis_provider='online')
        try:
            with patch('ml.phrase_explanation.explain',return_value=VALUE) as run:
                self.assertTrue(service.explain('first',config,PAYLOAD))
                self.assertEqual(service.worker.config.analysis_provider,'local')
                for _ in range(100):
                    QTest.qWait(5)
                    if not service.busy:break
                self.assertTrue(results)
                self.assertTrue(service.explain('second',config,PAYLOAD));QTest.qWait(10)
                self.assertEqual(run.call_count,1)
                self.assertTrue(results[-1][1]['cached'])
        finally:
            service.shutdown();service.timer.stop()

    def test_selection_menu_emits_exact_phrase_and_keeps_copy_actions(self):
        label=CopyableLabel('gua beli nasi');selected=[];label.explain_handler=selected.append
        label.setSelection(0,3);menu=label.create_copy_menu()
        self.assertEqual(menu.actions()[0].text(),'Copy')
        next(a for a in menu.actions() if a.text()=='Create learning card (local AI)').trigger()
        self.assertEqual(selected,['gua'])
        menu.deleteLater();label.deleteLater()

    def test_closing_before_queued_start_never_requests_inference(self):
        from ui.phrase_explain import PhraseExplanationDialog
        events=EventBus();service=AnalysisService(events=events)
        with patch.object(service,'explain') as request:
            dialog=PhraseExplanationDialog(AppConfig(),events,service,PAYLOAD,Mock())
            dialog.reject();QTest.qWait(10)
            request.assert_not_called()
        service.shutdown();service.timer.stop()

    def test_live_model_lease_prevents_extra_explanation_worker(self):
        events=EventBus();events.setProperty('local_translation_owned',True)
        service=AnalysisService(events=events)
        self.assertFalse(service.explain('busy',AppConfig(),PAYLOAD))
        self.assertIsNone(service.worker);service.timer.stop()


class LearningDeckTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=Path.cwd())
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.folder.name);self.env.start()
        self.book=Phrasebook();self.update=SubtitleUpdate('', 'Hello','original',audio_id='never-persist-audio',source_language='en',target_language='id')
    def tearDown(self):self.env.stop();self.folder.cleanup()

    def test_only_explicitly_reviewed_cards_are_due_and_no_audio_is_written(self):
        self.book.save(self.update)
        self.assertEqual(self.book.due(),[])
        self.book.save(self.update,reviewed=True)
        self.assertEqual(len(self.book.items()),1)
        self.assertEqual(len(self.book.due()),1)
        self.assertNotIn('never-persist-audio',(data_dir()/'phrases.json').read_text())
        self.assertEqual(list(data_dir().glob('*.wav')),[])

    def test_spacing_and_edit_reset_are_cpu_only_and_persisted(self):
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        item=self.book.save(self.update,reviewed=True)
        self.book.grade(item['id'],True,now)
        self.assertEqual(self.book.due(now=now),[])
        self.assertEqual(len(self.book.due(now=now+timedelta(days=1))),1)
        self.book.grade(item['id'],False,now)
        self.assertEqual(self.book.due(now=now+timedelta(minutes=9)),[])
        self.assertEqual(len(self.book.due(now=now+timedelta(minutes=10))),1)
        self.book.update_card(item['id'],'edited original','edited meaning','',True)
        self.assertNotIn('due_at',self.book.items()[0])
        self.assertTrue(self.book.items()[0]['reviewed_by_user'])

    def test_quota_failure_during_edit_keeps_original_data(self):
        item=self.book.save(self.update,reviewed=True)
        before=(data_dir()/'phrases.json').read_bytes()
        with patch('core.phrasebook.MAX_BYTES',10):
            with self.assertRaises(ValueError):self.book.update_card(item['id'],'edited','meaning','',True)
        self.assertEqual(before,(data_dir()/'phrases.json').read_bytes())

    def test_save_requires_confirmation_and_invalidates_it_on_text_changes(self):
        dialog=StudyDialog(self.update,AppConfig(),EventBus(),ReplayStore(),self.book)
        dialog._save();self.assertEqual(self.book.items(),[])
        dialog.reviewed.setChecked(True);dialog._save()
        self.assertTrue(self.book.items()[0]['reviewed_by_user'])
        dialog.text.setPlainText('changed');self.assertFalse(dialog.reviewed.isChecked())
        dialog._save();self.assertEqual(len(self.book.items()),1)
        dialog.reject()

    def test_practice_requires_reveal_and_limits_session_to_ten(self):
        for index in range(12):
            self.book.save(SubtitleUpdate('', 'meaning '+str(index),'sentence '+str(index),source_language='en',target_language='id'),reviewed=True)
        dialog=LearningDeckDialog(AppConfig(),self.book)
        dialog.start_review();self.assertEqual(len(dialog.queue),10)
        dialog.grade(True);self.assertEqual(dialog.index,0)
        dialog.reveal_answer();dialog.grade(True);self.assertEqual(dialog.index,1)
        self.assertTrue(dialog.answer.isHidden());self.assertFalse(dialog.again.isEnabled())
        self.assertEqual(len(self.book.due()),11)
        dialog.close()
