"""No-capture, offline diagnostics for a freshly frozen application."""
import json
from pathlib import Path


def smoke_check(report,verify_models=False):
    results={}
    try:
        import numpy as np
        import ctranslate2,soundcard,sentencepiece,tokenizers,av,psutil
        from transformers import AutoTokenizer
        from faster_whisper import WhisperModel
        from audio.segmentation import StreamingSpeechDetector
        from ml.phonetics import phonetics_auto
        from core.events import EventBus,SubtitleUpdate
        from core.config import AppConfig
        from audio.replay import ReplayStore
        from ui.learning import StudyDialog
        from ui.overlay import SubtitleOverlay
        from core.local_assets import managed_paths
        from core.speech_assets import installed_paths
        from PySide6.QtWidgets import QApplication
        results['imports']='ok'
        results['chinese_pronunciation']=bool(phonetics_auto('\u4f60\u597d'))
        results['thai_pronunciation']=bool(phonetics_auto('\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35'))
        results['vad_silence']=StreamingSpeechDetector()(np.zeros(640,dtype=np.float32))<.5
        events=EventBus()
        dialog=StudyDialog(SubtitleUpdate('','Hello','Hello',source_language='en'),AppConfig(),events,ReplayStore(),None)
        dialog.show();QApplication.processEvents()
        results['details']='ok';dialog.reject();dialog.deleteLater()
        overlay=SubtitleOverlay(events,AppConfig());overlay.close();results['overlay']='ok'
        from ui.translation_compare import TranslationComparisonDialog
        comparison=TranslationComparisonDialog(AppConfig(),events)
        comparison.reject();comparison.deleteLater();results['comparison_ui']='ok'
        from ui.settings import SettingsDialog
        settings=SettingsDialog(AppConfig(),events)
        assert settings._translation_mode.count()==3
        settings.reject();settings.deleteLater();results['translation_settings']='ok'
        from ui.deck import LearningDeckDialog
        from core.phrasebook import Phrasebook
        deck=LearningDeckDialog(AppConfig(),Phrasebook())
        deck.reject();deck.deleteLater();results['learning_deck_ui']='ok'
        from ui.phrase_explain import PhraseExplanationDialog
        from core.analysis import AnalysisService
        phrase_service=AnalysisService(events=events,config=AppConfig())
        phrase=PhraseExplanationDialog(AppConfig(),events,phrase_service,
            {'phrase':'gua','sentence':'gua beli nasi dulu','language':'id','original_text':'gua beli nasi dulu','original_language':'id'},Phrasebook())
        # Do not process the queued automatic explanation during a UI-only smoke.
        phrase.reject();phrase.deleteLater();phrase_service.shutdown()
        results['phrase_explanation_ui']='ok'
        results['existing_speech_model']=installed_paths()[1].is_file()
        results['existing_context_model']=managed_paths()[1].is_file()
        if verify_models:
            import os
            os.environ['HF_HUB_OFFLINE']='1'
            from ml.whisper_engine import WhisperEngine
            from ml.translator import NllbTranslator,_looks_like_ct2
            from ml.local_analysis import LocalAnalysisRuntime
            from core.config import TargetLanguage
            from dataclasses import replace
            exe,model=installed_paths()
            config=replace(AppConfig(),backend='vulkan',vulkan_executable=str(exe),vulkan_model=str(model))
            engine=WhisperEngine(config)
            translator=NllbTranslator(config)
            runtime=LocalAnalysisRuntime()
            try:
                engine.ensure_loaded()
                engine._transcribe(np.zeros(16000,dtype=np.float32),'transcribe')
                results['gpu_speech']=engine.active_backend
                if not _looks_like_ct2(Path.home()/'.grammai/models/nllb-200-distilled-600M-int8'):
                    raise RuntimeError('Offline verification requires existing NLLB weights')
                results['translation']=translator.translate('Hello','en','id')
                runtime.ensure_loaded(config,lambda message:None,lambda:False)
                results['gpu_context']=runtime.status
                from core.translation_compare import compare_translations
                results['translation_comparison']=compare_translations(config,
                    {'text':'gua beli nasi dulu','source':'id','target':'en'},runtime)['results']
                if any('error' in record for record in results['translation_comparison']):
                    raise RuntimeError('Packaged translator comparison failed')
                from ml.live_translator import LiveTranslator
                from core.analysis import AnalysisWorker
                live=LiveTranslator(replace(config,translation_mode='context'),translator,runtime,events)
                live.ensure_loaded()
                results['context_translation']=live.translate('gua beli nasi dulu','id','en')
                live.remember('We are buying lunch.','en')
                results['context_translation_with_dialogue']=live.translate('gua beli nasi dulu','id','en')
                reviewed=[]
                worker=AnalysisWorker(config,{'text':'gua beli nasi dulu','source':'id','target':'en',
                    'context':[]},runtime,'refine')
                worker.result.connect(reviewed.append);worker.run()
                if not reviewed or 'error' in reviewed[0]:
                    raise RuntimeError('Packaged automatic review failed')
                results['review_translation']=reviewed[0]['translation']
                from ml.phrase_explanation import explain
                results['phrase_explanation']=explain(config,
                    {'phrase':'gua','sentence':'gua beli nasi dulu','language':'id',
                     'original_text':'gua beli nasi dulu','original_language':'id'},runtime)
                if results['phrase_explanation']['meaning'].strip().casefold()=='gua':
                    raise RuntimeError('Packaged explanation repeated the phrase without defining it')
                live.close()
            finally:
                engine.close();translator.close();runtime.close()
        results['ok']=all(results[key] for key in ('chinese_pronunciation','thai_pronunciation','vad_silence'))
    except Exception:
        import traceback
        results['ok']=False;results['error']=traceback.format_exc()
    if report:
        Path(report).write_text(json.dumps(results,indent=2),encoding='utf8')
    return 0 if results.get('ok') else 1
