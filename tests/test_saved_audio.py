"""Persistent audio: shared clips, quotas, failure recovery and Practice answer safety."""
import os,tempfile,unittest,json,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QThreadPool
from core.events import SubtitleUpdate,EventBus
from core.config import AppConfig
from core.phrasebook import Phrasebook,DeckReadError
from audio.library import AudioLibrary,AudioLimitError
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])


def settle(predicate):
    for _ in range(300):
        if predicate():return
        time.sleep(.005);QTest.qWait(5)
    raise AssertionError('Audio background job did not finish')


class SavedAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.audio=(.2*np.sin(2*np.pi*440*np.arange(64000)/16000)).astype(np.float32)
        self.library=AudioLibrary();self.book=Phrasebook();self.events=EventBus()
        self.update=SubtitleUpdate('','Hello','Halo',source_language='id',target_language='en')
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);QTest.qWait(10);self.env.stop();self.temp.cleanup()
    def test_restart_shared_audio_and_final_reference_delete(self):
        clip=self.library.save(self.audio);same=self.library.save(self.audio.copy())
        self.assertEqual(clip,same);self.assertLess(clip['bytes'],len(self.audio)*2)
        first=self.book.save(self.update,audio=clip,reviewed=True)
        from dataclasses import replace
        second=self.book.save(replace(self.update,native_text='Hai'),audio=clip,reviewed=True)
        restarted=Phrasebook().items(force=True);self.assertEqual(len(restarted),2)
        decoded=AudioLibrary().load(clip['file']);self.assertEqual(len(decoded),len(self.audio))
        self.assertLess(float(np.mean((decoded-self.audio)**2)),.01)
        self.book.delete(first['id']);self.assertTrue(self.library.available(second))
        self.book.remove_audio(second['id']);self.assertEqual(self.library.stats()['clips'],0)
        remaining=Phrasebook().items()[0];self.assertEqual(remaining['native_text'],'Hai');self.assertTrue(remaining['reviewed_by_user'])
    def test_quota_no_eviction_and_explicit_unused_cleanup(self):
        clip=self.library.save(self.audio);saved=self.book.save(self.update,audio=clip)
        tiny=AudioLibrary(limit_mb=clip['bytes']/1024**2)
        self.assertEqual(tiny.save(self.audio)['file'],clip['file'])
        with self.assertRaises(AudioLimitError):tiny.save(-self.audio)
        extra=self.library.save(-self.audio);self.assertGreater(self.library.stats(self.book.items())['unused_bytes'],0)
        self.library.cleanup(lambda:self.book.items(force=True))
        self.assertTrue(self.library.available(saved));self.assertFalse(self.library.available({'audio':extra}))
    def test_atomic_failure_and_missing_recording_keep_text(self):
        with patch('audio.library.os.replace',side_effect=OSError('disk unavailable')):
            # pathlib.Path.replace delegates to os.replace.
            with self.assertRaises(OSError):self.library.save(self.audio)
        self.assertEqual(list(Path(self.temp.name).glob('audio/*')),[])
        clip=self.library.save(self.audio)
        with patch('core.phrasebook.write_json',side_effect=OSError('deck unavailable')):
            with self.assertRaises(OSError):self.book.save(self.update,audio=clip)
        self.assertEqual(self.book.items(),[])
        self.library.cleanup(lambda:self.book.items(force=True));self.assertEqual(self.library.stats()['clips'],0)
        clip=self.library.save(self.audio);self.book.save(self.update,audio=clip)
        self.library.path(clip['file']).unlink();item=self.book.items()[0]
        self.book.update_notes(item['id'],'Still safe');self.assertEqual(self.book.items()[0]['notes'],'Still safe')
        self.assertFalse(self.library.available(item))
    def test_managed_paths_and_unreadable_deck_cleanup_protection(self):
        for name in ('../phrases.json','C:/private.ogg','x.ogg'):
            with self.assertRaises(ValueError):self.library.path(name)
        clip=self.library.save(self.audio);Path(self.temp.name,'phrases.json').write_text('{',encoding='utf8')
        with self.assertRaises(DeckReadError):self.library.cleanup(lambda:self.book.items(force=True))
        self.assertTrue(self.library.available({'audio':clip}))
    def test_save_widget_async_and_text_only_expired(self):
        from ui.card_audio import SaveAudioWidget
        store=ReplayStore();store.add('clip',self.audio)
        widget=SaveAudioWidget();widget.bind(store,'clip',AppConfig(),'Halo','id')
        self.assertTrue(widget.include.isChecked());results=[];items=[]
        widget.commit(lambda clip:items.append(clip),results.append)
        settle(lambda:not widget.busy)
        self.assertEqual(results,[None]);self.assertEqual(items[0]['original_text'],'Halo');self.assertEqual(items[0]['language'],'id')
        widget.bind(store,'missing',AppConfig());self.assertFalse(widget.include.isEnabled())
        widget.commit(lambda clip:items.append(clip),results.append);self.assertIsNone(items[-1]);widget.deleteLater()
    def test_closing_save_cancels_reference_write(self):
        from ui.card_audio import SaveAudioWidget
        store=ReplayStore();store.add('clip',self.audio);widget=SaveAudioWidget();widget.bind(store,'clip',AppConfig())
        saved=[];widget.commit(saved.append,lambda error:None);widget.cancel_pending()
        settle(lambda:not widget.busy);self.assertEqual(saved,[]);widget.deleteLater()
    def test_practice_audio_hidden_until_reveal_and_stops_when_leaving(self):
        from ui.deck import LearningDeckPage
        clip=dict(self.library.save(self.audio),original_text='Halo');self.book.save(self.update,audio=clip,reviewed=True)
        page=LearningDeckPage(AppConfig(),self.book,events=self.events);page.show();QTest.qWait(5)
        page.start_review();page.tabs.setCurrentIndex(1)
        self.assertTrue(page.practice_audio.play.isEnabled())
        page.mode.setCurrentIndex(page.mode.findData('recall'));self.assertFalse(page.practice_audio.play.isEnabled())
        self.assertEqual(page.practice_audio.caption.text(),'Reveal to listen');self.assertEqual(page.practice_audio.toolTip(),'')
        page.reveal_answer();self.assertTrue(page.practice_audio.play.isEnabled())
        stopped=[];self.events.replay_requested.connect(lambda key,speed:stopped.append(key))
        self.events.playback_started.emit(page.practice_audio.key);page.tabs.setCurrentIndex(0)
        self.assertIn('',stopped)
        page.dispose();page.close()
    def test_both_save_flows_keep_original_audio_and_provenance(self):
        from ui.learning import StudyDialog
        from ui.phrase_explain import PhraseExplanationDialog
        from core.analysis import AnalysisService
        from dataclasses import replace
        store=ReplayStore();store.add('original',self.audio)
        update=replace(self.update,audio_id='original')
        dialog=StudyDialog(update,AppConfig(),self.events,store,self.book)
        dialog.bookmark.click();dialog.reviewed.setChecked(True);dialog._save()
        settle(lambda:not dialog.save_fields.audio.busy)
        first=self.book.items()[0];self.assertEqual(first['audio']['original_text'],'Halo')
        dialog.reject()
        service=AnalysisService(events=self.events)
        payload=dict(phrase='Hello',sentence='Hello there',language='en',original_text='Halo',original_language='id',text_role='translation',audio_id='original',context=[])
        with patch.object(service,'explain',return_value=True):
            d=PhraseExplanationDialog(AppConfig(),self.events,service,payload,self.book,replays=store)
            QTest.qWait(5);d.completed(d.token,dict(meaning='Halo',usage='',usage_note='',uncertainty=''))
            d.checked.setChecked(True);d._save();settle(lambda:not d.form.audio.busy)
            second=next(x for x in self.book.items() if x.get('card_type')=='vocabulary')
            self.assertEqual(second['audio']['file'],first['audio']['file'])
            self.assertEqual(second['audio']['language'],'id');self.assertEqual(second['audio']['original_text'],'Halo')
            d.reject()
        service.shutdown();service.timer.stop()
    def test_saved_decode_returns_on_ui_thread_and_stop_cancels_pending_play(self):
        from audio.playback import AudioReplay
        from PySide6.QtCore import QThread
        clip=self.library.save(self.audio);player=AudioReplay(self.events,ReplayStore());started=[]
        def record(*args):started.append(QThread.currentThread())
        with patch.object(player,'_start',side_effect=record):
            player.play('saved:'+clip['file']);settle(lambda:bool(started))
            self.assertIs(started[0],APP.thread())
            started.clear();player.play('saved:'+clip['file']);player.stop()
            QThreadPool.globalInstance().waitForDone(3000);QTest.qWait(10);self.assertEqual(started,[])
        player.stop();player.deleteLater()
    def test_open_save_preview_retains_clip_after_session_expiry(self):
        from ui.card_audio import SaveAudioWidget
        from audio.playback import AudioReplay
        now=[0.];store=ReplayStore(clock=lambda:now[0]);store.add('held',self.audio)
        widget=SaveAudioWidget();widget.bind(store,'held',AppConfig(),events=self.events)
        now[0]=100;self.assertIsNone(store.get('held'))
        player=AudioReplay(self.events,store)
        with patch.object(player,'_start') as start:
            widget.preview.toggle();self.assertTrue(start.called)
            self.assertEqual(len(start.call_args.args[2]),len(self.audio))
        widget.cancel_pending();widget.preview.dispose();widget.deleteLater();player.stop();player.deleteLater()
    def test_load_preferences_budget_backwards_compatible(self):
        from core.preferences import load_config,write_json
        self.assertEqual(load_config().saved_audio_limit_mb,250)
        write_json('preferences.json',{'saved_audio_limit_mb':500});self.assertEqual(load_config().saved_audio_limit_mb,500)
        write_json('preferences.json',{'saved_audio_limit_mb':-1});self.assertEqual(load_config().saved_audio_limit_mb,250)

if __name__=='__main__':unittest.main()
