"""Regressions for centered threshold markers and separated deck reading panes."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.phrasebook import Phrasebook
from ui.components import AudioMeterWidget
from ui.panel import ControlPanel
APP=QApplication.instance() or QApplication([])


class VisualGeometryTests(unittest.TestCase):
 def test_marker_tracks_visible_bar_without_styling_each_volume_frame(self):
  for theme in ('dark','light'):
   APP.setProperty('grammai_theme',theme)
   for interactive in (False,True):
    meter=AudioMeterWidget(threshold=28,interactive=interactive);meter.resize(260,meter.height());meter.show();QTest.qWait(5)
    for width in (140,400):
     meter.resize(width,meter.height());QTest.qWait(5)
     track=meter.progress_bar.geometry();marker=meter._marker.geometry()
     self.assertEqual(track.height(),8);self.assertEqual(marker.center().y(),track.center().y())
     self.assertGreaterEqual(marker.top(),0);self.assertLess(marker.bottom(),meter.height())
     self.assertLessEqual(abs(marker.center().x()-width*.28),2)
    with patch.object(meter.progress_bar,'setStyleSheet',wraps=meter.progress_bar.setStyleSheet) as stylesheet:
     for level in range(20):meter.update_volume(level)
     stylesheet.assert_not_called();meter.update_volume(60);stylesheet.assert_called_once()
     meter.update_volume(80);stylesheet.assert_called_once()
    meter.close();meter.deleteLater()
 def test_deck_keeps_gap_and_aligned_padding_at_wide_and_compact_sizes(self):
  with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
   Phrasebook().save(SubtitleUpdate('','Meaning','Original sentence',source_language='en',target_language='id'),reviewed=True)
   for theme in ('dark','light'):
    with patch('ui.panel.list_audio_sources',return_value=[]):panel=ControlPanel(AppConfig(theme=theme),EventBus())
    panel.resize(1100,820);panel.show();panel._open_phrasebook();QTest.qWait(15);deck=panel._deck_page
    gap=deck.editor.x()-(deck.browser.x()+deck.browser.width())
    self.assertGreaterEqual(gap,16)
    expression_x=deck.editor.expression_text.mapTo(deck.editor,QPoint(0,0)).x();route_x=deck.editor.route.mapTo(deck.editor,QPoint(0,0)).x()
    self.assertGreaterEqual(expression_x,16);self.assertLessEqual(abs(expression_x-route_x),2)
    panel.resize(660,740);deck.edit_selected();QTest.qWait(10)
    self.assertTrue(deck.browser.isHidden());self.assertGreaterEqual(deck.editor.expression_text.mapTo(deck.editor,QPoint(0,0)).x(),16)
    panel.mark_quitting();panel.close();panel.deleteLater();QTest.qWait(5)
