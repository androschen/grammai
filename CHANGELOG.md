# Changelog

## 0.7.1 — 2026-10-18

### Sentence learning experience
- Separate original speech, pronunciation, translation, and highlighted first/current history into compact sections.
- Fix vertical stretching: growing the panel adds space below the content instead of between its lines.
- Keep Meaning & context on its own page; explanations run only on explicit request.
- Open Save to deck as a separate reviewed popup. Edited deck meanings do not overwrite session translations; live updates invalidate stale save reviews.

### Conversation and controls
- Compact navigation, a direct audio-device dropdown, a noise-threshold sliders control, inverted CC visibility states, and one dynamic sun/moon theme action.
- Keep conversation text aligned with and without refinement markers; preserve text copying and selection during background updates.

### Local inference and learning
- Fast NLLB, context-aware local Qwen, and fast-plus-local-review translation modes share bounded runtime ownership.
- Automatic review preserves original speech and the first translation, updates the session meaning, and marks AI refinement without claiming verified correctness.
- Local selected-phrase explanations, reviewed text-only cards, and lightweight practice; no new model is required.
- Use original transcripts and bounded original context for analysis; serialize local model tasks and reuse session caches.

### Verification
- 148 automated tests pass, including section geometry at multiple panel heights, stale-save handling, model ownership, copying, and review preservation.
- Native Windows previews and packaged/installed offline smoke checks pass.
- Existing local model presence is checked. GPU inference was not rebenchmarked for this UI release.

This release consolidates the unpublished 0.3.x–0.7.0 development updates since the previous GitHub snapshot. Model weights and personal runtime data are not included.
