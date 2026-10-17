"""Opt-in, text-only phrasebook with a hard serialized-size quota."""
from datetime import datetime,timezone
import json
from uuid import uuid4
from core.preferences import read_json,write_json,data_dir

MAX_PHRASES=1000
MAX_BYTES=2*1024*1024


class Phrasebook:
    def items(self):
        path=data_dir()/'phrases.json'
        try:
            stat=path.stat()
            key=(str(path),stat.st_mtime_ns,stat.st_size)
        except OSError:
            key=(str(path),None,0)
        if key!=getattr(self,'_cache_key',None):
            items=read_json('phrases.json',[])
            self._cache=[x for x in items if isinstance(x,dict) and isinstance(x.get('id'),str)] if isinstance(items,list) else []
            self._cache_key=key
        return [dict(x) for x in self._cache]

    def save(self,update,notes=''):
        fields={'native_text':update.native_text,'target_text':update.target_text,
                'phonetics':update.phonetics,'native_phonetics':update.native_phonetics,
                'source_language':update.source_language,'target_language':update.target_language,
                'notes':notes.strip()}
        if any(len(value)>4000 for value in fields.values()):
            raise ValueError('Each text field must be at most 4,000 characters.')
        items=self.items()
        existing=next((i for i,item in enumerate(items) if all(item.get(k)==fields[k] for k in ('native_text','target_text','source_language','target_language'))),None)
        if existing is not None:
            item=dict(items[existing],**dict(fields,notes=fields['notes'] or items[existing].get('notes','')))
            items[existing]=item
        else:
            if len(items)>=MAX_PHRASES:
                raise ValueError('Phrasebook is full (1,000 phrases). Delete an entry before saving another.')
            item=dict(fields,id=uuid4().hex,saved_at=datetime.now(timezone.utc).isoformat())
            items.append(item)
        size=len(json.dumps(items,ensure_ascii=False,indent=2).encode('utf-8'))
        if size>MAX_BYTES:
            raise ValueError('Phrasebook reached its 2 MB limit. Delete entries before saving more.')
        write_json('phrases.json',items)
        return item

    def delete(self,identifier):
        write_json('phrases.json',[x for x in self.items() if x['id']!=identifier])

    def clear(self):
        write_json('phrases.json',[])

    def stats(self):
        path=data_dir()/'phrases.json'
        return {'count':len(self.items()),'bytes':path.stat().st_size if path.is_file() else 0,
                'limit_bytes':MAX_BYTES,'limit_count':MAX_PHRASES}
