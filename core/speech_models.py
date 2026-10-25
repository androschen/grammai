"""Curated speech choices; file discovery never loads or downloads a model."""
from dataclasses import replace
from pathlib import Path

TITLES={'speech-turbo':'Whisper large-v3-turbo','speech-large':'Whisper large-v3','speech-qwen':'Qwen3-ASR-1.7B','speech-cpu':'Whisper base · CPU'}

def components(identifier):
    if identifier=='speech-cpu':return ('speech-cpu',)
    if identifier=='speech-qwen':return ('speech-qwen','qwen-asr-runtime')
    if identifier in ('speech-turbo','speech-large'):return (identifier,'speech-runtime')
    return ()

def paths(identifier,config=None):
    from core.components import resolve,catalog
    found={key:resolve(key) for key in components(identifier)}
    from core.components import ComponentManager
    if identifier=='speech-cpu' and ComponentManager().availability(identifier)!='installed':found[identifier]=None
    if config:
        for key in components(identifier):
            if found[key]:continue
            value=config.vulkan_executable if key=='speech-runtime' else config.vulkan_model if key in ('speech-turbo','speech-large') else ''
            file=Path(value) if value else None
            if file and file.is_file() and file.name==catalog()[key].entry:found[key]=file
    return found

def installed(identifier,config=None):
    found=paths(identifier,config)
    return bool(found) and all(found.values())

def selected_id(config):
    if config.speech_model_id!='external':return config.speech_model_id
    if config.backend=='vulkan':
        from core.components import catalog
        for key in ('speech-turbo','speech-large'):
            if Path(config.vulkan_model).name==catalog()[key].entry:return key
    return 'external'

def speech_key(config):
    return (config.speech_model_id,config.backend,config.vulkan_executable,config.vulkan_model,config.processing_mode,config.gpu_device,config.cpu_threads,config.beam_size,config.model_size)

def configure(config,identifier):
    c=replace(config,speech_model_id=identifier)
    if identifier=='external':return c
    found=paths(identifier,config)
    if not found or not all(found.values()):raise ValueError('Download the selected speech model and runtime first.')
    if identifier in ('speech-turbo','speech-large'):
        c.vulkan_executable=str(found['speech-runtime']);c.vulkan_model=str(found[identifier]);c.backend='vulkan'
    elif identifier=='speech-qwen':c.backend='qwen-asr'
    else:c.backend='cpu'
    return c
