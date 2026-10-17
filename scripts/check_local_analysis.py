"""Repeatable, synthetic four-language check. Never captures user audio.

Run: python -m scripts.check_local_analysis [--baseline]
Requires files installed with python -m core.local_assets.
"""
import argparse
import json
from time import perf_counter
from core.config import AppConfig
from core.local_assets import ASSET_ROOT
from ml.context_analysis import analyze
from ml.local_analysis import LocalAnalysisRuntime

CASES=[
    {'name':'English idiom','source_language':'en','target_language':'id',
     'selected_sentence':'You call the shots.', 'original_translation':'Kamu menembak.',
     'preceding_sentences':[{'text':'You are in charge of choosing the restaurant.','language':'en'}],
     'review_hint':'The listener makes the decision; no literal shooting.'},
    {'name':'Indonesian colloquial speech','source_language':'id','target_language':'en',
     'selected_sentence':'Gue nggak enakan nolak dia.', 'original_translation':'I am not comfortable rejecting him.',
     'preceding_sentences':[{'text':'Dia minta tolong lagi, padahal gue sibuk.','language':'id'}],
     'review_hint':'Reluctance or difficulty saying no; casual tone.'},
    {'name':'Chinese idiom','source_language':'zh','target_language':'id',
     'selected_sentence':'他又放我鸽子了。', 'original_translation':'Dia melepaskan merpatiku lagi.',
     'preceding_sentences':[{'text':'我们约好一起吃饭，可他没来。','language':'zh'}],
     'review_hint':'Someone stood the speaker up, not literal pigeons.'},
    {'name':'Thai social nuance','source_language':'th','target_language':'id',
     'selected_sentence':'ไม่เป็นไร เกรงใจเขา', 'original_translation':'Tidak apa-apa, takut padanya.',
     'preceding_sentences':[{'text':'เขาช่วยเรามาเยอะแล้ว ไม่อยากรบกวนอีก','language':'th'}],
     'review_hint':'Consideration/reluctance to impose, not necessarily fear.'},
]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',action='store_true',help='Also compare existing local NLLB translation')
    parser.add_argument('--fast',action='store_true',help='Disable deeper reasoning to compare speed and quality')
    args=parser.parse_args()
    config=AppConfig(analysis_enabled=True,analysis_explanation_language='id',analysis_reasoning=not args.fast)
    runtime=LocalAnalysisRuntime()
    report={'model':'Qwen3-4B-Q4_K_M','deeper_reasoning':config.analysis_reasoning,
        'quality':'Human review required; no automatic accuracy score','cases':[]}
    translator=None
    try:
        started=perf_counter()
        runtime.ensure_loaded(config,lambda message:print(message,flush=True))
        report['loading_seconds']=perf_counter()-started
        report['gpu_status']=runtime.status
        for case in CASES:
            payload={key:value for key,value in case.items() if key not in ('name','review_hint')}
            started=perf_counter()
            try:
                result=analyze(config,payload,runtime)
            except Exception as exc:
                result={'error':str(exc)}
            record=dict(case,result=result,analysis_seconds=perf_counter()-started)
            report['cases'].append(record)
            print(json.dumps({'case':case['name'],'seconds':record['analysis_seconds'],'result':result},ensure_ascii=True),flush=True)
        if args.baseline:
            from ml.translator import NllbTranslator
            translator=NllbTranslator(config)
            started=perf_counter()
            translator.ensure_loaded()
            report['nllb_loading_seconds']=perf_counter()-started
            for record in report['cases']:
                started=perf_counter()
                record['nllb_translation']=translator.translate(record['selected_sentence'],record['source_language'],record['target_language'])
                record['nllb_seconds']=perf_counter()-started
        ASSET_ROOT.mkdir(parents=True,exist_ok=True)
        output=ASSET_ROOT/'synthetic-analysis-check.json'
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Report: '+str(output),flush=True)
    finally:
        runtime.close()
        if translator:
            translator.close()


if __name__=='__main__':
    main()
