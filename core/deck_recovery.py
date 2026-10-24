"""Recover this app's cards from a launcher's redirected AppData cache."""
import json,os,shutil,tempfile
from pathlib import Path
from uuid import uuid4
from core.phrasebook import MAX_BYTES,MAX_PHRASES
from core.preferences import data_dir


def _read(path):
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value,list) or any(not isinstance(x,dict) or not isinstance(x.get('id'),str) or not x['id'] for x in value):
        raise ValueError('Invalid saved-card format; recovery left it unchanged.')
    return value


def recover_deck(folder=None,sources=None,dry_run=False):
    folder=Path(folder) if folder is not None else data_dir()
    target=folder/'phrases.json'
    if sources is None:
        local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
        sources=sorted((local/'Packages').glob('OpenAI.Codex_*/LocalCache/Local/GrammAI/phrases.json'))
    before=target.read_bytes() if target.is_file() else None
    existing=_read(target) if before is not None else []
    merged=list(existing);ids={x['id'] for x in merged};used=[]
    for source in map(Path,sources):
        if not source.is_file():continue
        # The apparent LocalAppData path can be redirected to this very same file.
        if target.is_file() and os.path.samefile(source,target):continue
        for item in _read(source):
            if item['id'] not in ids:merged.append(item);ids.add(item['id'])
        used.append(str(source))
    added=len(merged)-len(existing)
    result={'target':str(target),'existing':len(existing),'recovered':added,'total':len(merged),'sources':used,'dry_run':dry_run}
    if not added or dry_run:return result
    encoded=json.dumps(merged,ensure_ascii=False,indent=2).encode('utf-8')
    if len(merged)>MAX_PHRASES or len(encoded)>MAX_BYTES:
        raise ValueError('Recovery exceeds the saved-card quota; files were left unchanged.')
    folder.mkdir(parents=True,exist_ok=True)
    if before is not None:
        backup=folder/('phrases.before-recovery-'+uuid4().hex[:8]+'.bak')
        shutil.copy2(target,backup)
        if backup.read_bytes()!=before:raise OSError('Backup verification failed; recovery stopped.')
        result['backup']=str(backup)
    with tempfile.NamedTemporaryFile(dir=folder,prefix='phrases-recovery-',suffix='.tmp',delete=False) as f:
        f.write(encoded);f.flush();os.fsync(f.fileno());staged=Path(f.name)
    current=target.read_bytes() if target.is_file() else None
    if current!=before:
        staged.unlink();raise OSError('Saved cards changed during recovery; retry without overwriting them.')
    if before is None:
        # Atomic create, rather than replacing a card saved concurrently by the app.
        try:os.link(staged,target)
        finally:staged.unlink()
    else:os.replace(staged,target)
    if len(_read(target))!=len(merged):raise OSError('Recovered-card verification failed.')
    return result
