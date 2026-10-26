"""Role inventory, truthful detection and safe shared-model removal."""
import hashlib,os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from core.components import ComponentManager,catalog
from core.config import AppConfig
from core.events import EventBus
from core.model_management import usage,remove_model,storage_bytes,installation_components
from ui.model_setup import ComponentsWidget
APP=QApplication.instance() or QApplication([])

class ModelManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=str(self.root/'profile'),GRAMMAI_MODELS_DIR=str(self.root/'models'));self.env.start()
        self.home=patch('pathlib.Path.home',return_value=self.root);self.home.start()
        self.data=b'weights'
        specs={key:replace(spec,assets=tuple(replace(a,size=len(self.data),sha=hashlib.sha256(self.data).hexdigest()) for a in spec.assets)) if spec.kind!='runtime' else spec for key,spec in catalog().items()}
        self.specs=patch('core.components.catalog',return_value=specs);self.specs.start();self.manager=ComponentManager()
    def tearDown(self):self.specs.stop();self.home.stop();self.env.stop();self.temp.cleanup()
    def model(self,key,managed=True):
        spec=catalog()[key];base=self.manager.root/'managed'/key/spec.version if managed else self.root/'external'/key
        base.mkdir(parents=True,exist_ok=True)
        for asset in spec.assets:(base/asset.name).write_bytes(self.data)
        path=base/spec.entry
        self.manager.register(key,path,managed,{asset.name:hashlib.sha256(self.data).hexdigest() for asset in spec.assets} if managed else None)
        return path
    def test_new_pc_never_claims_available_or_installed(self):
        w=ComponentsWidget(AppConfig(),EventBus())
        self.assertTrue(all('Not downloaded' in row[2].text() for row in w.cards.values()))
        self.assertEqual(w.total.text(),'0 MB managed');w.dispose();w.close()
    def test_truncated_model_is_incomplete_and_cannot_activate(self):
        path=self.model('speech-turbo');path.write_bytes(b'x')
        self.assertEqual(self.manager.availability('speech-turbo'),'incomplete')
        from core.speech_models import installed
        self.assertFalse(installed('speech-turbo'))
    def test_missing_ct2_companion_is_incomplete(self):
        path=self.model('speech-cpu');(path.parent/'tokenizer.json').unlink()
        self.assertEqual(self.manager.availability('speech-cpu'),'incomplete')
    def test_nested_runtime_is_rediscovered_without_registry(self):
        spec=catalog()['speech-runtime'];base=self.manager.root/'managed/speech-runtime'/spec.version/'nested';base.mkdir(parents=True)
        exe=base/spec.entry;exe.write_bytes(b'exe')
        self.assertEqual(self.manager.path('speech-runtime'),exe)
        self.assertEqual(self.manager.records(),{})
    def test_missing_runtime_library_is_incomplete(self):
        spec=catalog()['speech-runtime'];base=self.manager.root/'managed/speech-runtime'/spec.version;base.mkdir(parents=True)
        exe=base/spec.entry;exe.write_bytes(b'exe')
        self.manager.register('speech-runtime',exe,True,{spec.entry:'irrelevant','engine.dll':'irrelevant'})
        self.assertEqual(self.manager.availability('speech-runtime'),'incomplete')
    def test_shared_qwen_blocks_removal_for_each_enabled_feature(self):
        path=self.model('qwen')
        configs=[AppConfig(analysis_enabled=True),AppConfig(translation_mode='context'),AppConfig(refinement_enabled=True)]
        for config in configs:
            self.assertTrue(usage('qwen',config,self.manager))
            with self.assertRaises(ValueError):remove_model('qwen',config,self.manager)
            self.assertTrue(path.exists())
    def test_disabled_learning_does_not_permanently_pin_qwen(self):
        path=self.model('qwen');config=AppConfig(analysis_enabled=False,learning_model_id='qwen',translation_enabled=False)
        remove_model('qwen',config,self.manager);self.assertFalse(path.exists())
    def test_unused_model_delete_preserves_shared_runtime_and_private_data(self):
        path=self.model('speech-large');kept=self.model('speech-turbo');private=self.root/'profile/phrases.json';private.write_text('private')
        remove_model('speech-large',AppConfig(speech_model_id='speech-turbo'),self.manager)
        self.assertFalse(path.exists());self.assertTrue(kept.exists());self.assertEqual(private.read_text(),'private')
        self.assertIn('Installed Whisper large-v3-turbo',usage('speech-runtime',AppConfig(),self.manager))
    def test_disconnect_keeps_files_and_survives_rediscovery(self):
        path=self.model('speech-large',False);config=AppConfig()
        remove_model('speech-large',config,self.manager)
        self.assertTrue(path.exists());self.assertIsNone(ComponentManager().path('speech-large'))
        self.assertEqual(self.manager.records()['speech-large'],{'disconnected':True})
    def test_shared_storage_count_and_dependencies(self):
        self.model('qwen');self.assertEqual(storage_bytes('qwen',self.manager),len(self.data))
        ids=installation_components('qwen','auto');self.assertEqual(ids.count('qwen'),1);self.assertIn('ai-cpu',ids);self.assertIn('ai-vulkan',ids)
        self.assertEqual(installation_components('speech-large','gpu'),('speech-large','speech-runtime'))
    def test_shared_delete_dialog_returns_to_settings_without_job(self):
        self.model('qwen');w=ComponentsWidget(AppConfig(refinement_enabled=True),EventBus());back=[];w.back.clicked.connect(lambda:back.append(True))
        with patch('ui.model_setup.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch.object(w,'start_job') as job:
            w.delete_selected('qwen');self.assertEqual(back,[True]);job.assert_not_called()
        w.dispose();w.close()
    def test_cancel_delete_leaves_files_untouched(self):
        path=self.model('speech-large');w=ComponentsWidget(AppConfig(),EventBus())
        with patch('ui.model_setup.QMessageBox.question',return_value=QMessageBox.StandardButton.No),patch.object(w,'start_job') as job:
            w.delete_selected('speech-large');job.assert_not_called();self.assertTrue(path.exists())
        w.dispose();w.close()
    def test_inventory_refresh_never_hashes_or_downloads(self):
        self.model('speech-large')
        with patch('core.components.digest',side_effect=AssertionError('UI must not hash')),patch('core.components.fetch',side_effect=AssertionError('No download')):
            w=ComponentsWidget(AppConfig(),EventBus());w.refresh();self.assertIn('Files detected',w.cards['speech-large'][2].text());w.dispose();w.close()

    def test_custom_speech_status_requires_explicit_compatibility_check(self):
        from ui.settings import SettingsPage
        with patch('ui.settings.list_audio_sources',return_value=[]):w=SettingsPage(AppConfig(),EventBus(),page=3)
        self.assertIn('Test setup',w._role_detail['speech'].text())
        self.assertNotIn('Installed',w._role_detail['speech'].text());w.dispose();w.close()

    def test_legacy_cpu_base_selection_is_protected(self):
        path=self.model('speech-cpu',False)
        with self.assertRaises(ValueError):remove_model('speech-cpu',AppConfig(),self.manager)
        self.assertTrue(path.exists())

    def test_custom_learning_model_does_not_pin_unused_qwen(self):
        path=self.model('qwen');custom=self.root/'other.gguf';custom.write_bytes(b'custom')
        config=AppConfig(analysis_enabled=True,analysis_gguf=str(custom),learning_model_id='external',translation_enabled=False)
        remove_model('qwen',config,self.manager);self.assertFalse(path.exists())
