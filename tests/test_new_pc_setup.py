"""Fresh-profile and missing-model recovery, without developer caches or real downloads."""
import os,tempfile,unittest,json,io,zipfile,hashlib
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,Mock
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.preferences import write_json,load_config
from core.readiness import setup_required,missing_models
from core.setup import learning_components
from core.components import ComponentManager,Component,Asset
from ui.settings import SettingsPage
from ui.model_setup import SetupDialog,active_jobs,cancel_jobs
APP=QApplication.instance() or QApplication([])
def settle(predicate):
 for _ in range(800):
  if predicate():return
  QTest.qWait(10)
 raise AssertionError('Background setup did not finish')
class NewPCSetupTests(unittest.TestCase):
 def setUp(self):
  self.windows=set(APP.topLevelWidgets());self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
  self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name,GRAMMAI_MODELS_DIR=str(self.folder/'models'),HF_HUB_CACHE=str(self.folder/'cache'));self.env.start()
  self.home=patch('pathlib.Path.home',return_value=self.folder);self.home.start()
  from core.components import catalog
  self.specs=patch('core.components.catalog',return_value={key:replace(spec,assets=tuple(replace(a,size=7) for a in spec.assets)) if spec.kind!='runtime' else spec for key,spec in catalog().items()});self.specs.start()
  self.hardware=patch('ui.model_setup.system_info',return_value={'cpu':'Test CPU','ram_bytes':16*1024**3,'display_adapters':['NVIDIA RTX test']});self.hardware.start()
 def tearDown(self):
  cancel_jobs();settle(lambda:not active_jobs())
  from PySide6.QtCore import QCoreApplication,QEvent
  for w in APP.topLevelWidgets():
   if w not in self.windows and w.parentWidget() is None:
    if hasattr(w,'dispose'):w.dispose()
    w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
  self.hardware.stop();self.specs.stop();self.home.stop();self.env.stop();self.temp.cleanup()
 def test_fresh_and_partial_preferences_cannot_skip_setup(self):
  self.assertTrue(setup_required(load_config()));write_json('preferences.json',{'theme':'dark'});self.assertFalse(load_config().setup_completed);self.assertTrue(setup_required(load_config()))
  write_json('preferences.json',{'setup_completed':True,'vulkan_model':'old-computer.bin','backend':'vulkan'})
  self.assertTrue(setup_required(load_config()));self.assertIn('Speech recognition model and runtime',missing_models(load_config()))
 def test_valid_existing_install_does_not_rerun_setup(self):
  config=AppConfig(setup_completed=True,speech_model_id='speech-cpu',translation_enabled=False)
  with patch('core.speech_models.installed',return_value=True):self.assertFalse(setup_required(config))
 def test_missing_learning_files_prompt_repair_when_enabled(self):
  c=AppConfig(setup_completed=True,speech_model_id='speech-cpu',translation_enabled=False,analysis_enabled=True,analysis_executable='missing.exe',analysis_gguf='missing.gguf')
  with patch('core.speech_models.installed',return_value=True):self.assertIn('Learning / refinement model and runtime',missing_models(c))
 def test_nvidia_recommendation_does_not_require_ai_runtime(self):
  with patch('ui.model_setup.probe_devices',side_effect=AssertionError('No executable is installed')):
   d=SetupDialog(AppConfig());settle(lambda:d._detect_done)
  self.assertTrue(d._gpu_available);self.assertEqual(d.speech.currentData(),'speech-turbo');self.assertEqual(d.processing.currentData(),'auto');self.assertTrue(d.fast.isChecked());self.assertTrue(d.ai.isChecked());self.assertIn('NVIDIA',d.hardware.text());self.assertFalse(d.finish.isEnabled());d.reject()
 def test_learning_download_installs_model_and_runtimes_without_manual_paths(self):
  events=EventBus();config=AppConfig(processing_mode='auto')
  with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsPage(config,events)
  self.assertFalse(d.learning_download.isHidden());installed=[]
  with patch('core.components.ComponentManager.install',side_effect=lambda key,*args:installed.append(key)):
   d._download_learning();settle(lambda:d.learning_task.job is None)
  self.assertEqual(installed,learning_components('auto'));self.assertEqual(installed.count('qwen'),1);self.assertEqual(d._learning_choice.currentData(),'qwen');self.assertTrue(d.analysis_settings.enabled.isChecked());self.assertEqual(config.learning_model_id,'external');self.assertTrue(d.save_changes.isEnabled());d.dispose()
 def test_cpu_only_mode_is_explicit_and_gpu_action_requires_save(self):
  c=AppConfig(processing_mode='cpu');events=EventBus()
  with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsPage(c,events)
  d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-turbo'))
  self.assertFalse(d.try_gpu.isHidden());self.assertIn('CPU only',d._speech_note.text());d.try_gpu.click();self.assertEqual(d._processing.currentData(),'gpu');self.assertEqual(c.processing_mode,'cpu');self.assertTrue(d.save_changes.isEnabled());d.dispose()
 def test_nvidia_adapter_enumeration_does_not_claim_runtime_compatibility(self):
  from core.hardware import display_adapters
  display_adapters.cache_clear()
  try:
   with patch('core.hardware.platform.system',return_value='Windows'),patch('core.hardware.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='["NVIDIA RTX 4060","Microsoft Basic Display Adapter"]')):
    self.assertEqual(display_adapters(),['NVIDIA RTX 4060'])
  finally:display_adapters.cache_clear()
 def test_component_roundtrip_uses_local_files_and_preserves_registry(self):
  # A tiny, real pinned archive exercises extraction and registration on an empty PC.
  data=io.BytesIO()
  with zipfile.ZipFile(data,'w') as z:z.writestr('runtime/server.exe',b'executable fixture');z.writestr('runtime/engine.dll',b'library fixture')
  raw=data.getvalue();asset=Asset('runtime.zip','https://example.invalid/runtime.zip',len(raw),hashlib.sha256(raw).hexdigest());spec=Component('fixture','Fixture runtime','runtime','test',(asset,),'server.exe',('learning',),'test','MIT')
  def local_fetch(item,path,progress,cancelled):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
  manager=ComponentManager()
  with patch('core.components.catalog',return_value={'fixture':spec}),patch('core.components.fetch',side_effect=local_fetch):
   path=manager.install('fixture');self.assertTrue(path.is_file());self.assertEqual(manager.records()['fixture']['path'],str(path));self.assertTrue(manager.verify('fixture'));self.assertEqual(ComponentManager().path('fixture'),path)

 def test_gpu_failure_is_explained_and_explicit_gpu_mode_never_silently_falls_back(self):
  from ml.whisper_engine import WhisperEngine
  files={key:self.folder/key for key in ('speech-runtime','speech-turbo','speech-cpu')}
  for p in files.values():p.touch()
  for mode in ('auto','gpu'):
   config=AppConfig(speech_model_id='speech-turbo',processing_mode=mode,backend='vulkan')
   with patch('core.components.ComponentManager.availability',return_value='installed'),patch('core.components.resolve',side_effect=files.get),patch('ml.vulkan_engine.VulkanWhisper') as gpu,patch('faster_whisper.WhisperModel') as cpu:
    gpu.return_value.start.side_effect=RuntimeError('NVIDIA Vulkan driver could not start')
    engine=WhisperEngine(config)
    if mode=='auto':
     engine.ensure_loaded();self.assertIn('CPU',engine.active_backend);self.assertIn('NVIDIA Vulkan driver',engine.processing_note);cpu.assert_called_once()
    else:
     with self.assertRaises(RuntimeError):engine.ensure_loaded()
     cpu.assert_not_called()
    engine.close()
 def test_gpu_detection_requires_allocation_not_just_nvidia_name(self):
  from ml.vulkan_engine import VulkanWhisper
  self.assertFalse(VulkanWhisper.gpu_allocated('Vulkan0: NVIDIA RTX 4060'))
  self.assertTrue(VulkanWhisper.gpu_allocated('Vulkan0: NVIDIA RTX 4060 model buffer size 600 MB'))

 def test_first_run_install_test_finish_and_restart_are_one_in_app_flow(self):
  d=SetupDialog(AppConfig());settle(lambda:d._detect_done);d.preset(False);d.fast.setChecked(False);d.show_step(1)
  def install(identifier,progress,cancelled):
   self.assertEqual(identifier,'speech-cpu');folder=self.folder/'models/base-fixture';folder.mkdir(parents=True,exist_ok=True)
   for name in ('model.bin','config.json','tokenizer.json','vocabulary.txt'):(folder/name).write_bytes(b'fixture')
   ComponentManager().register('speech-cpu',folder/'model.bin');return folder/'model.bin'
  result={'backend':'CPU / int8','speech_ms':100,'audio_seconds':3.,'keeps_up':True,'memory_mb':50}
  with patch('core.components.ComponentManager.install',side_effect=install),patch('ui.model_setup.test_configuration',return_value=result):
   d.install_and_test();settle(lambda:d.task.job is None)
  self.assertEqual(d.pages.currentIndex(),2);self.assertTrue(d.finish.isEnabled());d.accept_setup()
  restored=load_config();self.assertTrue(restored.setup_completed);self.assertEqual(restored.speech_model_id,'speech-cpu');self.assertFalse(setup_required(restored))
