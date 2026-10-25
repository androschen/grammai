"""Hardware-neutral runtime selection, legacy migration and explicit setup actions."""
import io,json,os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.hardware import vulkan_devices,select_device
from core.setup import required_components,select_configuration
from core.preferences import load_config,save_config
from ml.local_analysis import LocalAnalysisRuntime
APP=QApplication.instance() or QApplication([])


def settle(predicate):
    for _ in range(200):
        if predicate():return
        QTest.qWait(10)
    raise AssertionError('Background task did not complete')


class ModularSetupTests(unittest.TestCase):
    def setUp(self):
        self.windows=set(APP.topLevelWidgets())
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=self.temp.name,GRAMMAI_MODELS_DIR=str(self.folder/'models'),HF_HUB_CACHE=str(self.folder/'cache'));self.env.start();self.home=patch('pathlib.Path.home',return_value=self.folder);self.home.start()
    def tearDown(self):
        from ui.model_setup import active_jobs,cancel_jobs
        cancel_jobs();settle(lambda:not active_jobs())
        for widget in APP.topLevelWidgets():
            if widget not in self.windows and widget.parentWidget() is None:widget.close();widget.deleteLater()
        from PySide6.QtCore import QCoreApplication,QEvent
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.home.stop();self.env.stop();self.temp.cleanup()
    def test_devices_accept_amd_intel_nvidia_and_preference(self):
        devices=vulkan_devices('Vulkan0: Intel Arc\nVulkan1: NVIDIA RTX\nVulkan2: AMD Radeon')
        self.assertEqual(len(devices),3);self.assertEqual(select_device(devices,'Vulkan1')['name'],'NVIDIA RTX');self.assertIsNone(select_device([]))
    def test_external_model_paths_do_not_depend_on_component_registry(self):
        (self.folder/'components.json').write_text('invalid',encoding='utf8')
        config=AppConfig(analysis_executable=str(self.folder/'server.exe'),analysis_gguf=str(self.folder/'model.gguf'))
        runtime=LocalAnalysisRuntime();exe,model=runtime.paths(config)
        self.assertEqual(exe,Path(config.analysis_executable));self.assertEqual(model,Path(config.analysis_gguf))
    def test_legacy_preferences_preserve_models_and_skip_onboarding(self):
        from core.preferences import write_json
        write_json('preferences.json',{'backend':'vulkan','vulkan_model':'original.bin','analysis_gguf':'original.gguf','cpu_threads':6})
        c=load_config();self.assertTrue(c.setup_completed);self.assertEqual(c.processing_mode,'legacy');self.assertEqual(c.vulkan_model,'original.bin');self.assertEqual(c.cpu_threads,6)
        self.assertEqual(c.speech_model_id,'external')
    def test_fresh_setup_requires_explicit_confirmation_and_quality_does_not_replace_model(self):
        self.assertFalse(load_config().setup_completed)
        c=AppConfig(speech_model_id='speech-turbo',model_size='chosen');c.apply_quality();self.assertEqual(c.model_size,'chosen')
        ids=required_components('speech-turbo','auto',True,backup=True)
        self.assertEqual(ids.count('qwen'),1);self.assertIn('ai-cpu',ids);self.assertIn('speech-cpu',ids)
    def runtime_case(self,mode,devices,log):
        exe=self.folder/'server.exe';model=self.folder/'model.gguf';exe.touch();model.touch()
        runtime=LocalAnalysisRuntime();runtime.http=Mock();runtime.http.open.return_value=io.BytesIO(b'{"status":"ok"}')
        process=Mock();process.poll.return_value=None
        with patch('core.hardware.subprocess.run',return_value=SimpleNamespace(stdout=devices,stderr='',returncode=0)),patch('ml.local_analysis.subprocess.Popen',return_value=process) as spawn,patch.object(runtime,'log_tail',return_value=log):
            runtime.ensure_loaded(AppConfig(processing_mode=mode,analysis_executable=str(exe),analysis_gguf=str(model),cpu_threads=2))
            command=spawn.call_args.args[0]
            process.poll.return_value=0;runtime.close();return command
    def test_learning_can_share_qwen_with_fast_cpu_translation_and_assessment_includes_both_stages(self):
        from core.setup import assess_realtime
        config=select_configuration(AppConfig(),'speech-cpu','cpu',ai=True,fast=True)
        self.assertTrue(config.analysis_enabled);self.assertEqual(config.translation_mode,'fast')
        self.assertFalse(assess_realtime({'speech_ms':1000,'translation_ms':4000,'audio_seconds':3}))
        self.assertTrue(assess_realtime({'speech_ms':1000,'translation_ms':300,'audio_seconds':3}))
    def test_cpu_ai_uses_zero_offload_and_never_requires_gpu(self):
        command=self.runtime_case('cpu','CPU','CPU model buffer')
        self.assertEqual(command[command.index('--device')+1],'none');self.assertEqual(command[command.index('--n-gpu-layers')+1],'0');self.assertEqual(command[command.index('--threads')+1],'2')
    def test_nvidia_vulkan_is_accepted_without_amd_name(self):
        command=self.runtime_case('gpu','Vulkan0: NVIDIA RTX 4070','Vulkan0 model buffer\noffloaded 20/37 layers to GPU')
        self.assertEqual(command[command.index('--device')+1],'Vulkan0');self.assertIn('--fit',command)
    def test_cpu_selection_retains_existing_ggml_speech_model(self):
        from ml.whisper_engine import WhisperEngine
        config=AppConfig(processing_mode='cpu',backend='vulkan',vulkan_executable='existing.exe',vulkan_model='my-selected.bin')
        with patch('ml.vulkan_engine.VulkanWhisper') as runtime:
            engine=WhisperEngine(config);engine.ensure_loaded()
            self.assertEqual(runtime.call_args.args[0].vulkan_model,'my-selected.bin')
            self.assertTrue(runtime.return_value.start.call_args.kwargs['cpu_only']);self.assertEqual(engine.active_backend,'CPU / whisper.cpp');engine.close()
    def test_managed_model_status_uses_registry_instead_of_empty_legacy_fields(self):
        from ui.settings import SettingsDialog
        names={'speech-turbo':'ggml-large-v3-turbo.bin','speech-runtime':'whisper-server.exe','qwen':'Qwen.gguf','ai-cpu':'llama-server.exe'}
        paths={key:self.folder/name for key,name in names.items()}
        for path in paths.values():path.touch()
        with patch('ui.settings.list_audio_sources',return_value=[]),patch('core.components.resolve',side_effect=lambda key:paths.get(key)):
            d=SettingsDialog(AppConfig(),EventBus());d._processing.setCurrentIndex(d._processing.findData('cpu'));d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-turbo'));d._learning_choice.setCurrentIndex(d._learning_choice.findData('qwen'))
            self.assertNotIn('Files missing',d._selected_models.text());self.assertNotIn('Local AI files missing',d._selected_models.text());d.reject()
    def test_setup_constructor_never_downloads_and_preserves_cards(self):
        from ui.model_setup import SetupDialog,active_jobs
        cards=self.folder/'phrases.json';cards.write_text('[{"id":"one","native_text":"hello"}]',encoding='utf8');before=cards.read_bytes()
        with patch.object(SetupDialog,'detect_hardware',return_value={'cpu':'Test CPU','ram_bytes':8*1024**3,'devices':[]}),patch('core.components.fetch',side_effect=AssertionError('Unexpected download')):
            d=SetupDialog(AppConfig());d.show();settle(lambda:not active_jobs());self.assertFalse(d.finish.isEnabled());self.assertEqual(cards.read_bytes(),before);d.reject()
    def test_live_pipeline_blocks_component_changes(self):
        from ui.model_setup import TaskWidget
        events=EventBus();events.setProperty('translation_running',True);w=TaskWidget(events)
        self.assertFalse(w.start_job(lambda p,c:self.fail('Must not run')));self.assertIn('Pause',w.status.text())
    def test_embedded_settings_cannot_apply_a_missing_managed_model(self):
        from ui.settings import SettingsPage
        with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsPage(AppConfig(),EventBus())
        d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-cpu'));self.assertFalse(d.apply());d.dispose();d.close()
    def test_setup_three_steps_preserve_choices_until_real_test_succeeds(self):
        from ui.model_setup import SetupDialog,active_jobs
        with patch.object(SetupDialog,'detect_hardware',return_value={'cpu':'Test CPU','ram_bytes':8*1024**3,'devices':[]}):
            d=SetupDialog(AppConfig());d.show();settle(lambda:not active_jobs());d.essential.click();d.continue_button.click()
            self.assertEqual(d.pages.currentIndex(),1);self.assertFalse(d.ai.isChecked());self.assertFalse(d.fast.isChecked());self.assertFalse(d.finish.isEnabled())
            d.back.click();self.assertEqual(d.pages.currentIndex(),0);d.reject()
    def test_selected_managed_model_requires_install_and_manager_is_inline(self):
        from ui.settings import SettingsDialog
        with patch('ui.settings.list_audio_sources',return_value=[]):d=SettingsDialog(AppConfig(),EventBus())
        d._speech_choice.setCurrentIndex(d._speech_choice.findData('speech-cpu'))
        with self.assertRaises(ValueError):d._draft()
        d.manage_components.click();self.assertFalse(d.component_manager.isWindow());self.assertTrue(d._models_normal.isHidden());d.component_manager.back.click();self.assertEqual(d.component_stack.currentWidget(),d._models_normal);d.reject()

    def settings_window(self,embedded=False):
        from ui.settings import SettingsPage,SettingsDialog
        with patch('ui.settings.list_audio_sources',return_value=[]):
            d=(SettingsPage if embedded else SettingsDialog)(AppConfig(),EventBus(),page=3)
        d.resize(1000,850);d.show();QTest.qWait(25)
        return d

    def pointer_click(self,window,control):
        from PySide6.QtCore import Qt
        point=control.mapTo(window,control.rect().center())
        self.assertTrue(control.isVisible());self.assertIs(window.childAt(point),control,
            'Another widget intercepts input intended for '+control.metaObject().className())
        QTest.mouseClick(window.windowHandle(),Qt.MouseButton.LeftButton,pos=point)
        QTest.qWait(20)

    def test_models_pointer_clicks_open_combos_in_embedded_and_dialog_settings(self):
        for embedded in (False,True):
            d=self.settings_window(embedded)
            for control in (d._processing,d._speech_choice,d._translation_mode,d._learning_choice):
                self.assertTrue(d._models_normal.isAncestorOf(control))
                self.pointer_click(d,control)
                popup=APP.activePopupWidget();self.assertIsNotNone(popup)
                popup.hide();QTest.qWait(10)
            d.dispose();d.close()

    def test_models_pointer_navigation_reaches_manager_and_returns(self):
        d=self.settings_window(True)
        self.pointer_click(d,d.manage_components)
        self.assertIs(d.component_stack.currentWidget(),d.component_manager)
        self.assertFalse(d._processing.isVisible());self.assertFalse(d.manage_components.isVisible())
        self.pointer_click(d,d.component_manager.back)
        self.assertIs(d.component_stack.currentWidget(),d._models_normal)
        self.pointer_click(d,d._processing);APP.activePopupWidget().hide()
        d.dispose();d.close()

    def test_models_pointer_actions_invoke_test_and_setup(self):
        from ui.model_setup import SetupDialog,active_jobs
        d=self.settings_window(True)
        with patch.object(d,'_draft',return_value=AppConfig()),patch.object(d.model_task,'start_job') as run:
            self.pointer_click(d,d.test_setup);run.assert_called_once()
        with patch.object(SetupDialog,'detect_hardware',return_value={'cpu':'Test','ram_bytes':8*1024**3,'devices':[]}):
            self.pointer_click(d,d.setup_assistant);settle(lambda:not active_jobs())
            self.assertTrue(d._setup_dialog.isVisible());d._setup_dialog.reject()
        d.dispose();d.close()

    def test_component_cards_select_without_starting_downloads(self):
        d=self.settings_window(True);self.pointer_click(d,d.manage_components)
        manager=d.component_manager
        with patch.object(manager,'start_job') as run:
            card,button,state,verify=manager.cards['speech-turbo']
            self.pointer_click(d,button)
            self.assertEqual(manager.choice.currentData(),'speech-turbo')
            self.assertTrue(button.isChecked());self.assertIn('Whisper',manager.details.text());run.assert_not_called()
        d.dispose();d.close()

if __name__=='__main__':unittest.main()
