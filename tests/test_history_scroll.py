"""History follows actual cards after layout changes and bounded eviction."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from dataclasses import replace

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.events import SubtitleUpdate
from ui.history import HistoryCard, HistoryPanel

APP = QApplication.instance() or QApplication([])


class HistoryScrollTests(unittest.TestCase):
    def setUp(self):
        self.panel = HistoryPanel()
        self.panel.resize(640, 360)
        self.panel.show()
        QTest.qWait(30)

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        QTest.qWait(10)

    def append_lines(self, count):
        for index in range(count):
            self.panel.append(SubtitleUpdate('pronunciation', f'Sentence {index}', 'original'))
        for _ in range(10):
            QTest.qWait(20)

    def assert_last_visible(self):
        cards = [self.panel._list.itemAt(i).widget()
                 for i in range(self.panel._list.count())
                 if isinstance(self.panel._list.itemAt(i).widget(), HistoryCard)]
        last = cards[-1]
        viewport = self.panel._scroll.viewport()
        bottom = last.mapTo(viewport, QPoint(0, last.height() - 1)).y()
        self.assertGreaterEqual(bottom, 0)
        self.assertLess(bottom, viewport.height())
        self.assertLess(viewport.height() - bottom, 12)

    def test_follow_after_eviction_resize_and_replacement(self):
        self.append_lines(110)
        self.assertEqual(self.panel._card_count(), 80)
        self.assert_last_visible()
        last = self.panel._list.itemAt(self.panel._list.count()-1).widget()
        self.panel.replace_update(replace(last.subtitle, target_text='A longer translated sentence ' * 12))
        self.panel.resize(520, 420)
        for _ in range(10):
            QTest.qWait(20)
        self.assert_last_visible()

    def test_clear_repopulate_and_disable_follow(self):
        self.append_lines(90)
        self.panel.clear()
        self.append_lines(85)
        self.assert_last_visible()
        self.panel._follow.setChecked(False)
        bar = self.panel._scroll.verticalScrollBar()
        bar.setValue(0)
        self.append_lines(1)
        self.assertEqual(bar.value(), 0)


if __name__ == '__main__':
    unittest.main()
