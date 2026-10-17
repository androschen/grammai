import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.analysis import AnalysisService
from core.config import AppConfig
from core.events import EventBus, SubtitleUpdate
from core.history import SessionHistory
from core.performance import PerformanceMonitor
from core.preferences import save_config, load_config
from ml.context_analysis import analyze, validate_endpoint
from ui.analysis import preceding_context
from ui.learning import StudyDialog
from ui.performance import LivePerformance

APP=QApplication.instance() or QApplication([])


class ContextTests(unittest.TestCase):
    def test_only_preceding_five_in_same_context(self):
        history=SessionHistory()
        items=[SubtitleUpdate('',str(i),str(i)) for i in range(9)]
        for item in items:
            history.append(item)
        self.assertEqual([item['text'] for item in preceding_context(history,items[7])],['2','3','4','5','6'])
        history.begin_context()
        selected=SubtitleUpdate('','new','new')
        history.append(selected)
        self.assertEqual(preceding_context(history,selected),[])

    def test_api_payload_no_audio_and_validated_result(self):
        config=AppConfig(analysis_provider='online',analysis_enabled=True,analysis_endpoint='https://example.test/v1/chat/completions',analysis_model='tutor')
        value={'source_meaning':'The speaker decides.','translation':'refined','explanation':'idiom','ambiguity':'unclear subject'}
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(value)}}]}).encode())
        opener=Mock()
        opener.open.return_value=response
        with patch.dict(os.environ,GRAMMAI_ANALYSIS_API_KEY='test-key'),patch('ml.context_analysis.urllib.request.build_opener',return_value=opener):
            self.assertEqual(analyze(config,{'selected_sentence':'hello','source_language':'en','target_language':'id'}),value)
        request=opener.open.call_args.args[0]
        self.assertNotIn('audio',json.loads(request.data))
        self.assertEqual(request.get_header('Authorization'),'Bearer test-key')
        for url in ('http://example.test','https://user:secret@example.test','https://example.test/?key=secret'):
            with self.assertRaises(ValueError):
                validate_endpoint(url)

    def test_cache_and_cancel_discard_late_results(self):
        service=AnalysisService()
        received=[]
        service.completed.connect(lambda token,value:received.append((token,value)))
        config=AppConfig()
        value={'translation':'yes','explanation':'meaning','ambiguity':''}
        def wait():
            for _ in range(100):
                QTest.qWait(10)
                if not service.busy:
                    return
            self.fail('worker did not finish')
        with patch('core.analysis.analyze',return_value=value) as api:
            self.assertTrue(service.request('first',config,{'selected_sentence':'hello'}))
            wait()
            self.assertTrue(service.request('cached',config,{'selected_sentence':'hello'}))
            QTest.qWait(10)
            self.assertEqual(api.call_count,1)
            service.request('cancelled',config,{'selected_sentence':'other'})
            service.cancel('cancelled')
            wait()
        self.assertEqual([token for token,_ in received],['first','cached'])

    def test_apply_is_explicit_and_stale_edits_rejected(self):
        config=AppConfig()
        service=AnalysisService()
        events=EventBus()
        update=SubtitleUpdate('','old translation','original',source_language='en',target_language='zh')
        dialog=StudyDialog(update,config,events,Mock(),Mock(),analysis=service,history=SessionHistory())
        widget=dialog.analysis_widget
        widget.token='request'
        widget.payload={'original_translation':'old translation','selected_sentence':'original','source_language':'en','target_language':'zh'}
        widget._comparison_translation='old translation'
        changed=[]
        events.subtitle_corrected.connect(changed.append)
        value={'source_meaning':'Source intent','translation':'refined','explanation':'context','ambiguity':''}
        widget._finished('request',value)
        self.assertEqual(changed,[])
        dialog.text.setPlainText('edited')
        widget._apply()
        self.assertEqual(changed,[])
        dialog.text.setPlainText('original')
        widget.token='retry'
        widget._finished('retry',value)
        widget._apply()
        self.assertEqual(changed[0].target_text,'refined')
        self.assertEqual(changed[0].uid,update.uid)
        dialog.reject()

    def test_preferences_do_not_store_api_key(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder,GRAMMAI_ANALYSIS_API_KEY='never-write-this'):
            save_config(AppConfig(analysis_model='model',analysis_enabled=True))
            self.assertTrue(load_config().analysis_enabled)
            self.assertNotIn('never-write-this',(Path(folder)/'preferences.json').read_text())

    def test_monitor_history_is_bounded_and_charts_render(self):
        events=EventBus()
        pipeline=SimpleNamespace(inference_requested=False,backlog_seconds=0,sample_rate=16000,active_backend='CPU',active_model='base')
        monitor=PerformanceMonitor(events,pipeline)
        monitor.timer.stop()
        monitor._process=None
        with patch('core.performance.monotonic',side_effect=range(150)):
            for _ in range(150):
                monitor.sample()
        self.assertEqual(len(events.property('resource_history')),121)
        self.assertEqual(events.property('resource_history')[0][0],29)
        widget=LivePerformance(events)
        widget.resize(600,650)
        self.assertFalse(widget.grab().isNull())
        widget.deleteLater()
