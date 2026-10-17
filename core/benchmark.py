"""Fixed-fixture, warmed inference benchmark. Runs outside the UI thread."""
from __future__ import annotations
import hashlib
import os
import platform
import statistics
import subprocess
import time
import wave
from dataclasses import replace
from datetime import datetime, timezone
import numpy as np
from PySide6.QtCore import QThread, Signal
from core.preferences import data_dir, read_json, write_json
from core.config import TargetLanguage
from ml.whisper_engine import WhisperEngine
from ml.translator import NllbTranslator

REFERENCE = "The meeting starts at three in the afternoon."


def fixture():
    path = data_dir() / "benchmark.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        env = dict(os.environ, GRAMMAI_BENCH_WAV=str(path))
        script = '''$ErrorActionPreference='Stop'
$s=New-Object -ComObject SAPI.SpFileStream
$v=New-Object -ComObject SAPI.SpVoice
try { $s.Open($env:GRAMMAI_BENCH_WAV,3,$false); $v.AudioOutputStream=$s; $v.Speak('The meeting starts at three in the afternoon.') | Out-Null } finally { $s.Close() }
'''
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                     env=env, capture_output=True, timeout=30,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("Could not generate benchmark speech using Windows speech synthesis.")
    with wave.open(str(path)) as source:
        if source.getsampwidth() != 2:
            raise RuntimeError("Benchmark audio must be 16-bit PCM.")
        rate, channels = source.getframerate(), source.getnchannels()
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32)
        samples = samples.reshape(-1, channels).mean(axis=1) / 32768
    audio = np.interp(np.arange(round(len(samples) * 16000 / rate)) * rate / 16000,
                      np.arange(len(samples)), samples).astype(np.float32)
    return audio, hashlib.sha256(path.read_bytes()).hexdigest()


def compare_results(current, previous):
    if not previous:
        return "First run. Change a preset and run again to compare."
    if current.get('fixture') != previous.get('fixture') or current.get('protocol') != previous.get('protocol'):
        return "Different benchmark fixture/protocol; results are not directly comparable."
    before = previous['total_ms']
    if before <= 0:
        return "Previous timing unavailable."
    delta = (current['total_ms'] - before) / before * 100
    if abs(delta) < 5:
        return 'Similar warmed performance (within 5%); repeat before drawing conclusions.'
    return f"{abs(delta):.0f}% {'faster' if delta < 0 else 'slower'} than the previous run (warmed inference)."


class BenchmarkWorker(QThread):
    result = Signal(object)
    progress = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = replace(config, source_language="en", target_language=TargetLanguage.CHINESE, translation_enabled=True)

    def run(self):
        engine = None
        try:
            self.progress.emit("Preparing fixed English speech sample…")
            audio, digest = fixture()
            engine = WhisperEngine(self.config, NllbTranslator(self.config))
            self.progress.emit("Loading models (timed separately)…")
            start = time.perf_counter()
            engine.ensure_loaded()
            engine.ensure_translator()
            loading = time.perf_counter() - start
            if self.isInterruptionRequested():
                return
            self.progress.emit("Warming models…")
            engine._transcribe(audio, "transcribe")
            engine._translator.translate(REFERENCE, "en", "zh")
            import psutil
            process = psutil.Process()
            def resources():
                processes = [process, *process.children(recursive=True)]
                cpu = sum(p.cpu_times().user + p.cpu_times().system for p in processes)
                rss = sum(p.memory_info().rss for p in processes) / 1024 ** 2
                return cpu, rss
            cpu_start, memory_start = resources()
            measurement_start = time.perf_counter()
            peak_memory = memory_start
            stt, mt = [], []
            for index in range(3):
                if self.isInterruptionRequested():
                    return
                self.progress.emit(f"Measuring run {index + 1} of 3…")
                start = time.perf_counter()
                transcript, _ = engine._transcribe(audio, "transcribe")
                stt.append((time.perf_counter() - start) * 1000)
                start = time.perf_counter()
                translation = engine._translator.translate(REFERENCE, "en", "zh")
                mt.append((time.perf_counter() - start) * 1000)
                peak_memory = max(peak_memory, resources()[1])
            cpu_end, _ = resources()
            cpu_share = (cpu_end - cpu_start) / (time.perf_counter()-measurement_start) / (psutil.cpu_count() or 1) * 100
            result = {"protocol": 1, "fixture": digest, "date": datetime.now(timezone.utc).isoformat(),
                      "preset": self.config.quality_mode.value, "backend": engine.active_backend,
                      "model": self.config.model_size if self.config.backend == 'cpu' else self.config.vulkan_model,
                      "cpu_threads": self.config.cpu_threads, "translation_threads": self.config.translation_threads,
                      "beam_size": self.config.beam_size, "translation_beam_size": self.config.translation_beam_size,
                      "cpu_percent": cpu_share, "memory_mb": peak_memory,
                      "audio_seconds": len(audio) / 16000, "loading_seconds": loading,
                      "stt_ms": statistics.median(stt), "mt_ms": statistics.median(mt),
                      "total_ms": statistics.median([a + b for a,b in zip(stt,mt)]),
                      "transcript": transcript, "translation": translation,
                      "platform": platform.platform(), "reference": REFERENCE}
            runs = read_json("benchmarks.json", [])
            if not isinstance(runs, list):
                runs = []
            result['comparison'] = compare_results(result, runs[-1] if runs else None)
            write_json("benchmarks.json", (runs + [result])[-20:])
            self.result.emit(result)
        except Exception as exc:
            self.result.emit({"error": str(exc)})
        finally:
            if engine:
                engine.close()

if __name__ == '__main__':
    import argparse
    import json
    from PySide6.QtCore import QCoreApplication
    from core.config import AppConfig, QualityMode
    parser = argparse.ArgumentParser(description='Run the fixed-fixture GrammAI performance comparison')
    parser.add_argument('--preset', action='append', choices=[mode.value for mode in QualityMode])
    args = parser.parse_args()
    app = QCoreApplication([])
    for preset in args.preset or ['balanced']:
        config = AppConfig(quality_mode=QualityMode(preset))
        config.apply_quality()
        worker = BenchmarkWorker(config)
        results = []
        worker.result.connect(results.append)
        worker.progress.connect(lambda message: print(message.encode('ascii', errors='replace').decode(), flush=True))
        worker.run()
        if not results or 'error' in results[0]:
            raise SystemExit(str(results))
        print(json.dumps(results[0], ensure_ascii=True, indent=2), flush=True)
