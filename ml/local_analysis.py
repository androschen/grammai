"""App-owned, loopback-only llama.cpp Vulkan process with verified offloading."""
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from core.local_assets import managed_paths


class LocalAnalysisRuntime:
    def __init__(self):
        self.process = None
        self.log = None
        self.url = ''
        self.key = ''
        self.signature = None
        self.status = 'Unloaded'
        self.last_used = time.monotonic()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                return None
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def paths(self, config):
        executable, model = managed_paths()
        return Path(config.analysis_executable or executable), Path(config.analysis_gguf or model)

    @property
    def loaded(self):
        return self.process is not None and self.process.poll() is None and self.signature is not None

    @staticmethod
    def verified_offload(log):
        layers = re.search(r'offloaded\s+(\d+)\s*/\s*(\d+)\s+layers to GPU', log, re.I)
        return bool(layers and int(layers[1]) > 0 and re.search(r'Vulkan\d+.*(?:model buffer|device buffer)', log, re.I))

    def log_tail(self):
        if self.log is None:
            return ''
        self.log.seek(0, 2)
        size = self.log.tell()
        self.log.seek(max(0, size - 131072))
        return self.log.read().decode('utf-8', errors='replace')

    def ensure_loaded(self, config, progress=lambda message: None, cancelled=lambda: False):
        executable, model = self.paths(config)
        signature = (str(executable.resolve()), str(model.resolve()), config.analysis_context_tokens)
        if self.loaded and self.signature == signature:
            self.last_used = time.monotonic()
            return
        self.close()
        if not executable.is_file() or not model.is_file():
            raise ValueError('Install the local model/runtime or select existing files in Settings > Analysis.')
        if model.suffix.lower() != '.gguf':
            raise ValueError('Select a GGUF instruction model.')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        progress('Detecting Vulkan GPU...')
        devices = subprocess.run([str(executable.resolve()), '--list-devices'], cwd=executable.resolve().parent,
            capture_output=True, text=True, errors='replace', timeout=20, creationflags=flags)
        output = devices.stdout + devices.stderr
        candidates=list(re.finditer(r'(Vulkan\d+):[^\n]*(?:AMD|Radeon)[^\n]*', output, re.I))
        found=next((item for item in candidates if 'RX 7700' in item[0]),None) or next((item for item in candidates if 'RX ' in item[0]),None) or next(iter(candidates),None)
        if not found or devices.returncode:
            raise RuntimeError('AMD Vulkan GPU was not detected. Check the Vulkan runtime and Radeon driver; CPU fallback is disabled.')
        self.status = found[0].strip()
        progress('Loading local model on ' + self.status)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url, self.key = f'http://127.0.0.1:{port}', secrets.token_urlsafe(32)
        self.log = tempfile.TemporaryFile(mode='w+b',buffering=0)
        environment = {k:v for k,v in os.environ.items() if not k.startswith('LLAMA_ARG_')}
        environment['LLAMA_API_KEY'] = self.key
        command = [str(executable.resolve()), '--model', str(model.resolve()), '--host', '127.0.0.1',
            '--port', str(port), '--device', found[1], '--n-gpu-layers', '99', '--ctx-size', str(config.analysis_context_tokens),
            '--parallel', '1', '--threads', '4', '--threads-batch', '4', '--jinja', '--offline',
            '--cache-ram', '0', '--no-webui', '--alias', 'grammai-local', '--verbosity', '4', '--log-colors', 'off']
        try:
            self.process = subprocess.Popen(command, cwd=executable.resolve().parent, env=environment,
                stdout=self.log, stderr=subprocess.STDOUT, creationflags=flags)
            started = time.monotonic()
            deadline = started + 240
            last_progress = started
            while time.monotonic() < deadline:
                if time.monotonic()-last_progress >= 10:
                    progress(f'Loading local GPU model ({time.monotonic()-started:.0f}s). First Vulkan startup can compile shaders.')
                    last_progress = time.monotonic()
                if cancelled():
                    raise InterruptedError('Model loading cancelled')
                if self.process.poll() is not None:
                    raise RuntimeError('Local runtime exited while loading. ' + self.log_tail()[-1200:])
                try:
                    with self.http.open(self.request('/health'), timeout=.7) as response:
                        healthy = json.load(response).get('status') == 'ok'
                    if healthy:
                        if not self.verified_offload(self.log_tail()):
                            diagnostics='\n'.join(line for line in self.log_tail().splitlines()
                                if re.search(r'offload|vulkan.*buffer',line,re.I))[-2500:]
                            raise RuntimeError('Runtime did not confirm Vulkan GPU model offloading. CPU fallback is disabled.\n'+(diagnostics or self.log_tail()[-2500:]))
                        self.signature = signature
                        self.last_used = time.monotonic()
                        self.status = 'GPU verified: ' + found[0].strip()
                        progress(self.status)
                        return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.1)
            raise TimeoutError('Local model loading timed out. Try a smaller GGUF model or free GPU memory.')
        except Exception:
            self.close()
            raise

    def request(self, path, body=None):
        return urllib.request.Request(self.url + path,
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})

    def complete(self, body, cancelled=lambda: False):
        from ml.context_analysis import parse_response, ANALYSIS_SCHEMA
        if not self.loaded:
            raise RuntimeError('Local model is not loaded.')
        if cancelled():
            raise InterruptedError('Analysis cancelled')
        body = dict(body, model='grammai-local', temperature=.3,
            response_format={'type': 'json_object', 'schema': ANALYSIS_SCHEMA})
        self.last_used = time.monotonic()
        try:
            with self.http.open(self.request('/v1/chat/completions', body), timeout=120) as response:
                raw = response.read(262145)
            if cancelled():
                raise InterruptedError('Analysis cancelled')
            return parse_response(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 413):
                raise ValueError('Local request did not fit or was rejected. Shorten the transcript/context, or increase the context limit.') from None
            raise RuntimeError(f'Local analysis failed (HTTP {exc.code}).') from None
        finally:
            self.last_used = time.monotonic()

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
        self.signature = None
        self.status = 'Unloaded'
        self.url, self.key = '', ''

    def interrupt(self):
        # Termination unblocks a pending local HTTP read; cleanup stays on the worker.
        process=self.process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass
