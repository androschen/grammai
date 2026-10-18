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

    def save(self,update,notes='',reviewed=False):
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
        if reviewed:
            item['reviewed_by_user']=True
            item['reviewed_at']=datetime.now(timezone.utc).isoformat()
        self._write(items)
        return item

    def _write(self,items):
        if len(items)>MAX_PHRASES:
            raise ValueError('Learning deck reached its 1,000-card limit.')
        size=len(json.dumps(items,ensure_ascii=False,indent=2).encode('utf-8'))
        if size>MAX_BYTES:
            raise ValueError('Phrasebook reached its 2 MB limit. Delete entries before saving more.')
        write_json('phrases.json',items)

    def update_card(self,identifier,native_text,target_text,notes,reviewed):
        if not reviewed:
            raise ValueError('Confirm that you checked this sentence and its meaning before saving.')
        if not native_text.strip() or not target_text.strip() or any(len(x)>4000 for x in (native_text,target_text,notes)):
            raise ValueError('Original and meaning are required; keep each field within 4,000 characters.')
        from ml.phonetics import phonetics_auto
        items=self.items()
        item=next((x for x in items if x['id']==identifier),None)
        if item is None:
            raise ValueError('This card was deleted. Reopen the deck.')
        changed=(item.get('native_text'),item.get('target_text'))!=(native_text.strip(),target_text.strip())
        item.update(native_text=native_text.strip(),target_text=target_text.strip(),notes=notes.strip(),
                    native_phonetics=phonetics_auto(native_text.strip()),phonetics=phonetics_auto(target_text.strip()),
                    reviewed_by_user=True,reviewed_at=datetime.now(timezone.utc).isoformat())
        if changed:
            item.pop('due_at',None);item.pop('interval_days',None)
        self._write(items)

    def grade(self,identifier,remembered,now=None):
        from datetime import timedelta
        now=now or datetime.now(timezone.utc)
        items=self.items();item=next((x for x in items if x['id']==identifier),None)
        if item is None or item.get('reviewed_by_user') is not True:
            raise ValueError('Review and confirm this card before practising it.')
        interval=max(0,min(365,int(item.get('interval_days',0))))
        interval=min(365,max(1,interval*2)) if remembered else 0
        item.update(interval_days=interval,last_practised_at=now.isoformat(),
                    due_at=(now+timedelta(days=interval,minutes=0 if remembered else 10)).isoformat())
        self._write(items)

    def due(self,language='',now=None):
        now=now or datetime.now(timezone.utc)
        result=[]
        for item in self.items():
            if item.get('reviewed_by_user') is not True or (language and item.get('source_language')!=language):
                continue
            try:
                due=datetime.fromisoformat(item.get('due_at',''))
                if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
            except (TypeError,ValueError):due=now
            if due<=now:result.append(item)
        return result

    def delete(self,identifier):
        write_json('phrases.json',[x for x in self.items() if x['id']!=identifier])

    def clear(self):
        write_json('phrases.json',[])

    def stats(self):
        path=data_dir()/'phrases.json'
        return {'count':len(self.items()),'bytes':path.stat().st_size if path.is_file() else 0,
                'limit_bytes':MAX_BYTES,'limit_count':MAX_PHRASES}
