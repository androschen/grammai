"""Offline routing, GPU verification, model lifecycle, and learning controls."""
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
from core.events import EventBus
from core.local_assets import download
from core.preferences import save_config,load_config
from core.tutor import examples,save_example
from ml.context_analysis import analyze,build_body,parse_response
from ml.local_analysis import LocalAnalysisRuntime
from ui.local_ai_settings import LocalAISettings
from core.gpu_monitor import WindowsGpuMonitor

APP=QApplication.instance() or QApplication([])
PAYLOAD={'selected_sentence':'You call the shots.','original_translation':'You shoot.',
    'source_language':'en','target_language':'id','preceding_sentences':[{'text':'You decide.','language':'en'}]}
RESULT={'source_meaning':'Pembicara menyerahkan keputusan.','translation':'Kamu yang memutuskan.','explanation':'Idiom keputusan.','ambiguity':''}


def wait_for(service):
    for _ in range(150):
        QTest.qWait(10)
        if not service.busy:
            return
    raise AssertionError('Worker did not finish')


class LocalAnalysisTests(unittest.TestCase):
    def test_local_never_uses_online_adapter_or_key(self):
        runtime=Mock()
        runtime.complete.return_value=RESULT
        config=AppConfig(analysis_provider='local',analysis_endpoint='https://never.example')
        with patch('ml.context_analysis.urllib.request.build_opener') as online:
            self.assertEqual(analyze(config,PAYLOAD,runtime),RESULT)
            online.assert_not_called()
        runtime.ensure_loaded.assert_called_once()
        runtime.complete.assert_called_once()
        with self.assertRaises(ValueError):
            analyze(config,PAYLOAD)

    def test_prompt_includes_style_glossary_and_only_saved_examples(self):
        config=AppConfig(analysis_glossary='nggak = tidak',analysis_context_sentences=0)
        save_example(config,'call the shots','memutuskan','en','id')
        body=build_body(config,PAYLOAD)
        data=json.loads(body['messages'][1]['content'])
        self.assertEqual(data['preceding_sentences'],[])
        prefs=data['learning_preferences']
        self.assertEqual(prefs['explanation_language'],'id')
        self.assertEqual(prefs['speech_style'],'everyday')
        self.assertEqual(prefs['glossary'],'nggak = tidak')
        self.assertEqual(prefs['examples'][0]['preferred'],'memutuskan')

    def test_offload_requires_real_layers_and_vulkan_buffer(self):
        self.assertTrue(LocalAnalysisRuntime.verified_offload('Vulkan0 model buffer size = 2500 MiB\noffloaded 37/37 layers to GPU'))
        self.assertFalse(LocalAnalysisRuntime.verified_offload('Vulkan device detected\noffloaded 0/37 layers to GPU'))
        self.assertFalse(LocalAnalysisRuntime.verified_offload('offloaded 37/37 layers to GPU\nCUDA0 model buffer'))

    def test_missing_files_and_non_amd_device_fail_without_cpu_fallback(self):
        runtime=LocalAnalysisRuntime()
        config=AppConfig(analysis_executable='missing.exe',analysis_gguf='missing.gguf')
        with self.assertRaises(ValueError):
            runtime.ensure_loaded(config)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            exe,model=Path(folder)/'server.exe',Path(folder)/'model.gguf'
            exe.touch(); model.touch()
            config=replace(config,analysis_executable=str(exe),analysis_gguf=str(model))
            with patch('ml.local_analysis.subprocess.run',return_value=SimpleNamespace(stdout='CPU',stderr='',returncode=0)),patch('ml.local_analysis.subprocess.Popen') as spawn:
                with self.assertRaises(RuntimeError):
                    runtime.ensure_loaded(config)
                spawn.assert_not_called()

    def test_server_is_loopback_offline_and_gpu_verified(self):
        runtime=LocalAnalysisRuntime()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            exe,model=Path(folder)/'server.exe',Path(folder)/'model.gguf'
            exe.touch(); model.touch()
            config=AppConfig(analysis_executable=str(exe),analysis_gguf=str(model))
            runtime.http=Mock()
            runtime.http.open.return_value=io.BytesIO(b'{"status":"ok"}')
            process=Mock()
            process.poll.return_value=None
            with patch('ml.local_analysis.subprocess.run',return_value=SimpleNamespace(stdout='Vulkan0: AMD Radeon RX 7700 XT',stderr='',returncode=0)),patch('ml.local_analysis.subprocess.Popen',return_value=process) as spawn,patch.object(runtime,'log_tail',return_value='Vulkan0 model buffer\noffloaded 37/37 layers to GPU'):
                runtime.ensure_loaded(config)
                self.assertTrue(runtime.loaded)
                args=spawn.call_args.args[0]
                self.assertEqual(args[args.index('--host')+1],'127.0.0.1')
                self.assertIn('--offline',args)
                self.assertIn('--no-webui',args)
                self.assertEqual(args[args.index('--device')+1],'Vulkan0')
                self.assertIn('LLAMA_API_KEY',spawn.call_args.kwargs['env'])
                process.poll.return_value=0
                runtime.close()
                self.assertFalse(runtime.loaded)

    def test_cancel_and_idle_unload_preserve_worker_ownership(self):
        config=AppConfig(analysis_idle_minutes=1)
        service=AnalysisService(config=config)
        service.runtime=Mock()
        service.runtime.loaded=True
        service.runtime.status='GPU verified'
        service.runtime.last_used=0
        service._idle_unload()
        wait_for(service)
        service.runtime.close.assert_called_once()
        self.assertFalse(service.busy)
        service.timer.stop()

    def test_gpu_counters_filter_other_processes(self):
        engines=[('pid_42_luid_1_eng_0_engtype_Compute',63),('pid_99_luid_1_eng_1_engtype_3D',90)]
        memory=[('pid_42_luid_1_phys_0',1024**3),('pid_99_luid_1_phys_0',2*1024**3)]
        self.assertEqual(WindowsGpuMonitor.aggregate(engines,memory,{42}),{'gpu_percent':63,'gpu_memory_mb':1024})

    def test_shutdown_cancels_local_connection_and_closes_runtime(self):
        service=AnalysisService(config=AppConfig())
        service.runtime=Mock()
        service.runtime.loaded=False
        service.runtime.status='Unloaded'
        worker=Mock()
        worker.config=AppConfig()
        worker.operation='analyze'
        service.worker=worker
        service.shutdown()
        worker.requestInterruption.assert_called_once()
        service.runtime.interrupt.assert_called_once()
        self.assertFalse(service.request('late',AppConfig(),PAYLOAD))
        service.worker=None
        service.runtime.close()

    def test_cache_changes_with_learning_preferences(self):
        config=AppConfig()
        service=AnalysisService()
        with patch('core.analysis.analyze',return_value=RESULT) as model:
            service.request('a',config,PAYLOAD); wait_for(service)
            service.request('b',config,PAYLOAD); QTest.qWait(10)
            self.assertEqual(model.call_count,1)
            config.analysis_translation_style='literal'
            service.request('c',config,PAYLOAD); wait_for(service)
            self.assertEqual(model.call_count,2)
        service.timer.stop()

    def test_preferences_and_examples_are_bounded(self):
        config=AppConfig(analysis_provider='local',analysis_glossary='slang',analysis_speech_style='everyday')
        for i in range(15):
            save_example(config,str(i),'meaning','en','id')
        self.assertEqual(len(examples(config)),10)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            save_config(config)
            loaded=load_config()
            self.assertEqual(len(examples(loaded)),10)
            self.assertEqual(loaded.analysis_provider,'local')
            self.assertEqual(loaded.analysis_glossary,'slang')

    def test_download_checksum_failure_does_not_install(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path=Path(folder)/'model.gguf'
            with patch('core.local_assets.urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
                with self.assertRaises(ValueError):
                    download('https://example.test',path,3,'not-a-checksum',lambda *args:None,lambda:False)
            self.assertFalse(path.exists())

    def test_invalid_or_truncated_response_is_not_applied(self):
        for content in ('[]','{"translation":""}'):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({'choices':[{'message':{'content':content}}]}).encode())
        with self.assertRaises(ValueError):
            parse_response(json.dumps({'choices':[{'finish_reason':'length','message':{'content':json.dumps(RESULT)}}]}).encode())

    def test_settings_apply_waits_for_explicit_apply(self):
        config=AppConfig()
        widget=LocalAISettings(config,EventBus())
        widget.glossary.setPlainText('informal words')
        widget.enabled.setChecked(True)
        self.assertEqual(config.analysis_glossary,'')
        draft=widget.apply_to(replace(config))
        self.assertEqual(draft.analysis_glossary,'informal words')
        self.assertEqual(draft.analysis_provider,'local')
        self.assertTrue(draft.analysis_enabled)
        widget.dispose()
        widget.deleteLater()
