"""Storage cleanup, backup fidelity, truthful model sizes and compact controls."""
import hashlib,json,os,tempfile,unittest,zipfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.preferences import write_json
from core.phrasebook import Phrasebook,DeckReadError
from core.storage_data import audio_snapshot,cleanup_recordings,export_deck
from core.storage_metrics import scan_model_storage
from ui.storage import StorageWidget
APP=QApplication.instance() or QApplication([])

def settle(predicate):
    for _ in range(400):
        APP.processEvents()
        if predicate():return
        QTest.qWait(10)
    raise AssertionError('Storage job did not finish')

class StorageRedesignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.profile=self.root/'profile';self.models=self.root/'models';self.widgets=[]
        self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=str(self.profile),GRAMMAI_MODELS_DIR=str(self.models),HF_HUB_CACHE=str(self.root/'cache'));self.env.start()
        self.home=patch('pathlib.Path.home',return_value=self.root);self.home.start()
    def tearDown(self):
        for widget in self.widgets:widget.dispose();widget.close()
        QThreadPool.globalInstance().waitForDone(5000);APP.processEvents()
        for widget in self.widgets:widget.deleteLater()
        APP.processEvents();self.home.stop();self.env.stop();self.temp.cleanup()
    def clip(self,content):
        name=hashlib.sha256(content).hexdigest()+'.ogg';file=self.profile/'audio'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(content);return file
    def cards(self,*names):write_json('phrases.json',[dict(id=str(i),native_text='你好',target_text='Hello',notes='remember this',audio={'file':name}) for i,name in enumerate(names)])
    def widget(self):
        w=StorageWidget(AppConfig(),EventBus());self.widgets.append(w);w.resize(760,780);w.show();w.scan_audio();settle(lambda:not w._audio_scanning);return w
    def test_snapshot_distinguishes_linked_and_unused_audio(self):
        used=self.clip(b'used');unused=self.clip(b'unused');self.cards(used.name)
        value=audio_snapshot();self.assertEqual(value['clips'],2);self.assertEqual(value['unused_bytes'],6);self.assertEqual(value['unused_files'][0]['name'],unused.name)
    def test_cleanup_keeps_newly_referenced_and_unreviewed_files(self):
        old=self.clip(b'old');self.cards();preview=audio_snapshot()['unused_files'];self.cards(old.name);new=self.clip(b'new')
        value=cleanup_recordings(preview);self.assertEqual(value['removed_files'],0);self.assertTrue(old.exists());self.assertTrue(new.exists())
    def test_cleanup_removes_only_the_reviewed_unchanged_orphan(self):
        used=self.clip(b'used');old=self.clip(b'old');self.cards(used.name);before=(self.profile/'phrases.json').read_bytes();preview=audio_snapshot()['unused_files'];new=self.clip(b'new')
        value=cleanup_recordings(preview);self.assertEqual(value['removed_files'],1);self.assertFalse(old.exists());self.assertTrue(new.exists());self.assertTrue(used.exists());self.assertEqual((self.profile/'phrases.json').read_bytes(),before)
    def test_changed_files_are_not_deleted_after_preview(self):
        file=self.clip(b'old');self.cards();preview=audio_snapshot()['unused_files'];file.write_bytes(b'changed')
        self.assertEqual(cleanup_recordings(preview)['removed_files'],0);self.assertTrue(file.exists())
    def test_unreadable_deck_never_becomes_empty_cleanup(self):
        file=self.clip(b'old');self.cards();preview=audio_snapshot()['unused_files'];(self.profile/'phrases.json').write_text('broken')
        with self.assertRaises(DeckReadError):cleanup_recordings(preview)
        self.assertTrue(file.exists())
    def test_invalid_audio_reference_disables_cleanup(self):
        write_json('phrases.json',[{'id':'x','audio':{'file':'../outside.ogg'}}])
        with self.assertRaises(ValueError):audio_snapshot()
    def test_backup_contains_cards_and_shared_linked_audio_once(self):
        file=self.clip(b'audio');self.clip(b'orphan');self.cards(file.name,file.name);write_json('preferences.json',{'private_key':'do not export'})
        out=self.root/'backup.zip';result=export_deck(out)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(set(archive.namelist()),{'phrases.json','manifest.json','audio/'+file.name})
            cards=json.loads(archive.read('phrases.json'));manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(cards,Phrasebook().items());self.assertEqual(manifest['cards_sha256'],hashlib.sha256(archive.read('phrases.json')).hexdigest());self.assertEqual(archive.read('audio/'+file.name),b'audio')
        self.assertEqual(result['recordings'],1);self.assertEqual(result['cards'],2)
    def test_backup_reports_missing_recordings_without_losing_cards(self):
        self.cards('a'*64+'.ogg');result=export_deck(self.root/'backup.zip')
        self.assertEqual(result['cards'],1);self.assertEqual(result['missing_recordings'],1)
    def test_failed_backup_preserves_existing_destination(self):
        file=self.clip(b'audio');self.cards(file.name);out=self.root/'backup.zip';out.write_bytes(b'previous')
        with patch('core.storage_data._backup_clip',side_effect=OSError('cannot read')):
            with self.assertRaises(OSError):export_deck(out)
        self.assertEqual(out.read_bytes(),b'previous');self.assertEqual(list(self.root.glob('.grammai-backup-*')),[])
    def test_deck_only_clear_retains_audio_for_separate_cleanup(self):
        file=self.clip(b'audio');self.cards(file.name);Phrasebook().clear(preserve_audio=True)
        self.assertEqual(Phrasebook().items(),[]);self.assertTrue(file.exists());self.assertEqual(audio_snapshot()['unused_bytes'],5)
    def test_model_scan_includes_managed_and_external_files_once(self):
        managed=self.models/'managed/qwen/revision/weights.gguf';managed.parent.mkdir(parents=True);managed.write_bytes(b'weight')
        extra=self.root/'external.gguf';extra.write_bytes(b'external')
        value=scan_model_storage(AppConfig(analysis_gguf=str(extra),vulkan_model=str(managed)))
        self.assertEqual(value['bytes'],len(b'weight')+len(b'external'));self.assertFalse(value['partial'])
    def test_model_scan_deduplicates_hardlinks_and_counts_partial_downloads_separately(self):
        file=self.models/'managed/model/weights.gguf';file.parent.mkdir(parents=True);file.write_bytes(b'weight')
        linked=self.models/'speech/shared.gguf';linked.parent.mkdir();os.link(file,linked)
        part=self.models/'downloads/qwen/model.gguf.part';part.parent.mkdir(parents=True);part.write_bytes(b'partial')
        value=scan_model_storage(AppConfig());self.assertEqual(value['bytes'],6);self.assertEqual(value['download_bytes'],7)
    def test_model_scan_marks_bounded_partial_results(self):
        folder=self.models/'managed/test';folder.mkdir(parents=True)
        for i in range(5):(folder/str(i)).write_bytes(b'x')
        self.assertTrue(scan_model_storage(AppConfig(),max_files=2)['partial'])
    def test_cleanup_preview_and_cancel_do_not_modify_files(self):
        file=self.clip(b'orphan');self.cards();w=self.widget();w.clean_audio.click();self.assertTrue(w.preview_dialog.isVisible());self.assertTrue(file.exists());w.preview_dialog.cancel.click();self.assertTrue(file.exists())
    def test_confirmed_cleanup_updates_ui_and_keeps_cards(self):
        used=self.clip(b'used');unused=self.clip(b'orphan');self.cards(used.name);w=self.widget();w.clean_audio.click();w.preview_dialog.confirm.click();settle(lambda:not w._mutation)
        self.assertFalse(unused.exists());self.assertTrue(used.exists());self.assertFalse(w.clean_audio.isEnabled());self.assertEqual(len(Phrasebook().items()),1)
    def test_limit_change_updates_gauge_without_starting_worker(self):
        file=self.clip(b'used');self.cards(file.name);w=self.widget()
        with patch.object(w,'scan_audio') as scan:w.audio_limit.setCurrentIndex(0)
        scan.assert_not_called();self.assertEqual(w.gauge.limit,100*1024**2);self.assertEqual(w.config.saved_audio_limit_mb,250)
    def test_delete_requires_acknowledgement_and_retains_audio(self):
        file=self.clip(b'used');self.cards(file.name);w=self.widget();w._clear_phrases();dialog=w.preview_dialog
        self.assertFalse(dialog.confirm.isEnabled());dialog.confirm_check.setChecked(True);dialog.confirm.click();settle(lambda:not w._mutation)
        self.assertTrue(file.exists());self.assertEqual(Phrasebook().items(),[])
    def test_backup_ui_runs_export_off_thread(self):
        file=self.clip(b'used');self.cards(file.name);w=self.widget();out=self.root/'export.zip';w.export_backup(str(out));settle(lambda:not w._backup_busy)
        self.assertTrue(out.is_file());self.assertIn('Backup saved',w.feedback.text())
    def test_model_navigation_emits_only_intent(self):
        w=self.widget();called=[];w.manage_models_requested.connect(lambda:called.append(True));w.manage_models.click();self.assertEqual(called,[True]);self.assertFalse(w._scanning)
    def test_models_scan_is_cached_until_invalidated(self):
        w=self.widget()
        with patch.object(w,'scan_models') as scan:
            w._models_scanned=True;w.set_active(True);scan.assert_not_called();w.invalidate_models();scan.assert_called_once()
    def test_full_audio_limit_has_actionable_message(self):
        w=self.widget();value={'bytes':100*1024**2,'clips':50,'unused_bytes':0,'unused_files':[]};w.audio_limit.setCurrentIndex(0);w._show_audio(value)
        self.assertTrue(w.audio_warning.isVisible());self.assertIn('text only',w.audio_warning.text());self.assertFalse(w.clean_audio.isEnabled())

    def test_backup_review_rows_have_space_to_display(self):
        self.cards();w=self.widget();w._backup_preview();APP.processEvents();dialog=w.backup_dialog
        self.assertEqual(dialog.rows.count(),3);self.assertGreaterEqual(dialog.breakdown.height(),100)
        self.assertTrue(dialog.confirm.isVisible());self.assertTrue(dialog.cancel.isVisible())

    def test_settings_model_link_opens_existing_manager(self):
        from ui.settings import SettingsPage
        with patch('ui.settings.list_audio_sources',return_value=[]):page=SettingsPage(AppConfig(),EventBus(),page=4)
        self.widgets.append(page.storage);page.storage.manage_models.click()
        self.assertEqual(page.tabs.currentIndex(),3);self.assertIs(page.component_stack.currentWidget(),page.component_manager)
        page.dispose();page.close()
