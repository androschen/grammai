"""Optional resident whisper.cpp Vulkan server, owned by this app."""
from __future__ import annotations
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import uuid
import wave
import urllib.request
import numpy as np


class VulkanWhisper:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.log = None
        self.url = ""

    def start(self):
        exe, model = Path(self.config.vulkan_executable), Path(self.config.vulkan_model)
        if not exe.is_file() or not model.is_file():
            raise RuntimeError("Choose a Vulkan whisper-server executable and GGML model in Performance settings.")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.log = tempfile.TemporaryFile(mode="w+b")
        self.process = subprocess.Popen(
            [str(exe.resolve()), "--host", "127.0.0.1", "--port", str(port),
             "-m", str(model.resolve()), "-t", str(self.config.cpu_threads),
             "-bs", str(self.config.beam_size), "-l", "auto"],
            cwd=str(exe.resolve().parent), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Bypass proxy environment variables for this local child process.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                with self.http.open(self.url + "/health", timeout=.5):
                    pass
                self.log.seek(0)
                log = self.log.read().decode("utf-8", errors="replace").lower()
                if "vulkan" not in log or "vulkan0" not in log:
                    raise RuntimeError("Server did not confirm Vulkan GPU model allocation. Use a Vulkan build.")
                return
            except (OSError, urllib.error.URLError):
                time.sleep(.1)
        self.close()
        raise RuntimeError("Vulkan server did not become ready; check executable, model, and driver.")

    def transcribe(self, audio, language, translate=False):
        wav = io.BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in {"response_format": "verbose_json", "language": language or "auto",
                            "translate": "true" if translate else "false", "temperature": "0.0",
                            "token_timestamps": "false", "no_language_probabilities": "true"}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode() + wav.getvalue() + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        request = urllib.request.Request(self.url + "/inference", data=b''.join(parts),
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with self.http.open(request, timeout=120) as response:
            result = json.load(response)
        detected = result.get("language", language)
        detected = {"english": "en", "chinese": "zh", "thai": "th"}.get((detected or "").lower(), detected)
        return result.get("text", "").strip(), detected

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
