"""Lightweight model identity and per-result provenance; never starts inference."""
from pathlib import Path


def refinement_enabled(config):
    return config.translation_mode!='context' and (config.refinement_enabled or config.translation_mode == 'review')


def local_ai_name(config, runtime=None):
    try:
        if runtime is None:
            from ml.local_analysis import LocalAnalysisRuntime
            runtime = LocalAnalysisRuntime()
        path = runtime.paths(config)[1]
        return 'Qwen3-4B' if 'qwen3-4b' in path.name.lower() else path.stem or 'Custom local model'
    except (OSError, ValueError):
        return 'Local AI (identity unavailable)'


def sentence_info(update):
    speech = update.speech_model or 'Not recorded'
    if update.speech_backend: speech += ' / ' + update.speech_backend
    if update.translation_status == 'same_language':
        translation = 'Not needed (same language)'
    elif update.translation_status == 'transcribed':
        translation = 'Off (transcript only)'
    else:
        translation = update.translation_model or 'Not recorded'
        if update.translation_backend: translation += ' / ' + update.translation_backend
        if update.translation_status == 'unavailable': translation += ' / Unavailable'
    states = {'not_requested':'Off / not requested','awaiting':'Queued','reviewing':'In progress',
        'refined':'Completed / wording changed','unchanged':'Completed / wording kept',
        'skipped':'Skipped','failed':'Failed / initial translation retained'}
    state = 'refined' if update.ai_refined and update.review_status == 'not_requested' else update.review_status
    refinement = states.get(state, 'Not recorded')
    if update.refinement_model:
        refinement = update.refinement_model + (' / ' + update.refinement_backend if update.refinement_backend else '') + ' / ' + refinement
    lines = ['Speech: ' + speech, 'Translation: ' + translation, 'AI refinement: ' + refinement]
    if update.translation_fallback: lines.append('Fallback: ' + update.translation_fallback)
    if update.review_reason and state in ('skipped','failed'): lines.append(update.review_reason)
    return '\n'.join(lines)
