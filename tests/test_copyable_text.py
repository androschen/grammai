"""Exercise copy shortcuts and the actual reading-text context menu."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from ui.copyable_text import CopyableLabel
from ui.history import HistoryCard
from core.events import SubtitleUpdate

APP=QApplication.instance() or QApplication([])


class CopyTextTests(unittest.TestCase):
    def setUp(self):
        self.label=CopyableLabel('你好 hello สวัสดี <text> 🎧')
        self.label.show();self.label.setFocus();APP.processEvents()
        APP.clipboard().setText('unchanged')

    def tearDown(self):
        self.label.close();self.label.deleteLater()

    def test_keyboard_copies_selection_and_whole_text(self):
        self.label.setSelection(3,5)
        QTest.keyClick(self.label,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(APP.clipboard().text(),'hello')
        self.label.setSelection(0,0)
        QTest.keyClick(self.label,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(APP.clipboard().text(),self.label.text())
        QTest.keyClick(self.label,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.label.selectedText(),self.label.text())

    def test_right_click_menu_copies_selection(self):
        self.label.setSelection(3,5)
        def choose_copy():
            menu=APP.activePopupWidget()
            if menu:
                menu.actions()[0].trigger();menu.close()
        QTimer.singleShot(30,choose_copy)
        event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,QPoint(5,5),self.label.mapToGlobal(QPoint(5,5)))
        APP.sendEvent(self.label,event)
        self.assertEqual(APP.clipboard().text(),'hello')

    def test_history_uses_copyable_text_without_copy_buttons(self):
        for featured in (False,True):
            card=HistoryCard(SubtitleUpdate('ni hao','Hello','你好'),featured=featured)
            label=card.findChild(CopyableLabel,'target')
            self.assertIsNotNone(label)
            label.copy()
            self.assertEqual(APP.clipboard().text(),'Hello')
            self.assertFalse(any('Copy' in b.text() for b in card.findChildren(QPushButton)))
            card.deleteLater()
