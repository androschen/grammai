"""Immutable first-version snapshots; revisions remain session-only."""
from dataclasses import replace


def revised_update(original, **changes):
    if any(key in changes for key in ('native_text','target_text')):
        changes.setdefault('suggested_translation','')
        if not changes.get('ai_refined',False):
            changes.setdefault('refinement_model','');changes.setdefault('refinement_backend','')
            if changes.get('target_text',original.target_text)!=original.target_text:
                changes.setdefault('translation_model','');changes.setdefault('translation_backend','');changes.setdefault('translation_fallback','')
    candidate = replace(original, **changes)
    changed = (candidate.native_text, candidate.target_text) != (original.native_text, original.target_text)
    if not changed:
        return candidate
    return replace(candidate,
        original_native_text=(original.native_text if original.original_native_text is None else original.original_native_text),
        original_target_text=(original.target_text if original.original_target_text is None else original.original_target_text),
        revision_count=original.revision_count + 1,
        ai_refined=changes.get('ai_refined',False),
        review_status=changes.get('review_status','not_requested'),
        review_reason=changes.get('review_reason','Wording changed; automatic review has not run on this version.'))


def revision_label(update):
    if not update.revision_count:
        return ''
    transcript = update.original_native_text != update.native_text
    translation = update.original_target_text != update.target_text
    if transcript and translation:
        return 'Transcript corrected; translation revised'
    if transcript:
        return 'Transcript corrected'
    if translation:
        return 'Translation revised'
    return 'Revised; returned to original wording'
