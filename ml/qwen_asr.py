"""Resident, authenticated loopback Qwen speech runtime; separate from text Qwen."""
import io,json,os,re,secrets,socket,subprocess,tempfile,time,uuid,wave
from pathlib import Path
import urllib.request,urllib.error
import numpy as np
from ml.vulkan_engine import VulkanWhisper

class QwenASR(VulkanWhisper):
    def __init__(self,config):
        super().__init__(config);self.key=secrets.token_hex(24);self.active_backend='Not loaded'
    def log_tail(self):
        if self.log is None:return ''
        self.log.seek(0);return self.log.read().decode('utf-8',errors='replace')[-20000:]
    @staticmethod
    def gpu_allocated(log):
        return bool(re.search(r'using preferred GPU backend: Vulkan\d+',log) and re.search(r'qwen3_asr: loaded ',log))
    def start(self,cpu_only=False,cancelled=lambda:False):
        from core.components import resolve
        exe,model=resolve('qwen-asr-runtime'),resolve('speech-qwen')
        if not exe or not model:raise ValueError('Download Qwen ASR and its speech runtime first.')
        cpu_only=cpu_only or self.config.processing_mode=='cpu'
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}';self.log=tempfile.TemporaryFile(mode='w+b',buffering=0)
        command=[str(exe),'--server','--host','127.0.0.1','--port',str(port),'--backend','qwen3','-m',str(model),'-t',str(self.config.cpu_threads),'--gpu-backend','cpu' if cpu_only else 'vulkan','--no-warmup','-l','auto','--verbose']
        if cpu_only:command.append('--no-gpu')
        elif self.config.gpu_device:
            device=self.config.gpu_device.removeprefix('Vulkan')
            if not device.isdigit():raise ValueError('Invalid GPU device selection')
            command.extend(['--device',device])
        env=dict(os.environ,CRISPASR_API_KEYS=self.key,HF_HUB_OFFLINE='1',CRISPASR_NO_AUTO_DOWNLOAD='1',CRISPASR_N_GPU_LAYERS='-1')
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            self.process=subprocess.Popen(command,cwd=str(exe.parent),env=env,stdout=self.log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if cancelled():raise InterruptedError('Speech loading cancelled')
                if self.process.poll() is not None:raise RuntimeError('Qwen speech runtime exited. '+self.log_tail()[-1800:])
                try:
                    with self.http.open(self.url+'/health',timeout=.5) as response:healthy=json.load(response).get('status')=='ok'
                    if healthy:
                        if not cpu_only and not self.gpu_allocated(self.log_tail()):raise RuntimeError('Qwen did not confirm Vulkan model allocation. '+self.log_tail()[-1800:])
                        self.active_backend='CPU / Qwen ASR' if cpu_only else 'GPU / Vulkan · Qwen ASR';return
                except (OSError,urllib.error.URLError):time.sleep(.1)
            raise TimeoutError('Qwen ASR loading timed out.')
        except Exception:
            self.close();raise
    def transcribe(self,audio,language,translate=False,allowed_languages=None):
        if translate:raise RuntimeError('Qwen ASR transcribes speech; choose a text translation model for translation.')
        if not np.any(np.abs(audio)>1e-5):return '',language
        wav=io.BytesIO()
        with wave.open(wav,'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
        boundary=uuid.uuid4().hex;parts=[]
        for name,value in {'response_format':'verbose_json','language':language or 'auto','prompt':self.config.speech_prompt,'temperature':'0','max_tokens':'256'}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8'))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+wav.getvalue()+b'\r\n');parts.append(f'--{boundary}--\r\n'.encode())
        request=urllib.request.Request(self.url+'/v1/audio/transcriptions',data=b''.join(parts),headers={'Authorization':'Bearer '+self.key,'Content-Type':f'multipart/form-data; boundary={boundary}'})
        with self.http.open(request,timeout=120) as response:result=json.load(response)
        detected=str(result.get('language') or language or '').lower()
        detected={'english':'en','chinese':'zh','mandarin':'zh','thai':'th','indonesian':'id'}.get(detected,detected)
        if allowed_languages and detected not in allowed_languages:raise RuntimeError('Detected speech is outside the selected auto-language group. Choose a spoken language manually.')
        return str(result.get('text','')).strip(),detected or None
