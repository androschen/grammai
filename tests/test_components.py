"""Component transactions must preserve user data and never activate corrupt downloads."""
import hashlib,io,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from core.components import Asset,Component,ComponentManager,fetch,catalog


class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.env=patch.dict(os.environ,GRAMMAI_DATA_DIR=str(self.home/'profile'));self.env.start()
        self.manager=ComponentManager(self.home/'models');self.data=b'known model weights';self.asset=Asset('weights.bin','https://example.invalid/weights',len(self.data),hashlib.sha256(self.data).hexdigest())
        self.spec=Component('sample','Sample model','gguf','v1',(self.asset,),'weights.bin',('speech',),'Test','MIT')
        self.cat=patch('core.components.catalog',return_value={'sample':self.spec});self.cat.start()
    def tearDown(self):self.cat.stop();self.env.stop();self.temp.cleanup()
    def install(self):
        with patch('core.components.urllib.request.urlopen',return_value=Response(self.data)):return self.manager.install('sample')
    def test_install_verify_reuses_weights_and_independent_registry(self):
        path=self.install();self.assertEqual(path.read_bytes(),self.data);self.assertTrue(self.manager.verify('sample'))
        with patch('core.components.urllib.request.urlopen',side_effect=AssertionError('No repeat download')):self.assertEqual(self.manager.install('sample'),path)
        self.assertEqual(self.manager.records()['sample']['version'],'v1')
    def test_corrupt_download_never_activates_model(self):
        with patch('core.components.urllib.request.urlopen',return_value=Response(b'x'*len(self.data))):
            with self.assertRaises(ValueError):self.manager.install('sample')
        self.assertIsNone(self.manager.path('sample'));self.assertEqual(list((self.manager.root/'managed').rglob('weights.bin')),[])
    def test_cancel_preserves_partial_and_retry_resumes(self):
        path=self.manager.root/'cached.bin';path.parent.mkdir(parents=True);part=path.with_suffix('.bin.part');part.write_bytes(self.data[:5])
        with patch('core.components.urllib.request.urlopen',return_value=Response(self.data[5:],206,{'Content-Range':f'bytes 5-{len(self.data)-1}/{len(self.data)}'})) as request:
            fetch(self.asset,path)
        self.assertEqual(path.read_bytes(),self.data);self.assertEqual(request.call_args.args[0].get_header('Range'),'bytes=5-')
    def test_server_ignores_range_restarts_instead_of_appending(self):
        path=self.manager.root/'cached.bin';path.parent.mkdir(parents=True);path.with_suffix('.bin.part').write_bytes(b'wrong')
        with patch('core.components.urllib.request.urlopen',return_value=Response(self.data)):fetch(self.asset,path)
        self.assertEqual(path.read_bytes(),self.data)
    def test_archive_traversal_is_rejected(self):
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as z:z.writestr('../escape.exe',b'bad')
        raw=memory.getvalue();asset=Asset('runtime.zip','https://example.invalid/a',len(raw),hashlib.sha256(raw).hexdigest())
        self.cat.stop();self.cat=patch('core.components.catalog',return_value={'sample':Component('sample','Runtime','runtime','v1',(asset,),'server.exe',('speech',),'Test','MIT')});self.cat.start()
        with patch('core.components.urllib.request.urlopen',return_value=Response(raw)):
            with self.assertRaises(ValueError):self.manager.install('sample')
        self.assertFalse((self.manager.root/'managed/sample/escape.exe').exists());self.assertIsNone(self.manager.path('sample'))
    def test_repair_failure_restores_working_model_and_registry(self):
        path=self.install();before=self.manager.records()
        with patch('core.components.urllib.request.urlopen',side_effect=OSError('Offline')):
            with self.assertRaises(OSError):self.manager.repair('sample')
        self.assertEqual(self.manager.records(),before);self.assertEqual(path.read_bytes(),self.data)
    def test_move_verifies_then_commits_and_external_files_stay(self):
        original=self.install();external=self.home/'outside.bin';external.write_bytes(b'personal')
        destination=self.home/'another-drive';self.manager.move(destination)
        self.assertFalse(original.exists());self.assertEqual(self.manager.path('sample').read_bytes(),self.data);self.assertEqual(external.read_bytes(),b'personal')
        from core.paths import model_root
        self.assertEqual(model_root(),destination)
    def test_move_cancel_keeps_original_and_retry_can_succeed(self):
        original=self.install();destination=self.home/'destination'
        with self.assertRaises(InterruptedError):self.manager.move(destination,cancelled=lambda:True)
        self.assertTrue(original.exists());self.manager.move(destination);self.assertEqual(self.manager.path('sample').read_bytes(),self.data)
    def test_external_files_cannot_be_removed(self):
        outside=self.home/'external.bin';outside.write_bytes(self.data);self.manager.register('sample',outside)
        with self.assertRaises(ValueError):self.manager.remove('sample')
        self.assertTrue(outside.exists())
    def test_corrupt_registry_is_not_silently_replaced(self):
        profile=self.home/'profile';profile.mkdir();path=profile/'components.json';path.write_text('invalid',encoding='utf8')
        with self.assertRaises(ValueError):self.manager.records()
        self.assertEqual(path.read_text(),'invalid')
    def test_catalog_has_pinned_versions_and_shared_ai(self):
        self.cat.stop();values=catalog();self.cat.start()
        self.assertEqual(values['qwen'].roles,('translation','learning'));self.assertIn('ai-cpu',values)
        for spec in values.values():
            self.assertTrue(spec.version)
            for asset in spec.assets:self.assertEqual(len(asset.sha),64);self.assertGreater(asset.size,0);self.assertTrue(asset.url.startswith('https://'))

if __name__=='__main__':unittest.main()
