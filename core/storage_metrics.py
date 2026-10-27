"""Read-only, bounded model-size discovery, including managed components and shared caches."""
from pathlib import Path
import os
from core.components import ComponentManager,catalog
from core.paths import model_root,model_candidates


def scan_model_storage(config,max_files=50000):
    root=model_root();roots=[root/'managed',Path.home()/'.grammai/models',*model_candidates('local-ai'),*model_candidates('speech')]
    caches=[Path.home()/'.cache/huggingface/hub']
    for name in ('HF_HUB_CACHE','HUGGINGFACE_HUB_CACHE'):
        if os.environ.get(name):caches.append(Path(os.environ[name]))
    if os.environ.get('HF_HOME'):caches.append(Path(os.environ['HF_HOME'])/'hub')
    for cache in caches:
        if cache.is_dir():roots.extend(cache.glob('models--Systran--faster-whisper-*'))
    partial=False;extra=[]
    manager=ComponentManager()
    try:
        for key,record in manager.records().items():
            if key not in catalog():continue
            file=manager.path(key)
            if not file:continue
            spec=catalog()[key]
            if spec.kind=='ct2':extra.extend(file.parent/a.name for a in spec.assets)
            elif record.get('managed'):
                base=(root/'managed'/key/record['version']).resolve()
                if base.is_relative_to((root/'managed').resolve()):roots.append(base)
            else:extra.append(file)
    except (ValueError,OSError):partial=True
    extra.extend(Path(value) for value in (config.vulkan_model,config.analysis_gguf,config.vulkan_executable,config.analysis_executable) if value)
    unique=[]
    for candidate in sorted(set(p.resolve() for p in roots),key=lambda p:len(p.parts)):
        if not any(candidate.is_relative_to(parent) for parent in unique):unique.append(candidate)
    seen=set();visited=0;models=downloads=0
    def size(file):
        nonlocal visited,partial
        visited+=1
        if visited>max_files:partial=True;return 0
        try:
            if not file.is_file():return 0
            stat=file.stat();key=(stat.st_dev,stat.st_ino) if stat.st_ino else str(file.resolve())
            if key in seen:return 0
            seen.add(key);return stat.st_size
        except OSError:partial=True;return 0
    for directory in unique:
        if not directory.is_dir():continue
        try:
            for file in directory.rglob('*'):
                models+=size(file)
                if visited>max_files:break
        except OSError:partial=True
        if visited>max_files:break
    if visited<=max_files:
        for file in extra:
            models+=size(file)
            if visited>max_files:break
    cache=root/'downloads'
    if visited<=max_files and cache.is_dir():
        try:
            for file in cache.rglob('*'):
                downloads+=size(file)
                if visited>max_files:break
        except OSError:partial=True
    return dict(bytes=models,download_bytes=downloads,partial=partial)
