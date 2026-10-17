"""Streaming speech boundaries with pre-roll and overlap at forced cuts only."""
from collections import deque
import numpy as np
from audio.capture import normalized_rms


class StreamingSpeechDetector:
    """Reuses faster-whisper's bundled Silero v6 ONNX model on one CPU thread."""
    def __init__(self):
        from faster_whisper.vad import get_vad_model
        self.session=get_vad_model().session
        if {item.name for item in self.session.get_inputs()}!={'input','h','c'}:
            raise RuntimeError('Streaming VAD requires the bundled Silero v6 ONNX interface. Update faster-whisper or use volume gating.')
        self.reset()

    def reset(self):
        self.h=np.zeros((1,1,128),dtype=np.float32)
        self.c=np.zeros_like(self.h)
        self.context=np.zeros(64,dtype=np.float32)
        self.pending=np.empty(0,dtype=np.float32)
        self.probability=0.

    def __call__(self,chunk):
        self.pending=np.concatenate((self.pending,chunk))
        count=self.pending.size//512
        if not count:
            return self.probability
        frames=self.pending[:count*512].reshape(count,512)
        contexts=np.vstack((self.context,frames[:-1,-64:]))
        inputs=np.concatenate((contexts,frames),axis=1).astype(np.float32)
        output,self.h,self.c=self.session.run(None,{'input':inputs,'h':self.h,'c':self.c})
        self.context=frames[-1,-64:].copy()
        self.pending=self.pending[count*512:].copy()
        self.probability=float(np.max(output))
        return self.probability


class SpeechSegmenter:
    def __init__(self,config,detector=None):
        self.config,self.detector=config,detector
        self.pre=deque(maxlen=max(1,round(.24/config.capture_chunk_seconds)))
        self.parts=[]
        self.samples=self.silence=self.voiced=0
        self.current_overlap_samples=self.last_overlap_samples=0

    def push(self,chunk):
        rate=self.config.sample_rate
        level=normalized_rms(chunk,self.config.rms_full_scale)
        if self.detector is None:
            speech=level>=self.config.noise_threshold
        else:
            probability=self.detector(chunk)
            # The user gate controls onset; quiet syllables are retained once speech starts.
            speech=(probability>=.30 or level>=self.config.noise_threshold) if self.parts else (
                probability>=.50 and level>=self.config.noise_threshold)
        if not self.parts:
            if not speech:
                self.pre.append(chunk)
                return None
            self.parts.extend(self.pre)
            self.pre.clear()
            self.samples=sum(part.size for part in self.parts)
            self.voiced=sum(part.size for part in self.parts if normalized_rms(part,self.config.rms_full_scale)>=self.config.noise_threshold*.25)
        self.parts.append(chunk)
        self.samples+=chunk.size
        # VAD can remain positive briefly into silence. Do not treat that tail
        # as new speech and decode a carried word a second time after a forced cut.
        fresh=speech and level>=max(.005,self.config.noise_threshold*.25)
        self.voiced+=chunk.size if fresh else 0
        self.silence=0 if speech else self.silence+chunk.size
        # Give a natural endpoint a small bounded chance before cutting a long
        # phrase. Otherwise a final syllable becomes a new, contextless subtitle.
        grace=.8 if self.detector is not None and self.config.speech_max_seconds>=4 else 0.
        forced=self.samples>=round(rate*(self.config.speech_max_seconds+grace))
        if not forced and self.silence<round(rate*self.config.speech_silence_seconds):
            return None
        audio=np.concatenate(self.parts)
        self.last_overlap_samples=self.current_overlap_samples
        valid=self.voiced>=round(rate*.12) or (self.current_overlap_samples>0 and self.voiced>0)
        if forced and speech and valid:
            overlap=min(round(rate*self.config.speech_overlap_seconds),len(audio))
            carry=audio[-overlap:].copy() if overlap else np.empty(0,dtype=np.float32)
            self.parts=[carry] if overlap else []
            self.samples=overlap
            self.current_overlap_samples=overlap
        else:
            self.parts=[]
            self.samples=self.current_overlap_samples=0
            # A silence boundary needs no repeated audio in the next utterance.
            self.pre.extend([chunk])
        self.silence=self.voiced=0
        return audio if valid else None
