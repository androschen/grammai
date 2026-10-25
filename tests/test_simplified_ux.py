"""Approved UX flows: one action per control, explicit context, reviewed saving."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock
from dataclasses import replace
import numpy as np
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication,QPushButton
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.history import SessionHistory
from audio.replay import ReplayStore
from ui.learning import StudyDialog
from ui.history import HistoryPanel
APP=QApplication.instance() or QApplication([])
class Service(QObject):
    completed=Signal(str,object)
    def __init__(self):super().__init__();self.request=Mock(return_value=True);self.cancel=Mock()
class SimplifiedUXTests(unittest.TestCase):
    def make(self,history=None,source='zh',target='en'):
        self.events=EventBus();self.store=ReplayStore();self.store.add('sample',np.zeros(1600,dtype=np.float32));self.service=Service()
        self.value=SubtitleUpdate('', 'Meaning' if source!=target else 'Original','Original',audio_id='sample',source_language=source,target_language=target)
        if history is not None:history.append(self.value)
        self.dialog=StudyDialog(self.value,AppConfig(analysis_enabled=True),self.events,self.store,Mock(),analysis=self.service,history=history)
        return self.dialog
    def tearDown(self):
        if hasattr(self,'dialog'):self.dialog.reject()
    def test_one_replay_button_starts_stops_and_resets_on_finish(self):
        d=self.make();requests=[]
        def playback(key,speed):requests.append((key,speed));self.events.playback_active.emit(bool(key))
        self.events.replay_requested.connect(playback)
        d.replay.click();self.assertEqual(d.replay.accessibleName(),'Stop replay');self.assertEqual(requests[-1][0],'sample')
        d.replay.click();self.assertEqual(requests[-1][0],'');self.assertEqual(d.replay.accessibleName(),'Replay sentence')
        d.replay.click();self.events.playback_active.emit(False);self.assertEqual(d.replay.accessibleName(),'Replay sentence')
        self.assertEqual([b for b in d.findChildren(QPushButton) if b.accessibleName()=='Stop replay'],[])
    def test_replay_failure_never_claims_playing_and_other_playback_does_not_own_button(self):
        d=self.make();d.replay.click();self.assertFalse(d._replay_active)
        self.events.playback_active.emit(False);self.events.playback_active.emit(True);self.assertFalse(d._replay_active)
        self.assertEqual(d.replay.accessibleName(),'Replay sentence')
    def test_context_visible_only_when_available_and_selected_sentence_distinct(self):
        history=SessionHistory();history.append(SubtitleUpdate('', 'Earlier meaning','Earlier original',source_language='zh'))
        d=self.make(history);w=d.analysis_widget
        self.assertFalse(w.context_preview.isHidden());self.assertFalse(w.context_heading.isHidden());self.assertEqual(w.context.toPlainText(),'Earlier original')
        self.assertEqual(w.source_text.toPlainText(),'Original');self.assertTrue(w.source_text.isReadOnly())
        self.assertFalse(any(b.text()=='Earlier dialogue' for b in d.findChildren(QPushButton)));self.service.request.assert_not_called()
    def test_cancel_only_visible_during_request_and_empty_output_sections_omitted(self):
        d=self.make();w=d.analysis_widget;self.assertTrue(w.context_preview.isHidden());self.assertTrue(w.cancel.isHidden())
        w._run();self.assertFalse(w.cancel.isHidden());token=w.token
        w._finished(token,{'source_meaning':'Meaning','translation':'Meaning','explanation':'','ambiguity':''})
        self.assertTrue(w.cancel.isHidden());self.assertTrue(w.apply.isHidden());self.assertEqual(w.result_layout.count(),4)
        w._run();self.assertFalse(w.cancel.isHidden());w.cancel_request();self.assertTrue(w.cancel.isHidden())
    def test_same_language_has_status_tooltip_without_empty_translation_section(self):
        d=self.make(source='en',target='en');self.assertTrue(d.translation_section.isHidden());self.assertTrue(d.route_review_icon.isHidden());self.assertFalse(d.model_info.isHidden())
        self.events.review_state_changed.emit(replace(self.value,review_status='skipped',review_reason='Already English.'))
        self.assertIn('Already English',d.model_info.toolTip())
    def test_one_follow_control_and_save_confirmation_only_invalidates_meaning_edits(self):
        p=HistoryPanel();self.assertFalse(any(b.text()=='Resume live' for b in p.findChildren(QPushButton)));p.close()
        d=self.make();d.bookmark.click();d.reviewed.setChecked(True);d.notes.setPlainText('Reminder');self.assertTrue(d.reviewed.isChecked())
        d.save_meaning.setPlainText('Edited meaning');self.assertFalse(d.reviewed.isChecked());self.assertFalse(d.save.isEnabled())
