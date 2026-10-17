"""Bounded, session-only replay clips. No audio files are written."""
from collections import OrderedDict
from threading import RLock
from time import monotonic
import numpy as np


class ReplayStore:
    def __init__(self, sample_rate=16000, seconds=60, clock=monotonic):
        self.sample_rate=sample_rate
        self.seconds=seconds
        self.max_bytes=int(sample_rate*seconds*4)
        self._clock=clock
        self._items=OrderedDict()
        self._bytes=0
        self._lock=RLock()

    def _prune(self):
        now=self._clock()
        for key in list(self._items):
            when,audio=self._items[key]
            if now-when>self.seconds:
                self._bytes-=audio.nbytes
                del self._items[key]

    def add(self,key,audio,captured_at=None):
        with self._lock:
            self._prune()
            when=self._clock() if captured_at is None else captured_at
            data=np.ascontiguousarray(audio,dtype=np.float32)
            if data.nbytes>self.max_bytes or self._clock()-when>self.seconds:
                return ''
            if key in self._items:
                self._bytes-=self._items.pop(key)[1].nbytes
            while self._items and self._bytes+data.nbytes>self.max_bytes:
                self._bytes-=self._items.popitem(last=False)[1][1].nbytes
            self._items[key]=(when,data.copy())
            self._bytes+=data.nbytes
            return key

    def get(self,key):
        with self._lock:
            self._prune()
            item=self._items.get(key)
            return None if item is None else item[1].copy()

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes=0

    def stats(self):
        with self._lock:
            self._prune()
            return {'clips':len(self._items),'bytes':self._bytes,'limit_bytes':self.max_bytes}
