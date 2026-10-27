"""Bounded storage snapshots, reviewed cleanup and local learning backups."""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import json,os,re,tempfile,zipfile
from audio.library import AudioLibrary,audio_transaction
from core.phrasebook import Phrasebook
from core.preferences import data_dir


def references(items):
    refs=set()
    for item in items:
        audio=item.get('audio')
        if audio and not isinstance(audio,dict):raise ValueError('Card audio references cannot be read; cleanup is disabled.')
        if isinstance(audio,dict) and audio.get('file'):
            name=audio['file']
            AudioLibrary().path(name)  # Reject malformed/unsafe references before any cleanup.
            refs.add(name)
    return refs


@audio_transaction
def audio_snapshot(limit_mb=250):
    items=Phrasebook().items(force=True);refs=references(items);library=AudioLibrary(limit_mb)
    total=count=0;unused=[]
    if library.folder.is_dir():
        for file in library.folder.iterdir():
            if not re.fullmatch(r'[0-9a-f]{64}\.ogg',file.name) or file.is_symlink() or not file.is_file():continue
            stat=file.stat();total+=stat.st_size;count+=1
            if file.name not in refs:unused.append(dict(name=file.name,bytes=stat.st_size,mtime_ns=stat.st_mtime_ns))
    return dict(bytes=total,clips=count,unused_bytes=sum(x['bytes'] for x in unused),unused_files=unused,limit_bytes=library.limit_bytes)


@audio_transaction
def cleanup_recordings(preview,limit_mb=250):
    # Only the reviewed files are eligible. References are re-read under the same save/delete lock.
    refs=references(Phrasebook().items(force=True));library=AudioLibrary(limit_mb);removed=0;count=0
    for item in preview:
        file=library.path(item['name'])
        if item['name'] in refs or not file.is_file():continue
        stat=file.stat()
        if stat.st_size!=item['bytes'] or stat.st_mtime_ns!=item['mtime_ns']:continue
        file.unlink();removed+=stat.st_size;count+=1
    return dict(removed_bytes=removed,removed_files=count,stats=audio_snapshot(limit_mb))


@audio_transaction
def _backup_snapshot():
    items=Phrasebook().items(force=True)
    return len(items),json.dumps(items,ensure_ascii=False,indent=2).encode('utf8'),references(items)


@audio_transaction
def _backup_clip(name):
    file=AudioLibrary().path(name)
    if not file.is_file() or file.stat().st_size>1024**2:return None
    return file.read_bytes()


def export_deck(destination):
    """Atomic local archive; short per-clip locks keep card saves responsive."""
    count,raw,refs=_backup_snapshot()
    destination=Path(destination).absolute()
    # A backup must never replace a card store, recording or application configuration.
    if destination.suffix.lower()!='.zip':raise ValueError('Choose a .zip backup file.')
    if destination.resolve().is_relative_to((data_dir()/'audio').resolve()):raise ValueError('Save backups outside the recordings folder.')
    if destination.is_symlink():raise ValueError('Choose a regular backup file location.')
    fd,temporary=tempfile.mkstemp(prefix='.grammai-backup-',suffix='.tmp',dir=destination.parent);os.close(fd);temporary=Path(temporary)
    audio=[];missing=[]
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('phrases.json',raw,compress_type=zipfile.ZIP_DEFLATED)
            for name in sorted(refs):
                payload=_backup_clip(name)
                if payload is None:missing.append(name);continue
                archive.writestr('audio/'+name,payload)
                audio.append(dict(file='audio/'+name,bytes=len(payload),sha256=sha256(payload).hexdigest()))
            from core.version import APP_VERSION
            manifest=dict(kind='grammai-learning-deck',schema=1,app_version=APP_VERSION,created_at=datetime.now(timezone.utc).isoformat(),cards=count,cards_sha256=sha256(raw).hexdigest(),recordings=audio,missing_recordings=missing)
            archive.writestr('manifest.json',json.dumps(manifest,indent=2),compress_type=zipfile.ZIP_DEFLATED)
        with temporary.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())
        temporary.replace(destination)
        return dict(path=str(destination),cards=count,recordings=len(audio),missing_recordings=len(missing),bytes=destination.stat().st_size)
    finally:temporary.unlink(missing_ok=True)
