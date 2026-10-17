"""Measure one manual recheck on cached public Mandarin audio; no downloads."""
import argparse
import hashlib
import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

import av
import numpy as np
import psutil
from PySide6.QtCore import QCoreApplication
from core.config import AppConfig
from core.events import SubtitleUpdate
from core.gpu_monitor import WindowsGpuMonitor
from core.speech_assets import installed_paths
from ml.review import ReviewWorker
from scripts.benchmark_speech import character_errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('cpu','vulkan'),default='vulkan')
    parser.add_argument('--sample',type=int,default=1,help='Zero-based cached sample index')
    args=parser.parse_args()
    os.environ['HF_HUB_OFFLINE']='1'
    app=QCoreApplication.instance() or QCoreApplication([])
    root=Path(__file__).resolve().parents[1]/'models'/'speech'
    report=json.loads((root/'mandarin-speech-comparison-vulkan.json').read_text(encoding='utf8'))
    sample=report['profiles'][0]['records'][args.sample]
    path=root/'mandarin-benchmark'/sample['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sample['sha256']:
        raise RuntimeError('Cached audio checksum changed')
    resampler=av.AudioResampler(format='fltp',layout='mono',rate=16000)
    frames=[]
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            frames.extend(x.to_ndarray().reshape(-1) for x in resampler.resample(frame))
        frames.extend(x.to_ndarray().reshape(-1) for x in resampler.resample(None))
    audio=np.concatenate(frames).astype(np.float32)
    executable,model=installed_paths()
    config=replace(AppConfig(),backend=args.backend,source_language='zh',
        vulkan_executable=str(executable),vulkan_model=str(model))
    original=SubtitleUpdate('', '',sample['streamed_transcript'],source_language='zh',target_language='id')
    worker=ReviewWorker(config,dict(update=original,text=original.native_text,source='zh',target='id',recheck=True,audio=audio))
    results=[]
    worker.result.connect(results.append)
    stop=threading.Event()
    samples=[]
    def monitor():
        gpu=WindowsGpuMonitor()
        process=psutil.Process()
        try:
            while not stop.wait(.1):
                children=process.children(recursive=True)
                pids=[process.pid]+[p.pid for p in children]
                memory=process.memory_info().rss
                for child in children:
                    try:
                        memory+=child.memory_info().rss
                    except psutil.Error:
                        pass
                samples.append(dict(gpu.sample(pids),rss_mb=memory/1024**2))
        finally:
            gpu.close()
    thread=threading.Thread(target=monitor,daemon=True)
    thread.start()
    started=time.perf_counter()
    try:
        worker.run()
    finally:
        stop.set()
        thread.join(timeout=3)
    if not results or 'error' in results[0]:
        raise RuntimeError(results[0].get('error') if results else 'No result')
    result=results[0]
    update=result['update']
    def peak(key):
        values=[sample[key] for sample in samples if sample.get(key) is not None]
        return max(values) if values else None
    output=dict(dataset='Google FLEURS Mandarin dev (CC BY 4.0)',sample=sample['file'],
        backend=args.backend,audio_seconds=len(audio)/16000,mode=result['mode'],
        wall_seconds=time.perf_counter()-started,inference_and_loading_ms=result['duration_ms'],
        original_transcript=original.native_text,rechecked_transcript=update.native_text,
        translation=update.target_text,target_language='id',
        original_character_errors=character_errors(sample['reference'],original.native_text)[0],
        rechecked_character_errors=character_errors(sample['reference'],update.native_text)[0],
        peak_gpu_percent=peak('gpu_percent'),peak_gpu_memory_mb=peak('gpu_memory_mb'),peak_process_tree_rss_mb=peak('rss_mb'),
        notes='One cached read-speech sample. Cold model loading included. GPU peaks sampled at 100ms; not sustained utilization. Translation meaning requires human review. This runs alone; it does not measure concurrent live subtitle delay.')
    destination=root/'manual-recheck-comparison.json'
    destination.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({key:output[key] for key in ('wall_seconds','original_character_errors','rechecked_character_errors','peak_gpu_percent','peak_gpu_memory_mb')},ensure_ascii=True))
    print('Report: '+str(destination))


if __name__=='__main__':
    main()
