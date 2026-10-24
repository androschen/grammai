"""Opt-in, text-only phrasebook with a hard serialized-size quota."""
from datetime import datetime,timezone
import json
from uuid import uuid4
from core.preferences import write_json,data_dir
import logging

MAX_PHRASES=1000
MAX_BYTES=2*1024*1024


class DeckReadError(ValueError):
    """Unreadable data is not an empty deck and must never be overwritten."""


class Phrasebook:
    def items(self,force=False):
        path=data_dir()/'phrases.json'
        try:
            stat=path.stat()
        except FileNotFoundError:
            self._cache_key=None;self._cache=[]
            return []
        except OSError as exc:
            raise DeckReadError(f'Cannot access saved cards ({type(exc).__name__}). File: {path}') from exc
        key=(str(path),stat.st_mtime_ns,stat.st_size)
        if force or key!=getattr(self,'_cache_key',None):
            try:
                # Read this exact path, and accept BOMs from Windows JSON editors.
                items=json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(items,list) or any(not isinstance(x,dict) or not isinstance(x.get('id'),str) or not x['id'] for x in items):
                    raise ValueError('Invalid deck format')
            except (OSError,ValueError) as exc:
                self._cache_key=None
                logging.warning('Cannot read saved deck %s (%s)',path,type(exc).__name__)
                raise DeckReadError(f'Cannot read saved cards ({type(exc).__name__}). File: {path}') from exc
            self._cache=items;self._cache_key=key
        return [dict(x) for x in self._cache]

    def save(self,update,notes='',reviewed=False):
        fields={'native_text':update.native_text,'target_text':update.target_text,
                'phonetics':update.phonetics,'native_phonetics':update.native_phonetics,
                'source_language':update.source_language,'target_language':update.target_language,
                'notes':notes.strip()}
        if any(len(value)>4000 for value in fields.values()):
            raise ValueError('Each text field must be at most 4,000 characters.')
        items=self.items()
        existing=next((i for i,item in enumerate(items) if item.get('card_type')!='vocabulary' and all(item.get(k)==fields[k] for k in ('native_text','target_text','source_language','target_language'))),None)
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

    def save_vocabulary(self,payload,value,meaning,notes='',target_language='id',reviewed=False):
        """Persist a reviewed expression with its real dialogue, never a generated example."""
        from ml.phrase_explanation import explanation_input
        from ml.phonetics import phonetics_auto
        checked=explanation_input(payload)
        if not reviewed:
            raise ValueError('Check the expression and meaning before saving.')
        phrase=checked['phrase'];sentence=payload['sentence'].strip()
        meaning=meaning.strip();notes=notes.strip()
        if not meaning or target_language not in ('zh','th','en','id'):
            raise ValueError('A meaning and supported explanation language are required.')
        fields=dict(card_type='vocabulary',native_text=phrase,target_text=meaning,
            native_phonetics=phonetics_auto(phrase),phonetics=phonetics_auto(meaning),
            source_language=checked['language'],target_language=target_language,notes=notes,
            example_sentence=sentence,example_translation=str(payload.get('example_translation','')).strip(),
            original_speech=str(payload.get('original_text','')).strip(),
            original_language=checked['original_language'],example_role=checked['text_role'],
            usage=str(value.get('usage','')).strip(),usage_note=str(value.get('usage_note','')).strip(),
            uncertainty=str(value.get('uncertainty','')).strip(),conversation_context=checked['context'])
        from ml.card_explanation import validate_learning, learning_source
        if 'words' in value:
            fields['learning_explanation']=dict(validate_learning(value,checked),language=target_language)
        if any(len(v)>4000 for v in fields.values() if isinstance(v,str)):
            raise ValueError('Each text field must be at most 4,000 characters.')
        items=self.items()
        identity=('native_text','source_language','target_language','example_sentence')
        item=next((x for x in items if x.get('card_type')=='vocabulary' and all(x.get(k)==fields[k] for k in identity)),None)
        if item is None:
            item=dict(id=uuid4().hex,saved_at=datetime.now(timezone.utc).isoformat());items.append(item)
        elif item.get('target_text')!=meaning:
            item.pop('due_at',None);item.pop('interval_days',None)
        if not notes:fields['notes']=item.get('notes','')
        item.update(fields,reviewed_by_user=True,reviewed_at=datetime.now(timezone.utc).isoformat())
        self._write(items)
        return dict(item)

    def _write(self,items):
        if len(items)>MAX_PHRASES:
            raise ValueError('Learning deck reached its 1,000-card limit.')
        size=len(json.dumps(items,ensure_ascii=False,indent=2).encode('utf-8'))
        if size>MAX_BYTES:
            raise ValueError('Phrasebook reached its 2 MB limit. Delete entries before saving more.')
        write_json('phrases.json',items)

    def update_notes(self,identifier,notes):
        if not isinstance(notes,str) or len(notes)>4000:raise ValueError('Keep notes within 4,000 characters.')
        items=self.items();item=next((x for x in items if x['id']==identifier),None)
        if item is None:raise ValueError('This card was deleted. Reopen the deck.')
        item['notes']=notes.strip();self._write(items)

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
        if item.get('card_type')=='vocabulary' and (len(native_text.strip())>120 or native_text.strip() not in item.get('example_sentence','')):
            raise ValueError('The expression must occur in its saved example (up to 120 characters).')
        changed=(item.get('native_text'),item.get('target_text'))!=(native_text.strip(),target_text.strip())
        item.update(native_text=native_text.strip(),target_text=target_text.strip(),notes=notes.strip(),
                    native_phonetics=phonetics_auto(native_text.strip()),phonetics=phonetics_auto(target_text.strip()),
                    reviewed_by_user=True,reviewed_at=datetime.now(timezone.utc).isoformat())
        if changed:
            item.pop('learning_explanation',None)
            item.pop('due_at',None);item.pop('interval_days',None)
        self._write(items)

    def save_explanation(self,identifier,value,language):
        from ml.card_explanation import card_payload,validate_learning,learning_source
        items=self.items();item=next((x for x in items if x['id']==identifier),None)
        if item is None:raise ValueError('This card was deleted. Reopen the deck.')
        payload=card_payload(item)
        item['learning_explanation']=dict(validate_learning(value,payload),language=language)
        self._write(items)
        return dict(item)

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
