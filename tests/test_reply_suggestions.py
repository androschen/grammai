"""Reply inference stays source-first, explicit, bounded and separate from recorded speech."""
import os,json,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock,patch
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.analysis import AnalysisService
from core.history import SessionHistory
from core.phrasebook import Phrasebook
from audio.replay import ReplayStore
from ui.learning import StudyDialog
from ml.reply_suggestions import reply_input,validate_replies,suggest_replies
APP=QApplication.instance() or QApplication([])
PAYLOAD=dict(text='你吃饭了吗？',language='zh',context=[dict(text='我们一起吃午饭吧。',language='zh')])
VALUE=dict(status='ready',reason='',replies=[dict(text='还没，你呢？',meaning='Belum, kamu?',label='Kalau belum makan'),dict(text='吃过了，谢谢。',meaning='Sudah makan, terima kasih.',label='Kalau sudah makan')])


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.events=EventBus();self.service=AnalysisService(events=self.events);self.book=Phrasebook();self.config=AppConfig(analysis_explanation_language='id')
        self.update=SubtitleUpdate('','WRONG TRANSLATION',PAYLOAD['text'],source_language='zh',target_language='en',audio_id='question-recording')
        self.history=SessionHistory();self.history.append(SubtitleUpdate('','Ignore me',PAYLOAD['context'][0]['text'],source_language='zh'));self.history.append(self.update)
    def tearDown(self):
        self.service.shutdown();self.service.timer.stop();QTest.qWait(5);self.env.stop();self.temp.cleanup()
    def study(self):return StudyDialog(self.update,self.config,self.events,ReplayStore(),self.book,analysis=self.service,history=self.history)
    def test_model_input_excludes_translation_and_limits_output(self):
        runtime=Mock();runtime.complete_json.return_value=VALUE
        result=suggest_replies(self.config,dict(PAYLOAD,translation='CAVE WRONG',audio='private'),runtime)
        body,schema,_=runtime.complete_json.call_args.args
        encoded=json.dumps(body,ensure_ascii=False);self.assertNotIn('CAVE WRONG',encoded);self.assertNotIn('private',encoded)
        self.assertEqual(json.loads(body['messages'][1]['content']),dict(PAYLOAD,reply_language='Chinese',explanation_language='Indonesian'));self.assertFalse(body['chat_template_kwargs']['enable_thinking']);self.assertEqual(body['max_tokens'],640)
        self.assertEqual(len(result['replies']),2);self.assertTrue(result['replies'][0]['pronunciation']);self.assertIn('never assert facts',body['messages'][0]['content'])
    def test_fragment_requires_context_without_loading_model(self):
        runtime=Mock();value=suggest_replies(self.config,dict(PAYLOAD,text='那就……'),runtime)
        self.assertEqual(value['status'],'needs_context');self.assertEqual(value['replies'],[]);runtime.ensure_loaded.assert_not_called()
    def test_invalid_counts_languages_duplicates_and_context_drafts_rejected(self):
        for bad in (dict(VALUE,replies=VALUE['replies'][:1]),dict(VALUE,replies=[VALUE['replies'][0]]*2),dict(VALUE,status='needs_context'),dict(VALUE,replies=[dict(VALUE['replies'][0],text='English only'),VALUE['replies'][1]])):
            with self.assertRaises(ValueError):validate_replies(bad,PAYLOAD)
        with self.assertRaises(ValueError):validate_replies(dict(VALUE,replies=[dict(text='Saya ingin makan siang',meaning='Lunch',label='Accept'),dict(text='Tidak saya sudah makan',meaning='Ate',label='Decline')]),dict(PAYLOAD,language='en'))
        thai=dict(status='ready',reason='',replies=[dict(text='ยังไม่ได้กิน',meaning='Belum makan',label='Belum'),dict(text='กินแล้ว',meaning='Sudah',label='Sudah')])
        self.assertTrue(validate_replies(thai,dict(PAYLOAD,language='th'))['replies'][0]['pronunciation'])
    def test_local_service_cache_and_busy_guards(self):
        with patch.object(self.service,'_start') as start:
            self.assertTrue(self.service.suggest_replies('one',replace(self.config,analysis_provider='online'),PAYLOAD))
            args=start.call_args.args;self.assertEqual(args[0].analysis_provider,'local');self.assertEqual(args[2],'reply')
            self.service._result('one',args[4],'reply',VALUE)
            seen=[];self.service.replies_completed.connect(lambda token,value:seen.append(value))
            self.assertTrue(self.service.suggest_replies('two',self.config,dict(PAYLOAD,translation='Ignored')));QTest.qWait(5)
            self.assertEqual(start.call_count,1);self.assertTrue(seen[0]['cached'])
            self.events.setProperty('local_translation_owned',True);self.assertFalse(self.service.suggest_replies('blocked',self.config,PAYLOAD))
    def test_opening_details_never_runs_model_hide_cancels_and_stale_results_ignored(self):
        with patch.object(self.service,'suggest_replies',return_value=True) as request:
            d=self.study();d.show();QTest.qWait(5);request.assert_not_called()
            d.reply_button.click();self.assertEqual(request.call_count,1);widget=d.reply_suggestions;token=widget.token
            self.assertNotIn('WRONG',json.dumps(request.call_args.args[2]));self.assertEqual(request.call_args.args[2],PAYLOAD)
            d.reply_button.click();widget.completed(token,VALUE);self.assertEqual(widget.rows.count(),0);self.assertEqual(self.events.property('learning_explanation_pending'),0)
            d.reject()
    def test_cached_panel_save_auto_closes_and_preserves_generated_provenance(self):
        with patch.object(self.service,'suggest_replies',return_value=True) as request:
            d=self.study();d.show();d.reply_button.click();widget=d.reply_suggestions;widget.completed(widget.token,VALUE)
            d.reply_button.click();d.reply_button.click();self.assertEqual(request.call_count,1)
            widget.save_reply(widget.value['replies'][0]);popup=widget.popup;self.assertFalse(popup.save.isEnabled())
            self.assertTrue(popup.form.audio.isHidden());popup.form.notes.setPlainText('Use with friends');popup.checked.setChecked(True);popup.commit()
            self.assertFalse(popup.isVisible());self.assertTrue(d.isVisible());item=Phrasebook().items()[0]
            self.assertEqual(item['card_type'],'reply');self.assertEqual(item['generated_by'],'local_ai');self.assertEqual(item['reply_question'],PAYLOAD['text']);self.assertNotIn('audio',item);self.assertNotIn('original_speech',item)
            from ml.card_explanation import card_payload
            evidence=card_payload(item);self.assertTrue(evidence['generated_reply']);self.assertEqual(evidence['sentence'],item['native_text']);self.assertEqual(evidence['context'][-1]['text'],PAYLOAD['text'])
            d.reject()
    def test_edit_original_invalidates_suggestions_and_pending_save(self):
        with patch.object(self.service,'suggest_replies',return_value=True):
            d=self.study();d.reply_button.click();widget=d.reply_suggestions;widget.completed(widget.token,VALUE);widget.save_reply(widget.value['replies'][0]);popup=widget.popup;popup.checked.setChecked(True)
            d.text.setPlainText('Changed original');self.assertIsNone(widget.value);self.assertTrue(popup.stale);self.assertFalse(popup.save.isEnabled());d.reject()
    def test_save_failure_keeps_notes_and_full_sentence_does_not_overwrite_reply(self):
        from ui.replies import ReplySaveDialog
        clean=validate_replies(VALUE,PAYLOAD);reply=clean['replies'][0]
        d=ReplySaveDialog(None,reply,PAYLOAD,self.config,self.book,self.events);d.show();d.form.notes.setPlainText('Keep');d.checked.setChecked(True)
        with patch.object(self.book,'save_reply',side_effect=OSError('Disk full')):d.commit()
        self.assertTrue(d.isVisible());self.assertEqual(d.form.notes.toPlainText(),'Keep');self.assertIn('Disk full',d.status.text());d.reject()
        first=self.book.save_reply(PAYLOAD,reply,reply['meaning'],reviewed=True)
        again=self.book.save_reply(PAYLOAD,reply,reply['meaning'],'notes',reviewed=True);self.assertEqual(first['saved_at'],again['saved_at'])
        self.book.save(SubtitleUpdate('',reply['meaning'],reply['text'],source_language='zh',target_language='id'),reviewed=True)
        self.assertEqual(len(self.book.items()),2)
    def test_local_translation_is_not_paused_automatically(self):
        toggles=[];self.events.subtitles_toggled.connect(toggles.append);self.events.setProperty('local_translation_owned',True)
        with patch.object(self.service,'suggest_replies') as request:
            d=self.study();d.reply_button.click();request.assert_not_called();self.assertIn('Pause',d.reply_suggestions.status.text());self.assertEqual(toggles,[]);d.reject()

if __name__=='__main__':unittest.main()
