"""Interrupted downloads resume safely, with bounded retries and no TLS bypass."""
import hashlib,http.client,io,ssl,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from core.components import Asset,fetch
from core.downloads import ATTEMPTS

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}

class Broken(Response):
    def __init__(self,prefix,error):super().__init__(prefix);self.error=error;self.first=True
    def read(self,size=-1):
        if self.first:self.first=False;return super().read(size)
        raise self.error

class Partial(Response):
    def read(self,size=-1):raise http.client.IncompleteRead(b'abc',4)

class DownloadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'Qwen3-4B.gguf';self.part=self.path.with_suffix('.gguf.part')
        self.data=b'abcdefg';self.asset=Asset(self.path.name,'https://huggingface.co/example/model',len(self.data),hashlib.sha256(self.data).hexdigest())
        self.wait=patch('core.downloads.wait_to_retry');self.waiter=self.wait.start()
    def tearDown(self):self.wait.stop();self.temp.cleanup()
    def remainder(self,start):return Response(self.data[start:],206,{'Content-Range':f'bytes {start}-6/7'})
    def test_connection_reset_at_open_is_retried(self):
        with patch('core.downloads.urllib.request.urlopen',side_effect=[urllib.error.URLError(ConnectionResetError(10054,'reset')),Response(self.data)]) as request:
            fetch(self.asset,self.path)
        self.assertEqual(request.call_count,2);self.assertEqual(request.call_args.kwargs['timeout'],30);self.assertEqual(self.path.read_bytes(),self.data)
    def test_midstream_reset_resumes_saved_bytes(self):
        progress=[]
        with patch('core.downloads.urllib.request.urlopen',side_effect=[Broken(self.data[:3],ConnectionResetError(10054,'reset')),self.remainder(3)]) as request:
            fetch(self.asset,self.path,lambda message,percent:progress.append(message))
        self.assertEqual(request.call_args_list[1].args[0].get_header('Range'),'bytes=3-');self.assertEqual(self.path.read_bytes(),self.data);self.assertFalse(self.part.exists());self.assertTrue(any('retry 1/4' in s for s in progress))
    def test_eof_before_expected_size_is_retried(self):
        with patch('core.downloads.urllib.request.urlopen',side_effect=[Response(self.data[:3]),self.remainder(3)]) as request:fetch(self.asset,self.path)
        self.assertEqual(request.call_args_list[1].args[0].get_header('Range'),'bytes=3-');self.assertEqual(self.path.read_bytes(),self.data)
    def test_incomplete_read_preserves_partial_payload(self):
        with patch('core.downloads.urllib.request.urlopen',side_effect=[Partial(b''),self.remainder(3)]):fetch(self.asset,self.path)
        self.assertEqual(self.path.read_bytes(),self.data)
    def test_exhausted_retries_keep_partial_and_identify_model_host(self):
        self.part.write_bytes(self.data[:3])
        with patch('core.downloads.urllib.request.urlopen',side_effect=urllib.error.URLError(ConnectionResetError(10054,'reset'))) as request:
            with self.assertRaisesRegex(OSError,'Qwen3-4B.gguf from huggingface.co'):fetch(self.asset,self.path)
        self.assertEqual(request.call_count,ATTEMPTS);self.assertEqual(self.waiter.call_count,ATTEMPTS-1);self.assertEqual(self.part.read_bytes(),self.data[:3]);self.assertFalse(self.path.exists())
    def test_missing_file_is_not_retried(self):
        error=urllib.error.HTTPError(self.asset.url,404,'Not found',{},None)
        with patch('core.downloads.urllib.request.urlopen',side_effect=error) as request:
            with self.assertRaisesRegex(OSError,'HTTP 404'):fetch(self.asset,self.path)
        self.assertEqual(request.call_count,1);self.waiter.assert_not_called()
    def test_rate_limit_respects_bounded_retry_after(self):
        error=urllib.error.HTTPError(self.asset.url,429,'Busy',{'Retry-After':'999'},None)
        with patch('core.downloads.urllib.request.urlopen',side_effect=[error,Response(self.data)]):fetch(self.asset,self.path)
        self.assertEqual(self.waiter.call_args.args[0],30)
    def test_certificate_error_is_not_retried_or_bypassed(self):
        with patch('core.downloads.urllib.request.urlopen',side_effect=urllib.error.URLError(ssl.SSLCertVerificationError('certificate failure'))) as request:
            with self.assertRaisesRegex(OSError,'TLS verification failed'):fetch(self.asset,self.path)
        self.assertEqual(request.call_count,1);self.waiter.assert_not_called()
    def test_invalid_content_range_never_appends_bytes(self):
        self.part.write_bytes(self.data[:3])
        with patch('core.downloads.urllib.request.urlopen',return_value=Response(self.data[3:],206,{'Content-Range':'bytes 2-6/7'})):
            with self.assertRaisesRegex(ValueError,'Invalid resume'):fetch(self.asset,self.path)
        self.assertEqual(self.part.read_bytes(),self.data[:3]);self.assertFalse(self.path.exists())
    def test_ignored_range_restarts_and_checksums_full_file(self):
        self.part.write_bytes(b'old')
        with patch('core.downloads.urllib.request.urlopen',return_value=Response(self.data)):fetch(self.asset,self.path)
        self.assertEqual(self.path.read_bytes(),self.data)
    def test_reset_after_final_bytes_can_complete_after_verification(self):
        with patch('core.downloads.urllib.request.urlopen',return_value=Broken(self.data,ConnectionResetError('reset'))) as request:fetch(self.asset,self.path)
        self.assertEqual(request.call_count,1);self.assertEqual(self.path.read_bytes(),self.data)
    def test_existing_verified_download_never_connects(self):
        self.path.write_bytes(self.data)
        with patch('core.downloads.urllib.request.urlopen',side_effect=AssertionError('No download')):fetch(self.asset,self.path)
    def test_cancel_during_backoff_is_immediate_and_keeps_progress(self):
        self.wait.stop();cancelled=[False]
        def progress(message,percent):
            if 'retry' in message:cancelled[0]=True
        self.part.write_bytes(self.data[:3])
        with patch('core.downloads.urllib.request.urlopen',side_effect=ConnectionResetError('reset')) as request:
            with self.assertRaises(InterruptedError):fetch(self.asset,self.path,progress,lambda:cancelled[0])
        self.assertEqual(request.call_count,1);self.assertEqual(self.part.read_bytes(),self.data[:3])
    def test_legacy_learning_setup_uses_same_resume_path(self):
        from core.local_assets import download
        self.part.write_bytes(self.data[:3])
        with patch('core.downloads.urllib.request.urlopen',return_value=self.remainder(3)) as request:download(self.asset.url,self.path,self.asset.size,self.asset.sha,lambda *args:None,lambda:False)
        self.assertEqual(request.call_args.args[0].get_header('Range'),'bytes=3-');self.assertEqual(self.path.read_bytes(),self.data)
