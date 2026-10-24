"""Per-sentence review lifecycle and deliberate-only auto-follow pausing."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock
from dataclasses import replace
from PySide6.QtCore import QObject,Signal,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QAbstractSlider
from core.config import AppConfig,TargetLanguage
from core.events import EventBus,SubtitleUpdate
from core.history import SessionHistory
from core.live_review import LiveReview
from ui.history import HistoryPanel,HistoryCard
from ui.learning import StudyDialog
from audio.replay import ReplayStore
APP=QApplication.instance() or QApplication([])
class Service(QObject):
    translation_completed=Signal(str,object)
    def __init__(self):super().__init__();self.busy=False;self.calls=[]
    def refine(self,token,config,payload):self.calls.append((token,payload));return True
    def cancel(self,token):pass
class StatusTests(unittest.TestCase):
    def setUp(self):
        self.events=EventBus();self.history=SessionHistory();self.service=Service();self.config=AppConfig(translation_mode='review',target_language=TargetLanguage.ENGLISH)
        self.review=LiveReview(self.config,self.events,self.service,self.history,lambda:True)
    def tearDown(self):self.review.close()
    def add(self,text='original',source='id'):
        u=SubtitleUpdate('',text+' translated',text,source_language=source,target_language='en');self.history.append(u);self.review.enqueue(u);return u
    def current(self,u):return next(x for x in self.history.items() if x.uid==u.uid)
    def test_awaiting_reviewing_and_unchanged_are_distinct(self):
        self.service.busy=True;u=self.add();self.assertEqual(self.current(u).review_status,'awaiting')
        self.service.busy=False;self.review.pump();self.assertEqual(self.current(u).review_status,'reviewing')
        self.review.completed(self.service.calls[-1][0],{'translation':u.target_text});self.assertEqual(self.current(u).review_status,'unchanged');self.assertEqual(self.current(u).revision_count,0)
    def test_refinement_retains_first_version_and_failure_is_explicit(self):
        u=self.add();self.review.completed(self.service.calls[-1][0],{'translation':'better meaning'})
        v=self.current(u);self.assertEqual(v.review_status,'refined');self.assertEqual(v.original_target_text,u.target_text);self.assertTrue(v.ai_refined)
        u=self.add('second');self.review.completed(self.service.calls[-1][0],{'error':'test failure'});self.assertEqual(self.current(u).review_status,'failed')
    def test_replaced_pending_and_same_language_have_skipped_reasons(self):
        self.service.busy=True;u=self.add('old');self.add('new');self.assertEqual(self.current(u).review_status,'skipped');self.assertIn('Newer',self.current(u).review_reason)
        u=self.add('hello',source='en');self.assertEqual(self.current(u).review_status,'skipped');self.assertIn('matches',self.current(u).review_reason)
    def test_clear_prevents_stale_status_result_and_stop_marks_pending(self):
        u=self.add();token=self.service.calls[-1][0];self.history.clear();seen=[];self.events.review_state_changed.connect(seen.append)
        self.review.completed(token,{'translation':'stale'});self.assertEqual(seen,[])
        self.service.busy=True;u=self.add('pending');self.review.reset();self.assertEqual(self.current(u).review_status,'skipped')
    def test_open_detail_updates_metadata_without_clearing_selection_or_review_confirmation(self):
        u=SubtitleUpdate('', 'meaning','original',source_language='en',target_language='id')
        d=StudyDialog(u,AppConfig(),self.events,ReplayStore(),Mock());d.source_display.setSelection(0,4);d.reviewed.setChecked(True)
        self.events.review_state_changed.emit(replace(u,review_status='unchanged',review_reason='Kept wording.'))
        self.assertEqual(d.review_status_label.text(),'Reviewed · unchanged');self.assertEqual(d.source_display.selectedText(),'orig');self.assertTrue(d.reviewed.isChecked());d.reject()
class FollowTests(unittest.TestCase):
    def setUp(self):
        self.panel=HistoryPanel();self.panel.resize(500,360);self.panel.show()
        for i in range(25):self.panel.append(SubtitleUpdate('', 'translation '+str(i),'original speech '+str(i)))
        QTest.qWait(80);self.bar=self.panel._scroll.verticalScrollBar()
    def tearDown(self):self.panel.close();self.panel.deleteLater();APP.processEvents()
    def test_automatic_actions_updates_and_resizing_keep_follow_enabled(self):
        self.bar.triggerAction(QAbstractSlider.SliderAction.SliderToMaximum);QTest.qWait(20);self.assertTrue(self.panel._follow.isChecked())
        card=self.panel._list.itemAt(1).widget();self.panel.replace_update(replace(card.subtitle,target_text='Updated '*15));self.panel.resize(420,440)
        self.panel.append(SubtitleUpdate('', 'new translation','new speech'));QTest.qWait(80)
        self.assertTrue(self.panel._follow.isChecked());self.assertLessEqual(self.bar.maximum()-self.bar.value(),4)
    def test_user_scroll_away_pauses_and_resume_immediately_follows(self):
        QTest.keyClick(self.bar,Qt.Key.Key_PageUp);QTest.qWait(30)
        self.assertFalse(self.panel._follow.isChecked());self.assertIn('Check Auto-scroll',self.panel._follow.toolTip())
        value=self.bar.value();self.panel.append(SubtitleUpdate('', 'next','next original'));QTest.qWait(40);self.assertEqual(self.bar.value(),value)
        self.panel._follow.setChecked(True);QTest.qWait(40);self.assertTrue(self.panel._follow.isChecked());self.assertLessEqual(self.bar.maximum()-self.bar.value(),4)
    def test_user_scroll_down_at_bottom_does_not_pause(self):
        QTest.keyClick(self.bar,Qt.Key.Key_Down);QTest.qWait(30);self.assertTrue(self.panel._follow.isChecked())

    def test_wheel_scroll_away_is_deliberate_but_status_updates_are_not(self):
        from PySide6.QtCore import QPoint,QPointF,QEvent
        from PySide6.QtGui import QWheelEvent
        viewport=self.panel._scroll.viewport();center=viewport.rect().center()
        wheel=QWheelEvent(QPointF(center),QPointF(viewport.mapToGlobal(center)),QPoint(0,0),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        APP.sendEvent(viewport,wheel);QTest.qWait(30);self.assertFalse(self.panel._follow.isChecked())
        self.panel._follow.setChecked(True);QTest.qWait(30);card=self.panel._list.itemAt(1).widget();card.findChild(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel,'target').setSelection(0,4)
        self.panel.replace_update(replace(card.subtitle,target_text='AI changed translation'))
        QTest.qWait(30);self.assertTrue(self.panel._follow.isChecked());self.assertEqual(len(self.panel._deferred_updates),1)
