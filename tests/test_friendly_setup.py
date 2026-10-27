"""Feature onboarding, recoverable transfers and explicit compatibility results."""
import os,tempfile,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.components import ComponentManager,catalog
from core.config import AppConfig
from core.onboarding import SetupPlan,inventory,disk_estimate
from ui.model_setup import SetupDialog,active_jobs,cancel_jobs
APP=QApplication.instance() or QApplication([])

def settle(predicate):
    for _ in range(600):
        if predicate():return
        QTest.qWait(10)
    raise AssertionError('Setup task did not finish')

class FriendlySetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.dialogs=[]
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=str(self.root/'profile'),GRAMMAI_MODELS_DIR=str(self.root/'models'),HF_HUB_CACHE=str(self.root/'cache'));self.env.start()
        self.home=patch('pathlib.Path.home',return_value=self.root);self.home.start()
        self.hardware=patch.object(SetupDialog,'detect_hardware',return_value={'cpu':'Test','ram_bytes':16*1024**3,'display_adapters':['NVIDIA test'],'devices':[]});self.hardware.start()
        specs={key:replace(spec,assets=tuple(replace(a,size=7) for a in spec.assets)) for key,spec in catalog().items()}
        self.specs=patch('core.components.catalog',return_value=specs);self.specs.start();self.plan_specs=patch('core.onboarding.catalog',return_value=specs);self.plan_specs.start()
    def tearDown(self):
        cancel_jobs();settle(lambda:not active_jobs())
        for d in self.dialogs:d.reject();d.deleteLater()
        APP.processEvents();self.plan_specs.stop();self.specs.stop();self.hardware.stop();self.home.stop();self.env.stop();self.temp.cleanup()
    def wizard(self):
        d=SetupDialog(AppConfig());self.dialogs.append(d);d.show();settle(lambda:d._detect_done);return d
    def install(self,key,progress,cancelled):
        spec=catalog()[key];folder=self.root/'fixtures'/key;folder.mkdir(parents=True,exist_ok=True)
        for asset in spec.assets:(folder/asset.name).write_bytes(b'fixture')
        file=folder/spec.entry;file.write_bytes(b'fixture');ComponentManager().register(key,file)
        progress('Downloaded',100);return file
    def good_result(self):return {'backend':'GPU / Vulkan','speech_ms':100,'audio_seconds':3,'keeps_up':True,'ai_status':'GPU / Tested'}
    def test_learning_and_translation_are_independent_choices(self):
        c=SetupPlan('speech-cpu','cpu',True,False).configuration(AppConfig(refinement_enabled=True))
        self.assertTrue(c.analysis_enabled);self.assertFalse(c.translation_enabled);self.assertEqual(c.translation_mode,'fast');self.assertFalse(c.refinement_enabled)
        c=SetupPlan('speech-cpu','cpu',False,True).configuration(AppConfig());self.assertFalse(c.analysis_enabled);self.assertTrue(c.translation_enabled)
    def test_small_download_keeps_fast_translation_optional(self):
        d=self.wizard();d.essential.click()
        self.assertEqual(d.speech.currentData(),'speech-cpu');self.assertFalse(d.ai.isChecked());self.assertTrue(d.fast.isChecked());self.assertFalse(d._advanced.isVisible());self.assertFalse(d.finish.isEnabled())
    def test_detection_does_not_override_choices_made_while_checking(self):
        d=self.wizard();d.preset(False);d.detected({'value':{'devices':[{'name':'Other GPU'}]}})
        self.assertEqual(d.speech.currentData(),'speech-cpu');self.assertFalse(d.ai.isChecked())
    def test_inventory_counts_partial_bytes_and_shared_weights_once(self):
        manager=ComponentManager();plan=SetupPlan('speech-turbo','auto',True,True);spec=catalog()['qwen']
        partial=manager.root/'downloads/qwen'/spec.assets[0].name;partial=partial.with_suffix(partial.suffix+'.part');partial.parent.mkdir(parents=True);partial.write_bytes(b'abc')
        rows=inventory(plan,manager);self.assertEqual([r['id'] for r in rows].count('qwen'),1);self.assertEqual(next(r['saved'] for r in rows if r['id']=='qwen'),3)
        download,reserve=disk_estimate(rows);self.assertEqual(download,sum(r['size'] for r in rows)-3);self.assertGreater(reserve,download)
    def test_primary_button_downloads_and_tests_in_one_action(self):
        d=self.wizard();d.preset(False);d.fast.setChecked(False)
        with patch('core.components.ComponentManager.install',side_effect=self.install),patch('ui.model_setup.test_configuration',return_value=self.good_result()) as check:
            d.continue_button.click();settle(lambda:d.checked is not None)
        check.assert_called_once();self.assertEqual(d.pages.currentIndex(),2);self.assertTrue(d.finish.isEnabled());self.assertFalse((self.root/'profile/preferences.json').exists())
    def test_failed_test_never_enables_start_or_changes_preferences(self):
        d=self.wizard();d.fast.setChecked(False);d.ai.setChecked(False)
        with patch('core.components.ComponentManager.install',side_effect=self.install),patch('ui.model_setup.test_configuration',side_effect=RuntimeError('GPU fixture failed')):
            d.install_and_test();settle(lambda:d.task.job is None)
        self.assertFalse(d.finish.isEnabled());self.assertIsNone(d.checked);self.assertTrue(d.retry_cpu.isVisible());self.assertFalse((self.root/'profile/preferences.json').exists())
    def test_interruption_shows_recovery_for_the_failed_learning_component(self):
        d=self.wizard();d._plan=d.plan();d._rows=inventory(d._plan,d.manager);d.show_step(1)
        d._component_changed('qwen','Connection interrupted · retry 2/4',40)
        self.assertTrue(d.recovery.isVisible());self.assertTrue(d.later.isVisible());self.assertIn('retry 2/4',d.recovery_note.text())
    def test_defer_learning_cancels_then_tests_remaining_features(self):
        d=self.wizard();calls=[];partial=self.root/'models/downloads/qwen/fixture.part'
        def download(key,progress,cancelled):
            calls.append(key)
            if key=='qwen':
                partial.parent.mkdir(parents=True,exist_ok=True);partial.write_bytes(b'abc');progress('Connection interrupted · retry 1/4',30)
                while not cancelled():time.sleep(.01)
                raise InterruptedError('Cancelled')
            return self.install(key,progress,cancelled)
        with patch('core.components.ComponentManager.install',side_effect=download),patch('ui.model_setup.test_configuration',return_value=self.good_result()):
            d.install_and_test();settle(lambda:d._active_id=='qwen' and d.recovery.isVisible());d.later.click();settle(lambda:d.checked is not None)
        self.assertFalse(d.checked['config'].analysis_enabled);self.assertTrue(d.checked['config'].translation_enabled);self.assertEqual(calls.count('qwen'),1);self.assertEqual(partial.read_bytes(),b'abc');self.assertTrue(d.finish.isEnabled())
    def test_ready_cpu_status_reports_actual_backend_and_warning(self):
        d=self.wizard();d._phase='test'
        d.tested({'value':{'config':d.plan().configuration(AppConfig()),'test':dict(self.good_result(),backend='CPU / int8 · Whisper base backup',speech_note='GPU startup failed: fixture')}})
        self.assertIn('CPU',d.ready_title.text());self.assertIn('Whisper base backup',d.ready.text());self.assertIn('GPU startup',d.ready_note.text());self.assertTrue(d.ready_retry.isVisible());self.assertTrue(d.finish.isEnabled())
    def test_cpu_recovery_changes_draft_only_and_retests(self):
        d=self.wizard();config=d.config.processing_mode
        with patch.object(d,'_restart_when_idle') as restart:
            d.request_action('cpu');APP.processEvents();restart.assert_called_once()
        self.assertEqual(d.processing.currentData(),'cpu');self.assertEqual(d.config.processing_mode,config);self.assertFalse(d.finish.isEnabled())
    def test_low_disk_space_stays_on_choices_without_starting_download(self):
        d=self.wizard()
        with patch('ui.setup_wizard.shutil.disk_usage',return_value=Mock(free=0)),patch.object(d.task,'start_job') as start:d.install_and_test()
        start.assert_not_called();self.assertEqual(d.pages.currentIndex(),0);self.assertIn('Not enough free space',d.total.text());self.assertFalse(d.finish.isEnabled())
    def test_new_ui_uses_three_compact_feature_cards(self):
        d=self.wizard();self.assertEqual(d.pages.count(),3);self.assertEqual(len(d.download_rows),3);self.assertEqual(d.continue_button.text(),'Download & test');self.assertTrue(d.task.status.parentWidget() is d.task)

    def test_closing_before_queued_retry_cannot_start_hidden_download(self):
        d=self.wizard()
        with patch.object(d,'install_and_test') as start:
            d.request_action('cpu');d.reject();APP.processEvents();start.assert_not_called()

    def test_ready_and_download_states_keep_readable_width(self):
        d=self.wizard();d.resize(650,780);d._plan=d.plan();d._rows=inventory(d._plan,d.manager);d.show_step(1);APP.processEvents()
        self.assertTrue(all(status.width()>=100 for _,_,status in d.download_rows.values()))
        d.tested({'value':{'config':d.plan().configuration(AppConfig()),'test':self.good_result()}});APP.processEvents()
        self.assertTrue(all(status.width()>=160 for _,status in d.ready_rows.values()))

    def test_download_waits_for_detector_thread_to_finish(self):
        with patch.object(SetupDialog,'detect_hardware',side_effect=lambda p,c:(time.sleep(.05) or {'devices':[]})):
            d=SetupDialog(AppConfig());self.dialogs.append(d)
            self.assertFalse(d.continue_button.isEnabled());d.fast.setChecked(False);self.assertFalse(d.continue_button.isEnabled())
            settle(lambda:d._detect_done);self.assertTrue(d.continue_button.isEnabled());self.assertEqual(d.continue_button.text(),'Download & test')

    def test_progress_weights_metadata_by_saved_bytes(self):
        from core.onboarding import component_percent
        manager=ComponentManager();spec=catalog()['speech-cpu'];file=manager.root/'downloads/speech-cpu'/spec.assets[0].name
        file.parent.mkdir(parents=True);file.write_bytes(b'fixture')
        self.assertEqual(component_percent('speech-cpu',manager,99),25)

    def test_close_during_hardware_detection_has_no_late_callback(self):
        from PySide6.QtCore import Qt
        from shiboken6 import isValid
        errors=[]
        with patch.object(SetupDialog,'detect_hardware',side_effect=lambda p,c:(time.sleep(.05) or {'devices':[]})),patch('sys.excepthook',side_effect=lambda kind,error,tb:errors.append(str(error))):
            d=SetupDialog(AppConfig());d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True);d.show();d.reject()
            settle(lambda:not active_jobs());QTest.qWait(30)
        self.assertEqual(errors,[]);self.assertFalse(isValid(d))
