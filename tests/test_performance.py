"""Performance settings, monitoring, benchmark and overlay regressions."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QThread, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core.config import AppConfig, QualityMode
from core.events import EventBus, SubtitleUpdate
from core.preferences import load_config, save_config, write_json
from core.benchmark import compare_results
from core.pipeline import TranslationPipeline
from core.performance import PerformanceMonitor
from ml.vulkan_engine import VulkanWhisper
from ui.settings import SettingsDialog
from tests_fakes import FakeCapture, SlowEngine

APP = QApplication.instance() or QApplication([])


class PreferencesTests(unittest.TestCase):
    def test_roundtrip_and_defensive_load(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder, patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            config=AppConfig(theme="light",show_overlay=False,cpu_threads=3,translation_threads=1,quality_mode=QualityMode.FAST)
            save_config(config)
            loaded=load_config()
            self.assertFalse(loaded.show_overlay)
            self.assertEqual(loaded.theme,"light")
            self.assertEqual(loaded.cpu_threads,3)
            self.assertEqual(loaded.quality_mode,QualityMode.FAST)
            self.assertEqual(loaded.beam_size,1)
            write_json('preferences.json',{'cpu_threads':999,'backend':'imaginary','quality_mode':'broken','noise_threshold':-3.})
            loaded=load_config()
            self.assertEqual(loaded.cpu_threads,16)
            self.assertEqual(loaded.backend,'cpu')
            self.assertEqual(loaded.noise_threshold,.01)

    def test_benchmark_comparison_checks_fixture(self):
        previous={'fixture':'a','protocol':1,'total_ms':100}
        self.assertIn('not directly comparable',compare_results({'fixture':'b','protocol':1,'total_ms':50},previous))
        self.assertIn('50% faster',compare_results({'fixture':'a','protocol':1,'total_ms':50},previous))
        self.assertIn('Similar',compare_results({'fixture':'a','protocol':1,'total_ms':98},previous))


class SettingsTests(unittest.TestCase):
    def test_expensive_changes_wait_for_apply_and_cancel_restores_gate(self):
        c,e=AppConfig(),EventBus()
        with patch('ui.settings.list_audio_sources',return_value=[]):
            dialog=SettingsDialog(c,e)
        dialog._threads.setValue(2)
        self.assertEqual(c.cpu_threads,4)
        dialog._preview_gate(30)
        self.assertEqual(c.noise_threshold,.3)
        dialog.reject()
        self.assertEqual(c.noise_threshold,.12)
        self.assertEqual(c.cpu_threads,4)
        dialog.deleteLater()

    def test_apply_and_invalid_gpu_selection(self):
        c,e=AppConfig(),EventBus()
        with patch('ui.settings.list_audio_sources',return_value=[]):
            dialog=SettingsDialog(c,e,page=3)
        self.assertEqual(dialog.tabs.count(),6)
        dialog._threads.setValue(2)
        self.assertTrue(dialog.apply())
        self.assertEqual(c.cpu_threads,2)
        dialog._backend.setCurrentIndex(1)
        self.assertFalse(dialog.apply())
        self.assertEqual(c.backend,'cpu')
        dialog.reject()
        dialog.deleteLater()

    def test_overlay_toggle_does_not_stop_translation(self):
        from main import GrammAIApp
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder, patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            app=GrammAIApp(AppConfig())
            app._on_subtitles_toggled(True)
            app._on_overlay_toggled(False)
            self.assertTrue(app._pipeline.inference_requested)
            self.assertFalse(app._overlay.isVisible())
            app._on_subtitles_toggled(False)
            app._preference_timer.stop()
            app._monitor.timer.stop()
            app._pipeline._timer.stop()
            app._panel.mark_quitting()
            app._panel.close()
            app._overlay.close()


class AppearanceTests(unittest.TestCase):
    def test_existing_history_rethemes_and_details_remain_accessible(self):
        from ui.panel import ControlPanel
        from ui.history import HistoryCard
        from ui.theme import style_for
        c,e=AppConfig(),EventBus()
        with patch('ui.panel.list_audio_sources',return_value=[]):
            panel=ControlPanel(c,e)
        update=SubtitleUpdate('ni hao','Chinese target','Hello')
        panel._on_subtitle(update)
        row=next(panel._history_panel._list.itemAt(i).widget() for i in range(panel._history_panel._list.count()) if isinstance(panel._history_panel._list.itemAt(i).widget(),HistoryCard))
        opened=[]
        e.learning_requested.connect(opened.append)
        row.details_button.click()
        self.assertEqual(opened,[update])
        panel._theme_picker.setCurrentIndex(panel._theme_picker.findData('light'))
        self.assertEqual(c.theme,'light')
        self.assertEqual(panel.styleSheet(),style_for('light'))
        self.assertEqual(panel._history_panel._card_count(),1)
        self.assertFalse(panel._toggle.isChecked())
        panel.mark_quitting()
        panel.close()


class VulkanTests(unittest.TestCase):
    def test_requires_local_files(self):
        with self.assertRaisesRegex(RuntimeError,'Choose a Vulkan'):
            VulkanWhisper(AppConfig(backend='vulkan')).start()

    def test_upload_is_wav_and_normalizes_verbose_language(self):
        import numpy as np
        backend=VulkanWhisper(AppConfig())
        backend.url='http://127.0.0.1:12345'
        backend.http=Mock()
        response=io.BytesIO(json.dumps({'text':'Hello','language':'english'}).encode())
        backend.http.open.return_value=response
        text,language=backend.transcribe(np.zeros(16000,dtype=np.float32),'auto')
        self.assertEqual((text,language),('Hello','en'))
        request=backend.http.open.call_args.args[0]
        self.assertIn(b'RIFF',request.data)
        self.assertIn(b'name="language"\r\n\r\nauto',request.data)


class FakeBenchmark(QThread):
    result=Signal(object)
    progress=Signal(str)
    overlap=False
    def __init__(self,config):
        super().__init__()
    def run(self):
        type(self).overlap=SlowEngine.active>0
        self.msleep(70)
        self.result.emit({'test':True})


class PerformanceTests(unittest.TestCase):
    def test_monitor_reports_machine_share_and_keeps_inference_fields(self):
        pipeline=Mock(inference_requested=True,processing_live=True,backlog_seconds=.4,sample_rate=16000,active_backend='CPU / int8')
        events=EventBus()
        monitor=PerformanceMonitor(events,pipeline)
        process=Mock()
        process.children.return_value=[]
        process.cpu_percent.return_value=400
        process.memory_info.return_value=Mock(rss=100*1024**2)
        monitor._process=process
        monitor._psutil=Mock()
        monitor._psutil.cpu_count.return_value=16
        monitor._psutil.Error=RuntimeError
        readings=[]
        events.metrics_changed.connect(readings.append)
        events.metrics_changed.emit({'kind':'inference','stt_ms':100,'mt_ms':50,'total_ms':150})
        events.audio_dropped.emit(1600)
        monitor.sample()
        self.assertEqual(readings[-1]['cpu_percent'],25)
        self.assertEqual(readings[-1]['memory_mb'],100)
        self.assertEqual(readings[-1]['stt_ms'],100)
        self.assertEqual(readings[-1]['dropped_seconds'],.1)
        self.assertIsNone(readings[-1]['gpu_percent'])
        monitor.timer.stop()

    def test_benchmark_waits_for_worker_and_resumes(self):
        SlowEngine.active=SlowEngine.maximum=0
        c,e=AppConfig(),EventBus()
        with patch('core.pipeline.LoopbackCapture',FakeCapture),patch('core.benchmark.BenchmarkWorker',FakeBenchmark):
            pipeline=TranslationPipeline(c,e,SlowEngine())
            results=[]
            e.benchmark_finished.connect(results.append)
            pipeline.start()
            QTest.qWait(70)
            pipeline.request_benchmark(c)
            for _ in range(100):
                if results and not e.property("benchmark_busy"):
                    break
                QTest.qWait(20)
            self.assertFalse(FakeBenchmark.overlap)
            self.assertTrue(results)
            self.assertTrue(pipeline.inference_requested)
            finished=[]
            pipeline.shutdown_finished.connect(lambda:finished.append(True))
            pipeline.stop()
            for _ in range(30):
                if finished:
                    break
                QTest.qWait(30)
            self.assertTrue(finished)


if __name__=='__main__':
    unittest.main()
