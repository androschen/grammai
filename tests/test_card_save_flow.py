"""Saved time, success-only close and live deck refresh regressions."""
import os,tempfile,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timezone,timedelta
from threading import Event
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QThreadPool
from core.card_time import saved_time
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.phrasebook import Phrasebook
from core.analysis import AnalysisService
from audio.replay import ReplayStore
from ui.learning import StudyDialog
from ui.phrase_explain import PhraseExplanationDialog
APP=QApplication.instance() or QApplication([])
PAYLOAD=dict(phrase='gua',sentence='gua beli nasi dulu',language='id',original_text='gua beli nasi dulu',original_language='id',context=[])
VALUE=dict(meaning='I / me',usage='Informal',usage_note='',uncertainty='')


def settle(predicate):
    for _ in range(300):
        if predicate():return
        time.sleep(.005);QTest.qWait(5)
    raise AssertionError('Save did not complete')


class CardSaveFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name);self.env.start()
        self.book=Phrasebook();self.events=EventBus();self.service=AnalysisService(events=self.events);self.update=SubtitleUpdate('','Hello','Halo',source_language='id',target_language='en')
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000);self.service.shutdown();self.service.timer.stop();QTest.qWait(5);self.env.stop();self.temp.cleanup()
    def phrase(self):
        d=PhraseExplanationDialog(AppConfig(),self.events,self.service,PAYLOAD,self.book)
        # Supply an already prepared draft without starting the local model.
        d.show();d.completed(None,VALUE);d.notes.setPlainText('Keep my note');d.checked.setChecked(True)
        return d
    def test_local_time_midnight_boundary_and_invalid_legacy_date(self):
        now=datetime(2026,10,25,0,30,tzinfo=timezone(timedelta(hours=7)))
        self.assertEqual(saved_time('2026-10-24T17:10:00+00:00',now)[0],'Today, 00:10')
        self.assertEqual(saved_time('2026-10-24T16:59:00+00:00',now)[0],'Yesterday, 23:59')
        self.assertIn('UTC+07:00',saved_time('2026-10-24T17:10:00Z',now)[1])
        for value in (None,'','wrong','2026-10-24T14:32:00'):
            self.assertEqual(saved_time(value,now)[0],'Date unavailable')
    def test_duplicate_save_and_note_edit_preserve_original_timestamp(self):
        first=self.book.save(self.update,reviewed=True);stamp=first['saved_at']
        self.book.update_notes(first['id'],'New notes');self.book.save(self.update,'Again',reviewed=True)
        self.assertEqual(self.book.items()[0]['saved_at'],stamp)
        word=self.book.save_vocabulary(PAYLOAD,VALUE,'I',reviewed=True);stamp=word['saved_at']
        self.book.save_vocabulary(PAYLOAD,VALUE,'I / me','Changed notes',reviewed=True)
        self.assertEqual(next(x for x in self.book.items() if x['id']==word['id'])['saved_at'],stamp)
    def test_phrase_success_closes_and_emits_one_saved_event(self):
        seen=[];self.events.card_saved.connect(seen.append);d=self.phrase();d._save()
        self.assertTrue(d.closed);self.assertFalse(d.isVisible());self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]['notes'],'Keep my note');self.assertEqual(seen[0]['saved_at'],self.book.items()[0]['saved_at'])
    def test_phrase_write_failure_keeps_popup_notes_and_no_success_event(self):
        seen=[];self.events.card_saved.connect(seen.append);d=self.phrase()
        with patch.object(self.book,'save_vocabulary',side_effect=OSError('Disk full')):d._save()
        self.assertTrue(d.isVisible());self.assertFalse(d.closed);self.assertEqual(d.notes.toPlainText(),'Keep my note');self.assertIn('Disk full',d.status.text());self.assertEqual(seen,[])
        d.reject()
    def test_sentence_waits_for_audio_then_closes_only_save_popup(self):
        store=ReplayStore();store.add('clip',np.zeros(16000,np.float32))
        from dataclasses import replace
        d=StudyDialog(replace(self.update,audio_id='clip'),AppConfig(),self.events,store,self.book);d.show();d.bookmark.click();d.notes.setPlainText('With audio');d.reviewed.setChecked(True)
        from audio.library import AudioLibrary
        original=AudioLibrary.save;release=Event();seen=[];self.events.card_saved.connect(seen.append)
        def blocked(library,audio,rate):
            if not release.wait(3):raise ValueError('Test timeout')
            return original(library,audio,rate)
        try:
            with patch.object(AudioLibrary,'save',blocked):
                d._save();self.assertTrue(d.save_popup.isVisible());self.assertFalse(d.save.isEnabled());self.assertEqual(self.book.items(),[])
                release.set();settle(lambda:not d.save_fields.audio.busy)
            self.assertFalse(d.save_popup.isVisible());self.assertTrue(d.isVisible());self.assertEqual(len(seen),1)
            self.assertTrue(seen[0].get('audio'));self.assertEqual(seen[0]['notes'],'With audio')
        finally:release.set();d.reject()
    def test_sentence_failure_keeps_popup_and_notes(self):
        d=StudyDialog(self.update,AppConfig(),self.events,ReplayStore(),self.book);d.show();d.bookmark.click();d.notes.setPlainText('Still here');d.reviewed.setChecked(True)
        seen=[];self.events.card_saved.connect(seen.append)
        with patch.object(self.book,'save',side_effect=ValueError('Deck limit')):d._save()
        self.assertTrue(d.save_popup.isVisible());self.assertEqual(d.notes.toPlainText(),'Still here');self.assertIn('Deck limit',d.learning_feedback.text());self.assertEqual(seen,[]);d.reject()
    def test_open_deck_refreshes_without_losing_notes_and_shows_time(self):
        from ui.deck import LearningDeckPage
        from ui.panel import ControlPanel
        from dataclasses import replace
        first=self.book.save(self.update,reviewed=True)
        panel=ControlPanel(AppConfig(),self.events);panel.show();panel._open_phrasebook();page=panel._deck_page;QTest.qWait(5)
        page.notes.setPlainText('Unsaved draft');second=self.book.save(replace(self.update,native_text='Apa kabar'),reviewed=True)
        self.events.card_saved.emit(second)
        self.assertEqual(page.list.count(),2);self.assertEqual(page.notes.toPlainText(),'Unsaved draft')
        self.assertTrue(page.editor.saved_at.text().startswith('Saved '));self.assertIn('UTC',page.editor.saved_at.toolTip())
        text=page.list.itemDelegate().document(page.list.model().index(0,0),300,page.palette()).toPlainText()
        self.assertIn(saved_time(first['saved_at'])[0],text)
        self.assertFalse(panel._save_notice.isHidden());self.assertEqual(panel._save_notice.text(),'✓ Card saved')
        panel.mark_quitting();panel.close()

if __name__=='__main__':unittest.main()
