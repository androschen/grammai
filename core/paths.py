"""Writable model locations independent of the installed executable."""
import os
import sys
from pathlib import Path


def model_root():
    override=os.environ.get('GRAMMAI_MODELS_DIR')
    if override:
        return Path(override)
    if not getattr(sys,'frozen',False):
        return Path(__file__).resolve().parents[1]/'models'
    from core.preferences import data_dir
    return data_dir()/'models'


def register_existing_models():
    """Record a developer's existing cache locally; never ship personal paths."""
    from core.preferences import write_json
    root=model_root()
    if not getattr(sys,'frozen',False) and root.is_dir():
        write_json('model-locations.json',{'root':str(root.resolve())})


def existing_model_root():
    from core.preferences import read_json
    value=read_json('model-locations.json',{})
    root=Path(value.get('root','')) if isinstance(value,dict) and value.get('root') else None
    return root if root is not None and root.is_dir() else None


def model_candidates(component):
    roots=[model_root()/component]
    legacy=existing_model_root()
    if legacy is not None and legacy/component not in roots:
        roots.append(legacy/component)
    return roots
