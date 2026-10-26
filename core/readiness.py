"""Offline readiness checks; flags and GPU names never substitute for usable files."""
from pathlib import Path


def missing_models(config):
    from core.components import ComponentManager
    from core.speech_models import installed
    manager=ComponentManager();missing=[]
    if config.speech_model_id!='external':
        speech_ready=installed(config.speech_model_id,config)
    elif config.backend=='vulkan':
        from core.speech_assets import installed_paths
        exe,model=installed_paths()
        speech_ready=Path(config.vulkan_executable or exe).is_file() and Path(config.vulkan_model or model).is_file()
    else:
        speech_ready=manager.availability('speech-cpu')=='installed' if config.model_size=='base' else False
        if not speech_ready:
            try:
                from huggingface_hub import try_to_load_from_cache
                cached=try_to_load_from_cache('Systran/faster-whisper-'+config.model_size,'model.bin')
                if isinstance(cached,str):
                    folder=Path(cached).parent
                    speech_ready=all((folder/name).is_file() for name in ('model.bin','config.json','tokenizer.json')) and any((folder/name).is_file() for name in ('vocabulary.txt','vocabulary.json'))
            except (ImportError,OSError,ValueError):pass
    if not speech_ready:missing.append('Speech recognition model and runtime')
    if config.translation_enabled and config.translation_mode in ('fast','review') and manager.availability('translation-fast')!='installed':missing.append('Live translation / NLLB')
    from core.model_info import refinement_enabled
    if (config.analysis_enabled and config.analysis_provider=='local') or (config.translation_enabled and (config.translation_mode=='context' or refinement_enabled(config))):
        from ml.local_analysis import LocalAnalysisRuntime
        exe,model=LocalAnalysisRuntime().paths(config)
        if not exe.is_file() or not model.is_file():missing.append('Learning / refinement model and runtime')
    return missing


def setup_required(config):
    return not config.setup_completed or bool(missing_models(config))
