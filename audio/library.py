"""Persistent, content-addressed Opus clips. Only explicit card saves write audio."""
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import RLock
import os
import re
import tempfile
from functools import wraps
import numpy as np
from core.preferences import data_dir

_LOCK = RLock()
_NAME = re.compile(r"[0-9a-f]{64}\.ogg")
MAX_SECONDS = 60


def audio_transaction(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with _LOCK:return function(*args, **kwargs)
    return guarded


class AudioLimitError(ValueError):
    pass


class AudioLibrary:
    def __init__(self, limit_mb=250):
        self.limit_bytes = max(1, int(limit_mb * 1024**2))
        self.folder = data_dir() / 'audio'

    def path(self, name):
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError('Invalid saved audio reference.')
        path = self.folder / name
        if path.is_symlink():
            raise ValueError('Saved audio must be a managed file.')
        return path

    def available(self, item):
        try:
            path = self.path((item.get('audio') or {}).get('file', ''))
            return path.is_file() and path.stat().st_size <= 1024**2
        except (ValueError, OSError, AttributeError):
            return False

    def stats(self, items=()):
        refs = {(x.get('audio') or {}).get('file') for x in items}
        total = unused = count = 0
        if self.folder.is_dir():
            for path in self.folder.iterdir():
                if _NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink():
                    size = path.stat().st_size
                    total += size; count += 1
                    if path.name not in refs: unused += size
        return dict(bytes=total, unused_bytes=unused, clips=count, limit_bytes=self.limit_bytes)

    def save(self, audio, sample_rate=16000):
        import av
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if sample_rate != 16000 or not 0 < len(audio) <= sample_rate * MAX_SECONDS or not np.isfinite(audio).all():
            raise ValueError('A finite original clip of at most 60 seconds is required.')
        pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2')
        name = sha256(pcm.tobytes()).hexdigest() + '.ogg'
        with _LOCK:
            existing=self.path(name)
            if existing.is_file():
                return dict(file=name,duration=round(len(audio)/sample_rate,3),bytes=existing.stat().st_size,codec='opus',sample_rate=sample_rate)
        stream_bytes = BytesIO()
        with av.open(stream_bytes, 'w', format='ogg') as output:
            stream = output.add_stream('libopus', rate=sample_rate)
            stream.layout = 'mono'; stream.bit_rate = 24000
            frame = av.AudioFrame.from_ndarray((pcm.astype(np.float32)/32767)[None, :], format='flt', layout='mono')
            frame.sample_rate = sample_rate; frame.time_base = Fraction(1, sample_rate)
            for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(None): output.mux(packet)
        encoded = stream_bytes.getvalue()
        with _LOCK:
            path = self.path(name)
            if not path.exists():
                if self.stats()['bytes'] + len(encoded) > self.limit_bytes:
                    raise AudioLimitError('Audio storage is full. Turn off Include original audio to save text only, or manage audio in Settings → Storage.')
                self.folder.mkdir(parents=True, exist_ok=True)
                fd, temp = tempfile.mkstemp(prefix='clip-', suffix='.tmp', dir=self.folder)
                try:
                    with os.fdopen(fd, 'wb') as handle:
                        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
                    Path(temp).replace(path)
                finally:
                    Path(temp).unlink(missing_ok=True)
            size = path.stat().st_size
        return dict(file=name, duration=round(len(audio)/sample_rate, 3), bytes=size, codec='opus', sample_rate=sample_rate)

    def load(self, name):
        import av
        path = self.path(name)
        if not path.is_file() or path.stat().st_size > 1024**2:
            raise ValueError('Saved audio is missing or unavailable. Your card text is still safe.')
        chunks = []; count = 0
        with av.open(str(path)) as source:
            resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)
            for frame in source.decode(audio=0):
                for converted in resampler.resample(frame):
                    chunk = converted.to_ndarray().reshape(-1)
                    count += len(chunk)
                    if count > 16000 * MAX_SECONDS: raise ValueError('Saved audio exceeds the replay limit.')
                    chunks.append(chunk)
            chunks.extend(frame.to_ndarray().reshape(-1) for frame in resampler.resample(None))
        if not chunks: raise ValueError('Saved audio is empty.')
        return np.concatenate(chunks)

    def cleanup(self, items):
        """Explicit cleanup only; unreadable decks must be rejected by the caller."""
        removed = 0
        with _LOCK:
            current=items() if callable(items) else items
            refs = {(x.get('audio') or {}).get('file') for x in current}
            if not self.folder.is_dir(): return 0
            for path in self.folder.iterdir():
                if _NAME.fullmatch(path.name) and path.name not in refs and path.is_file() and not path.is_symlink():
                    removed += path.stat().st_size; path.unlink()
        return removed
