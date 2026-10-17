"""Mandarin audio/reference comparison, with local inference and explicit data setup."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import tarfile
import time
import unicodedata
import urllib.request
from collections import deque
from functools import lru_cache
import numpy as np
from dataclasses import replace
from core.config import AppConfig
from core.speech_assets import ROOT,installed_paths

DATA_REVISION='70bb2e84b976b7e960aa89f1c648e09c59f894dd'
DATA_BASE=f'https://huggingface.co/datasets/google/fleurs/resolve/{DATA_REVISION}/data/cmn_hans_cn'
DATA_DIR=ROOT/'mandarin-benchmark'


@lru_cache(maxsize=1)
def converter():
    try:
        from opencc import OpenCC
        return OpenCC('t2s')
    except ImportError:
        return None


def normalized(text,convert_script=True):
    text=unicodedata.normalize('NFKC',text).casefold()
    if convert_script and converter() is not None:
        text=converter().convert(text)
    return ''.join(ch for ch in text if ch.isalnum())


def character_errors(reference,hypothesis,convert_script=True):
    before,after=normalized(reference,convert_script),normalized(hypothesis,convert_script)
    row=list(range(len(after)+1))
    for i,a in enumerate(before,1):
        following=[i]
        for j,b in enumerate(after,1):
            following.append(min(following[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=following
    return row[-1],len(before)


class LegacySegmenter:
    """Exact pre-change six-second volume-gate baseline, for comparisons only."""
    last_overlap_samples=0
    def __init__(self,config):
        self.config=config
        self.pre=deque(maxlen=max(1,int(.2/config.capture_chunk_seconds)))
        self.parts=[]
        self.samples=self.silence=0

    def push(self,chunk):
        from audio.capture import normalized_rms
        loud=normalized_rms(chunk,self.config.rms_full_scale)>=self.config.noise_threshold
        if not self.parts:
            if not loud:
                self.pre.append(chunk)
                return None
            self.parts.extend(self.pre)
            self.pre.clear()
            self.samples=sum(part.size for part in self.parts)
        self.parts.append(chunk)
        self.samples+=chunk.size
        self.silence=0 if loud else self.silence+chunk.size
        if self.samples<16000*6 and self.silence<16000*.5:
            return None
        audio=np.concatenate(self.parts)
        voiced=self.samples-self.silence
        self.parts=[]
        self.samples=self.silence=0
        return audio if voiced>=16000*.4 else None


def stream_transcript(engine,config,audio,legacy=False):
    from audio.segmentation import SpeechSegmenter,StreamingSpeechDetector
    from ml.transcript import trim_overlap
    segmenter=LegacySegmenter(config) if legacy else SpeechSegmenter(config,StreamingSpeechDetector() if config.speech_detection else None)
    outputs=[]
    previous=''
    seconds=0.
    padded=np.concatenate((audio,np.zeros(16000,dtype=np.float32)))
    for offset in range(0,len(padded),config.chunk_samples):
        segment=segmenter.push(padded[offset:offset+config.chunk_samples])
        if segment is None:
            continue
        start=time.perf_counter()
        raw,_=engine._transcribe(segment,'transcribe')
        seconds+=time.perf_counter()-start
        outputs.append(trim_overlap(previous,raw,segmenter.last_overlap_samples/16000))
        previous=raw
    return ' '.join(outputs),seconds,len(outputs)


def prepare(count):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    manifest=DATA_DIR/'manifest.json'
    if manifest.is_file():
        saved=json.loads(manifest.read_text(encoding='utf-8'))
        if len(saved['clips'])>=count:
            return saved['clips'][:count]
    print('Downloading a small streamed subset of Google FLEURS Mandarin dev (CC BY 4.0)...',flush=True)
    rows=csv.reader(io.StringIO(urllib.request.urlopen(DATA_BASE+'/dev.tsv',timeout=30).read().decode()),delimiter='\t')
    references={row[1]:{'id':row[0],'reference':row[2]} for row in rows if 48000<=int(row[5])<=320000}
    selected=[]
    ids=set()
    # Stream only until enough distinct sentences are found; do not fetch the full corpus.
    with urllib.request.urlopen(DATA_BASE+'/audio/dev.tar.gz',timeout=30) as response,tarfile.open(fileobj=response,mode='r|gz') as package:
        for member in package:
            name=Path(member.name).name
            entry=references.get(name)
            if not member.isfile() or entry is None or entry['id'] in ids or member.size>4*1024**2:
                continue
            raw=package.extractfile(member).read(4*1024**2+1)
            if len(raw)!=member.size:
                raise RuntimeError('Incomplete benchmark audio')
            (DATA_DIR/name).write_bytes(raw)
            selected.append(dict(entry,file=name,sha256=hashlib.sha256(raw).hexdigest()))
            ids.add(entry['id'])
            print(f'Prepared Mandarin sample {len(selected)}/{count}',flush=True)
            if len(selected)>=count:
                break
    if len(selected)<count:
        raise RuntimeError('Not enough benchmark samples')
    manifest.write_text(json.dumps({'dataset':'google/fleurs','configuration':'cmn_hans_cn','split':'dev',
        'revision':DATA_REVISION,'license':'CC BY 4.0','attribution':'Google FLEURS; https://huggingface.co/datasets/google/fleurs',
        'clips':selected},ensure_ascii=False,indent=2),encoding='utf-8')
    return selected


def run_profile(config,clips):
    import av
    from ml.whisper_engine import WhisperEngine
    from ml.transcript import trim_overlap
    from audio.segmentation import SpeechSegmenter,StreamingSpeechDetector
    engine=WhisperEngine(config)
    started=time.perf_counter()
    try:
        engine.ensure_loaded()
        loading=time.perf_counter()-started
        decoded=[]
        for item in clips:
            # Avoid a faster-whisper/PyAV metadata_errors compatibility issue.
            resampler=av.AudioResampler(format='fltp',layout='mono',rate=16000)
            frames=[]
            with av.open(str(DATA_DIR/item['file'])) as container:
                for frame in container.decode(audio=0):
                    frames.extend(converted.to_ndarray().reshape(-1) for converted in resampler.resample(frame))
                frames.extend(converted.to_ndarray().reshape(-1) for converted in resampler.resample(None))
            decoded.append(np.concatenate(frames).astype(np.float32))
        print('Warming '+config.backend+' / '+config.model_size,flush=True)
        engine._transcribe(decoded[0],'transcribe')
        records=[]
        for item,audio in zip(clips,decoded):
            if hashlib.sha256((DATA_DIR/item['file']).read_bytes()).hexdigest()!=item['sha256']:
                raise RuntimeError('Benchmark audio checksum changed')
            started=time.perf_counter()
            transcript,_=engine._transcribe(audio,'transcribe')
            elapsed=time.perf_counter()-started
            errors,characters=character_errors(item['reference'],transcript)
            streamed,stt_seconds,segments=stream_transcript(engine,config,audio)
            legacy,legacy_seconds,_=stream_transcript(engine,config,audio,True)
            stream_errors,_=character_errors(item['reference'],streamed)
            legacy_errors,_=character_errors(item['reference'],legacy)
            raw_errors,_=character_errors(item['reference'],transcript,False)
            records.append(dict(item,transcript=transcript,seconds=elapsed,audio_seconds=len(audio)/16000,
                character_errors=errors,raw_character_errors=raw_errors,reference_characters=characters,streamed_transcript=streamed,
                streamed_errors=stream_errors,streamed_stt_seconds=stt_seconds,segments=segments,
                legacy_streamed_transcript=legacy,legacy_streamed_errors=legacy_errors,legacy_stt_seconds=legacy_seconds))
            print(json.dumps({'backend':config.backend,'model':config.model_size if config.backend=='cpu' else Path(config.vulkan_model).name,'file':item['file'],
                'seconds':round(elapsed,3),'CER':round(errors/max(1,characters),3),
                'streamed_CER':round(stream_errors/max(1,characters),3),'legacy_streamed_CER':round(legacy_errors/max(1,characters),3)},ensure_ascii=True),flush=True)
        total_chars=sum(record['reference_characters'] for record in records)
        return {'backend':config.backend,'model':config.model_size if config.backend=='cpu' else Path(config.vulkan_model).name,
            'beam_size':config.beam_size,'speech_prompt':config.speech_prompt,'loading_seconds':loading,
            'CER':sum(record['character_errors'] for record in records)/max(1,total_chars),
            'streamed_CER':sum(record['streamed_errors'] for record in records)/max(1,total_chars),
            'legacy_streamed_CER':sum(record['legacy_streamed_errors'] for record in records)/max(1,total_chars),
            'median_stt_seconds':statistics.median(record['seconds'] for record in records),
            'real_time_factor':sum(record['seconds'] for record in records)/sum(record['audio_seconds'] for record in records),
            'records':records}
    finally:
        engine.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--download',action='store_true',help='Explicitly download public Mandarin benchmark audio')
    parser.add_argument('--clips',type=int,default=5)
    parser.add_argument('--backend',choices=('cpu','vulkan','all'),default='all')
    parser.add_argument('--segment-seconds',type=float,default=6.)
    parser.add_argument('--silence-seconds',type=float,default=.5)
    parser.add_argument('--volume-boundaries',action='store_true')
    args=parser.parse_args()
    if not 1<=args.clips<=20:
        parser.error('Choose 1-20 clips')
    os.environ['HF_HUB_OFFLINE']='1'
    if args.download:
        clips=prepare(args.clips)
    else:
        clips=json.loads((DATA_DIR/'manifest.json').read_text(encoding='utf-8'))['clips'][:args.clips]
    executable,model=installed_paths()
    base=AppConfig(source_language='zh',translation_enabled=False,speech_max_seconds=args.segment_seconds,
        speech_silence_seconds=args.silence_seconds,speech_detection=not args.volume_boundaries)
    profiles=[replace(base,model_size='base',beam_size=2),replace(base,model_size='small',beam_size=5)] if args.backend!='vulkan' else []
    if args.backend!='cpu':
        profiles.append(replace(base,backend='vulkan',vulkan_executable=str(executable),vulkan_model=str(model),beam_size=2))
    report={'dataset':'Google FLEURS Mandarin dev','revision':DATA_REVISION,
        'script_normalization':'Traditional-to-Simplified OpenCC' if converter() is not None else 'None (install requirements-benchmark.txt)',
        'segment_seconds':args.segment_seconds,
        'silence_seconds':args.silence_seconds,'speech_detection':not args.volume_boundaries,
        'notes':'Small read-speech subset, not informal conversation. Fixed Mandarin language. Punctuation/spacing ignored. No target translations used. Full-clip and streamed errors reported separately; legacy streaming uses the exact previous segmenter.',
        'profiles':[]}
    for config in profiles:
        report['profiles'].append(run_profile(config,clips))
        output=ROOT/('mandarin-speech-comparison'+('' if args.backend=='all' else '-'+args.backend)+'.json')
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Report: '+str(output),flush=True)


if __name__=='__main__':
    main()
