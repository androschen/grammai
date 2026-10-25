"""Window-level pointer regression for task helpers covering Settings navigation."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QEvent,QCoreApplication
from PySide6.QtWidgets import QApplication,QTabBar,QWidget,QVBoxLayout
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from audio.replay import ReplayStore
from ui.panel import ControlPanel
from ui.model_setup import TaskWidget,ComponentsWidget,SetupDialog,active_jobs,cancel_jobs
APP=QApplication.instance() or QApplication([])

class SettingsNavigationTests(unittest.TestCase):
 def setUp(self):
  self.windows=set(APP.topLevelWidgets());self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
  self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name,GRAMMAI_MODELS_DIR=str(self.folder/'models'),HF_HUB_CACHE=str(self.folder/'cache'));self.env.start()
  self.audio=patch('ui.settings.list_audio_sources',return_value=[]);self.audio.start()
  self.panel=None
 def tearDown(self):
  cancel_jobs()
  for _ in range(100):
   if not active_jobs():break
   QTest.qWait(10)
  if self.panel:self.panel.mark_quitting();self.panel.close();self.panel.deleteLater()
  for w in APP.topLevelWidgets():
   if w not in self.windows and w.parentWidget() is None:w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);QTest.qWait(5)
  self.audio.stop();self.env.stop();self.temp.cleanup()
 def panel_at(self,theme='dark'):
  with patch('ui.panel.list_audio_sources',return_value=[]):self.panel=ControlPanel(AppConfig(theme=theme),EventBus(),ReplayStore())
  self.panel.resize(1080,800);self.panel.show();self.panel._open_settings(2);QTest.qWait(15)
  return self.panel._settings_page
 def click_tab(self,page,index,fraction=.5):
  bar=page.tabs.tabBar();rect=bar.tabRect(index)
  # QTabBar legitimately scrolls tabs in narrow windows. Bring the target
  # back into its viewport using its actual arrow button before clicking.
  from PySide6.QtWidgets import QToolButton
  for _ in range(12):
   if bar.rect().contains(rect.center()):break
   direction='ScrollLeftButton' if rect.center().x()<0 else 'ScrollRightButton'
   arrow=bar.findChild(QToolButton,direction)
   self.assertIsNotNone(arrow);QTest.mouseClick(arrow,Qt.MouseButton.LeftButton);QTest.qWait(3);rect=bar.tabRect(index)
  point=QPoint(rect.center().x(),rect.top()+round((rect.height()-1)*fraction))
  window=page.window();position=bar.mapTo(window,point)
  hit=window.childAt(position)
  self.assertIs(hit,bar,'A sibling widget covers '+bar.tabText(index)+' at '+str(position)+' / '+(hit.accessibleName()+' / parent '+type(hit.parentWidget()).__name__+' / '+hit.parentWidget().objectName() if hit else 'outside'))
  QTest.mouseClick(window.windowHandle(),Qt.MouseButton.LeftButton,pos=position);QTest.qWait(3)
  self.assertEqual(page.tabs.currentIndex(),index)
 def test_tabs_clickable_at_top_center_and_bottom_after_normal_navigation(self):
  page=self.panel_at()
  for width in (1080,860):
   self.panel.resize(width,800);QTest.qWait(5)
   for fraction in (.2,.5,.85):
    for index in (0,1,2,3,4,5,2):self.click_tab(page,index,fraction)
    self.panel._show_page('conversation');self.panel._open_settings(None);QTest.qWait(5)
 def test_tabs_remain_clickable_after_task_progress_and_theme_change(self):
  page=self.panel_at('light')
  for task in (page.speech_task,page.model_task):
   task._progress('Checking local components',45);task.progress.show();task.cancel.show()
   self.click_tab(page,0);self.click_tab(page,2)
   task._done({'value':True})
   self.click_tab(page,1);self.click_tab(page,3)
  self.panel._theme_button.click();QTest.qWait(5);self.click_tab(page,2);self.click_tab(page,0)
 def test_task_footer_owns_its_controls_inside_the_requested_layout(self):
  host=QWidget();layout=QVBoxLayout(host);task=TaskWidget(EventBus(),host);task.task_footer(layout);host.show();QTest.qWait(5)
  self.assertIsNotNone(task.layout());self.assertEqual(layout.indexOf(task),0)
  for control in (task.status,task.progress,task.cancel):self.assertTrue(task.isAncestorOf(control))
  task._progress('Ready',50);task.progress.show();task.cancel.show();QTest.qWait(5);self.assertTrue(task.cancel.isVisible())
  task._done({'value':True});self.assertTrue(task.cancel.isHidden());host.close()
 def test_component_page_and_setup_footer_do_not_nest_themselves(self):
  events=EventBus();config=AppConfig();components=ComponentsWidget(config,events);components.show();QTest.qWait(5)
  self.assertTrue(components.isVisible());self.assertIs(components.status.parentWidget(),components)
  setup=SetupDialog(config,events);setup.show();QTest.qWait(5)
  self.assertIsNotNone(setup.task.layout());self.assertTrue(setup.task.isAncestorOf(setup.task.cancel));setup.reject();components.close()
