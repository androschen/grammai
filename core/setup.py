"""Setup choices and measured compatibility, shared by onboarding and Settings."""
from dataclasses import replace
from pathlib import Path
from statistics import median
from time import perf_counter
from core.components import ComponentManager,catalog
from core.hardware import system_info,probe_devices,default_threads


def installed_speech(config):
    if config.speech_model_id!='external':return config.speech_model_id
    return 'speech-turbo' if config.backend=='vulkan' else 'external'


def select_configuration(config,speech,processing,ai=False,fast=False):
    c=replace(config,processing_mode=processing,speech_model_id=speech,learning_model_id='qwen' if ai else 'external',translation_model_id='translation-fast' if fast else 'external',setup_completed=True)
    c.backend='vulkan' if speech=='speech-turbo' and processing!='cpu' else 'cpu'
    if speech=='speech-turbo':
        from core.components import resolve
        runtime,model=resolve('speech-runtime'),resolve('speech-turbo')
        if runtime:c.vulkan_executable=str(runtime)
        if model:c.vulkan_model=str(model)
    if ai:
        c.analysis_enabled=True;c.translation_enabled=True;c.translation_mode='fast' if fast else 'context'
    elif fast:
        c.analysis_enabled=False;c.translation_enabled=True;c.translation_mode='fast'
    else:c.analysis_enabled=False;c.translation_enabled=False;c.translation_mode='fast'
    c.cpu_threads=default_threads();c.translation_threads=max(1,min(4,c.cpu_threads//2));c.apply_quality();return c


def required_components(speech,processing,ai,fast=False,backup=False):
    from core.speech_models import components
    ids=list(components(speech))
    if backup and 'speech-cpu' not in ids:ids.append('speech-cpu')
    if ai:ids.extend(['qwen','ai-cpu' if processing=='cpu' else 'ai-vulkan'])
    if ai and (processing=='auto' or (backup and processing!='cpu')):ids.append('ai-cpu')
    if fast:ids.append('translation-fast')
    return list(dict.fromkeys(ids))


def test_configuration(config,progress=lambda m,p:None,cancelled=lambda:False):
    import psutil
    from ml.whisper_engine import WhisperEngine
    from ml.local_analysis import LocalAnalysisRuntime
    from core.benchmark import fixture
    c=replace(config);engine=WhisperEngine(c);ai=LocalAnalysisRuntime();start=perf_counter()
    owner=getattr(cancelled,'__self__',None)
    def abort():
        ai.interrupt()
        speech=getattr(engine,'_vulkan',None)
        process=getattr(speech,'process',None)
        if process is not None and process.poll() is None:
            try:process.terminate()
            except OSError:pass
    if owner is not None:setattr(owner,'abort',abort)
    try:
        progress('Loading selected speech model',0);engine.ensure_loaded(cancelled=cancelled)
        if cancelled():raise InterruptedError('Cancelled')
        audio,_=fixture();timings=[];engine._transcribe(audio,'transcribe')
        for i in range(3):
            if cancelled():raise InterruptedError('Cancelled')
            tick=perf_counter();engine._transcribe(audio,'transcribe');timings.append((perf_counter()-tick)*1000);progress('Measuring speech '+str(i+1)+'/3',20+15*i)
        result=dict(backend=engine.active_backend,speech_ms=median(timings),audio_seconds=len(audio)/16000,loading_and_test_seconds=perf_counter()-start)
        from core.model_info import refinement_enabled
        if c.analysis_enabled or c.translation_mode=='context' or refinement_enabled(c):
            ai.ensure_loaded(c,lambda message:progress(message,75),cancelled)
            ai.complete_json({'messages':[{'role':'user','content':'Reply with the JSON object {"ready":true} only.'}],'max_tokens':24,'chat_template_kwargs':{'enable_thinking':False}}, {'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False},cancelled)
            result['ai_status']=ai.status
            if c.translation_mode=='context':
                from ml.qwen_translator import QwenTranslator
                tick=perf_counter();result['translation_example']=QwenTranslator(c,ai).translate('The meeting starts at three in the afternoon.','en','id',cancelled=cancelled);result['translation_ms']=(perf_counter()-tick)*1000
        if c.translation_enabled and c.translation_mode in ('fast','review'):
            from ml.translator import NllbTranslator
            translator=NllbTranslator(c)
            try:
                tick=perf_counter();result['translation_example']=translator.translate('The meeting starts at three in the afternoon.','en','id');result['translation_ms']=(perf_counter()-tick)*1000
            finally:translator.close()
        processes=[psutil.Process(),*psutil.Process().children(recursive=True)]
        result['memory_mb']=sum(p.memory_info().rss for p in processes if p.is_running())/1024**2
        result['speech_keeps_up']=result['speech_ms']<result['audio_seconds']*1000
        result['keeps_up']=assess_realtime(result)
        progress('Compatibility check complete; this is not an accuracy score.',100);return result
    finally:
        if owner is not None:setattr(owner,'abort',None)
        engine.close();ai.close()


def validate_selection(config):
    from core.components import resolve
    if config.speech_model_id=='external' and config.processing_mode=='gpu' and config.backend!='vulkan':raise ValueError('Choose a GPU-compatible speech model, or use CPU processing.')
    if config.speech_model_id=='speech-cpu' and not resolve('speech-cpu'):raise ValueError('Install the selected CPU speech model in Manage models first.')
    if config.speech_model_id=='speech-turbo' and (not resolve('speech-runtime') or not resolve('speech-turbo')):raise ValueError('Install the selected speech model and runtime in Manage models first.')
    if config.speech_model_id in ('speech-large','speech-qwen'):
        from core.speech_models import configure
        configure(config,config.speech_model_id)
    if config.learning_model_id=='qwen':
        runtime=resolve('ai-cpu') if config.processing_mode=='cpu' else resolve('ai-vulkan') or (resolve('ai-cpu') if config.processing_mode=='auto' else None)
        if not resolve('qwen') or not runtime:raise ValueError('Install the selected local AI model and matching runtime first.')
    return config


def assess_realtime(result):
    return result['speech_ms']+result.get('translation_ms',0)<result['audio_seconds']*1000


def learning_components(processing):
    return ['qwen','ai-cpu'] if processing=='cpu' else ['qwen','ai-vulkan','ai-cpu'] if processing=='auto' else ['qwen','ai-vulkan']
