"""Role-based inventory and deletion rules. No inference or downloads during discovery."""
from pathlib import Path
from core.components import catalog

GROUPS=(('Transcription',('speech-cpu','speech-turbo','speech-large','speech-qwen')),
        ('Translation',('translation-fast',)),('Translation & learning',('qwen',)),
        ('Supporting runtimes',('speech-runtime','qwen-asr-runtime','ai-vulkan','ai-cpu')))


def installation_components(identifier,processing):
    from core.speech_models import components
    from core.setup import learning_components
    if identifier=='qwen':return learning_components(processing)
    return components(identifier) or (identifier,)


def usage(identifier,config,manager):
    """Saved selections block deletion; runtime dependencies include inactive installed models."""
    from core.model_info import refinement_enabled
    from core.speech_models import selected_id
    reasons=[]
    selected=selected_id(config)
    if identifier==selected or (identifier=='speech-cpu' and selected=='external' and config.backend=='cpu' and config.model_size=='base'):reasons.append('Transcription')
    path=manager.path(identifier)
    if path and identifier.startswith('speech-') and identifier not in ('speech-runtime',):
        if config.vulkan_model and Path(config.vulkan_model).resolve()==path.resolve() and selected=='external':reasons.append('Transcription')
    if identifier=='translation-fast' and config.translation_enabled and config.translation_mode in ('fast','review'):reasons.append('Live subtitle translation')
    qwen_used=config.learning_model_id=='qwen' or not config.analysis_gguf or bool(path and Path(config.analysis_gguf).resolve()==path.resolve())
    if identifier=='qwen' and qwen_used:
        if config.analysis_enabled and config.analysis_provider=='local':reasons.append('Learning assistant')
        if config.translation_enabled and config.translation_mode=='context':reasons.append('Live subtitle translation')
        if config.translation_enabled and refinement_enabled(config):reasons.append('Translation refinement')
    dependents={'speech-runtime':('speech-turbo','speech-large'),'qwen-asr-runtime':('speech-qwen',),'ai-vulkan':('qwen',),'ai-cpu':('qwen',)}
    for key in dependents.get(identifier,()):
        if manager.path(key):reasons.append('Installed '+catalog()[key].title)
    if path and identifier in ('speech-runtime','ai-vulkan','ai-cpu','qwen-asr-runtime'):
        values=(config.vulkan_executable,) if identifier in ('speech-runtime','qwen-asr-runtime') else (config.analysis_executable,) if config.analysis_enabled or (config.translation_enabled and (config.translation_mode=='context' or refinement_enabled(config))) else ()
        if any(value and Path(value).resolve()==path.resolve() for value in values):reasons.append('Selected runtime')
    return list(dict.fromkeys(reasons))


def storage_bytes(identifier,manager):
    """Count actual files, once per component. Never hash weights on the UI thread."""
    record=manager.records().get(identifier,{})
    path=manager.path(identifier)
    if not path:return 0
    spec=catalog()[identifier]
    if record.get('managed'):
        base=(manager.root/'managed'/identifier/record['version']).resolve()
        if not base.is_relative_to((manager.root/'managed').resolve()):return 0
        files=(base/name for name in record['hashes']) if record.get('hashes') else base.rglob('*')
    elif spec.kind=='ct2':files=(path.parent/a.name for a in spec.assets)
    else:files=(path,)
    total=0
    for file in files:
        try:
            if file.is_file():total+=file.stat().st_size
        except OSError:pass
    return total


def remove_model(identifier,config,manager):
    reasons=usage(identifier,config,manager)
    if reasons:raise ValueError('Still used by: '+', '.join(reasons)+'. Change and save model settings first.')
    if manager.records().get(identifier,{}).get('managed'):manager.remove(identifier)
    else:manager.disconnect(identifier)
