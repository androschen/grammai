"""Desktop panel navigation, safe version diffs and installed model locations."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.paths import model_root,model_candidates
from core.preferences import write_json
from audio.replay import ReplayStore
from ui.learning import StudyDialog
from ui.panel import ControlPanel
from ui.sentence_view import highlighted

APP=QApplication.instance() or QApplication([])


class DesktopDetailsTests(unittest.TestCase):
    def test_side_panel_switches_without_modal_dialog_and_releases_connections(self):
        config,events=AppConfig(),EventBus()
        with patch('ui.panel.list_audio_sources',return_value=[]):
            panel=ControlPanel(config,events)
        make=lambda text:StudyDialog(SubtitleUpdate('',text,text,source_language='en'),config,events,ReplayStore(),Mock(),panel)
        first=make('first');panel.open_sentence_details(first)
        self.assertFalse(first.isWindow())
        self.assertTrue(first.text.isReadOnly())
        self.assertEqual(first.source_display.text(),'first')
        first.edit.setChecked(True)
        self.assertFalse(first.text.isReadOnly())
        second=make('second');panel.open_sentence_details(second)
        self.assertIs(panel._details_view,second)
        self.assertEqual(panel._details_layout.count(),1)
        second.reject()
        self.assertIsNone(panel._details_view)
        self.assertTrue(panel._details_host.isHidden())
        panel.mark_quitting();panel.close()
        QTest.qWait(10)

    def test_diff_escapes_transcript_markup_and_highlights_changes(self):
        old,new=highlighted('<script>old</script>','<script>new</script>')
        self.assertNotIn('<script>',old+new)
        self.assertIn('&lt;script&gt;',old)
        self.assertIn('background:',new)

    def test_frozen_defaults_are_writable_and_existing_cache_is_reused(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            data=Path(folder)/'profile';legacy=Path(folder)/'existing';legacy.mkdir()
            with patch.dict(os.environ,GRAMMAI_DATA_DIR=str(data)):
                write_json('model-locations.json',{'root':str(legacy)})
                with patch('sys.frozen',True,create=True),patch.dict(os.environ,{},clear=False):
                    self.assertEqual(model_root(),data/'models')
                    self.assertEqual(model_candidates('speech'),[data/'models/speech',legacy/'speech'])

    def test_single_instance_activates_existing_server(self):
        from core.desktop import SingleInstance
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            first=SingleInstance();second=SingleInstance()
            self.assertTrue(first.acquire())
            activated=[];first.on_activate(lambda:activated.append(True))
            self.assertFalse(second.acquire())
            for _ in range(10):
                QTest.qWait(10)
                if activated:break
            self.assertTrue(activated)
            first.server.close()


if __name__=='__main__':
    unittest.main()
