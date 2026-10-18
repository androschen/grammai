"""Local text-only comparison; no downloads, quality claims, or saved transcripts."""
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from ml.translator import NllbTranslator,_looks_like_ct2
from ml.qwen_translator import QwenTranslator,translation_body

SAMPLES=(
    ('Indonesian · informal pronoun','id','en','gua beli nasi dulu'),
    ('Indonesian · literal cave','id','en','Ada gua di gunung itu.'),
    ('Indonesian · casual refusal','id','en','Gue nggak jadi ikut, besok aja ya.'),
    ('Chinese · casual invitation','zh','en','我们先去吃饭吧。'),
    ('Chinese · figurative expression','zh','id','别放我鸽子啊。'),
    ('Thai · casual invitation','th','en','ไปกินข้าวกันเถอะ'),
    ('English · idiom','en','id','You call the shots.'),
    ('English · informal speech','en','zh',"I'm gonna grab a bite, wanna come?"),
)


class OfflineNllbTranslator(NllbTranslator):
    def _resolve_model_dir(self):
        path=Path.home()/'.grammai/models/nllb-200-distilled-600M-int8'
        if not _looks_like_ct2(path):
            raise ValueError('NLLB is not installed. Set up normal translation first; comparison never downloads models.')
        return path


def compare_translations(config,payload,runtime,progress=lambda message:None,cancelled=lambda:False):
    text=payload.get('text','')
    source,target=payload.get('source'),payload.get('target')
    if not isinstance(text,str):
        raise ValueError('Enter a source transcript.')
    translation_body(text,source,target)  # Validate before loading either model.
    if source==target:
        raise ValueError('Choose different source and target languages for comparison.')
    records=[]
    local_config=replace(config,analysis_provider='local',analysis_reasoning=False)
    nllb=OfflineNllbTranslator(local_config)
    qwen=QwenTranslator(local_config,runtime)
    try:
        for engine,translator in (('nllb',nllb),('qwen',qwen)):
            if cancelled():
                raise InterruptedError('Comparison cancelled')
            record={'engine':engine}
            try:
                progress('Loading '+engine.upper()+' for translation comparison')
                started=perf_counter()
                if engine=='qwen':
                    qwen.ensure_loaded(progress,cancelled)
                else:
                    nllb.ensure_loaded()
                record['loading_ms']=(perf_counter()-started)*1000
                if cancelled():
                    raise InterruptedError('Comparison cancelled')
                progress('Translating with '+engine.upper())
                started=perf_counter()
                translated=(qwen.translate(text,source,target,cancelled) if engine=='qwen'
                    else nllb.translate(text,source,target))
                if not translated:
                    raise ValueError('Translator returned no text.')
                record.update(text=translated,translation_ms=(perf_counter()-started)*1000)
                if engine=='qwen':
                    record['model']=runtime.paths(local_config)[1].name
            except InterruptedError:
                raise
            except Exception as exc:
                record['error']=str(exc)
            records.append(record)
    finally:
        nllb.close()
    if cancelled():
        raise InterruptedError('Comparison cancelled')
    return {'text':text.strip(),'source':source,'target':target,'results':records,
        'protocol':'single-sentence-v1','context_used':False}
