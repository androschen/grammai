"""Offline NLLB/Qwen comparison on public starter cases; no personal input saved."""
import argparse
import json
from pathlib import Path
from core.config import AppConfig
from core.translation_compare import SAMPLES,compare_translations
from ml.local_analysis import LocalAnalysisRuntime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=2,help='Number of public starter cases, 1–8')
    args=parser.parse_args()
    if not 1<=args.samples<=len(SAMPLES):parser.error('Choose 1–8 starter cases')
    config=AppConfig()
    runtime=LocalAnalysisRuntime();results=[]
    try:
        for label,source,target,text in SAMPLES[:args.samples]:
            result=compare_translations(config,{'text':text,'source':source,'target':target},runtime,
                lambda message:print(message,flush=True))
            results.append(dict(result,label=label))
            print(json.dumps(result,ensure_ascii=True),flush=True)
    finally:runtime.close()
    output=Path(__file__).resolve().parents[1]/'models'/'translation-comparison.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'note':'Public starter examples only; human meaning review required. Not an accuracy score.',
        'comparisons':results},ensure_ascii=False,indent=2),encoding='utf8')
    print('Report: '+str(output))


if __name__=='__main__':main()
