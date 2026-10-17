"""Small, explicit learning preferences; no training or implicit phrase collection."""
import json


def examples(config):
    try:
        values = json.loads(config.analysis_examples)
    except (ValueError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    return [{key:value[key] for key in ('original','preferred','source','target')}
            for value in values[-10:] if isinstance(value,dict)
            and all(isinstance(value.get(key),str) and len(value[key])<=800
                    for key in ('original','preferred','source','target'))
            and value['source'] in ('en','zh','th','id') and value['target'] in ('en','zh','th','id')]


def learning_preferences(config):
    return {'speech_style':config.analysis_speech_style,
            'translation_style':config.analysis_translation_style,
            'explanation_language':config.analysis_explanation_language,
            'explain_slang':config.analysis_explain_slang,
            'glossary':config.analysis_glossary[:4000], 'examples':examples(config)}


def save_example(config, original, preferred, source, target):
    if not original.strip() or not preferred.strip() or max(len(original),len(preferred))>800:
        raise ValueError('Learning examples must contain 1-800 characters per sentence.')
    values = examples(config)
    value = {'original':original.strip(),'preferred':preferred.strip(),'source':source,'target':target}
    if value not in values:
        values.append(value)
    config.analysis_examples = json.dumps(values[-10:],ensure_ascii=False)
