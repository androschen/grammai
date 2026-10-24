# Changelog

Versions 0.7.2–0.9.7 below describe local desktop builds first published together in v0.9.8.

## 0.9.8 — 2026-10-24

- Open Learning deck as a persistent main-window page from the sidebar, with Cards and Practice in the same application shell.
- Show card details beside the list on wide layouts and use an inline Back action on compact layouts.
- Preserve searches, per-card note/edit drafts, and Practice progress across navigation. Read newly saved cards when returning without rebuilding the page.
- Keep play/pause, subtitles, theme, and current audio-device status available while learning. Navigation does not toggle transcription.
- Reuse card/deck content widgets; retain standalone diagnostic hosts and the existing Save to deck popup.

## 0.9.7 — Local desktop build

- Match learning cards and Save to deck to the approved reading layout, with sentence examples, aligned word rows, quiet section separators, and editable notes.
- Move expression/meaning corrections behind a pencil action. Saving notes preserves review schedules and saved explanations without reconfirming meaning.
- Stop merging every selection into one word row. Keep model-supplied word boundaries, and add an explicit local refresh for older breakdowns that bypasses the session cache.
- Keep preparation regeneration attached to the actual card draft so the saved explanation matches what is shown.

## 0.9.6 — Local desktop build

- Save original-speech sentence meaning, word/phrase explanations, and contextual reasoning with learning cards. Notes and existing cards remain compatible.
- Show saved explanations only after Practice Reveal; opening and revealing saved explanations require no model calls.
- Add on-demand explanation generation for existing cards and local follow-up questions. Serialize model work, allow cancellation, and retain text-only storage quotas.
- Use deterministic Chinese/Thai pronunciation and group selected expressions. Explain bounded source excerpts explicitly; local AI drafts still require checking.

## 0.9.5 — Local desktop build

- Reserve fixed subtitle width and row heights without shrinking fonts. Long text pages within the overlay; full text remains in history.
- Use one optional pronunciation row, preserve bottom anchoring, and stop paging while hidden. New speech replaces pending pages.


## 0.9.4 — Local desktop build

- Clarify due-card practice with expression focus, recall instructions, and hidden pronunciation until reveal.
- Add Skip without changing review schedules and a compact session summary. Practice stays local with no AI inference.


## 0.9.3 — Local desktop build

- Consolidate speech and translation choices on Models, with selected model summaries and separate live runtime status.
- Hide thread counts and speech/Qwen paths under Advanced; keep explanation preferences under Understanding.
- Correct GPU preset descriptions and automatic refinement guidance.


## 0.9.2 — Local desktop build

- Detect missing capture chunks by sequence number and reset partial speech/overlap before decoding subsequent audio.
- Clear live translator context after replay pauses or audio discontinuities without reloading models.
- Add a read-only accuracy configuration audit with physical Windows profile-path verification.

- Recover a missing saved deck from the Codex MSIX redirected AppData cache on normal Windows startup; preserve source files and existing user cards. Deliberately cleared decks stay cleared.
- Add an explicit recovery helper that can be launched through the native Windows desktop to avoid inheriting the launcher’s redirected filesystem view.

## 0.9.1 — Local desktop build

- Read saved cards directly from the verified deck path on each deck refresh.
- Treat read/format failures as visible errors, never as an empty deck; block saves from replacing unreadable data.
- Retry failed reads without caching an empty result, accept Windows UTF-8 BOM files, and expose the storage path in the deck.
- Verify persisted and displayed card counts in packaged diagnostics.

## 0.9.0 — Local desktop build

- Create reviewed vocabulary cards from selected expressions using the shared local Qwen model, with concise contextual meanings and usage notes.
- Retain the actual conversation example, translation and nearby original dialogue separately from AI explanations and personal notes.
- Browse compact expression rows with pronunciation, meaning, example and notes; open a separate card editor for full context.
- Practise understanding or recalling an expression in its sentence; preserve existing sentence cards and scheduling.
- Reuse bounded session drafts, prevent overlapping model work, and keep browsing/practice inference-free. Existing 1,000-card / 2 MB text quotas remain.

## 0.8.0 — Local desktop build

- Consolidate the reviewed UX: one auto-scroll control and one Play/Stop replay button, with playback completion resetting the action.
- Hide empty same-language translations and retain review reasons beside the route.
- Show selected speech and available original dialogue directly in Meaning & context.
- Show cancellation only while explaining; omit repeated introductions and empty result sections.
- Move occasional transcript tools to More; preserve the separate reviewed Save to deck popup.

## 0.7.2 — Local desktop build

- Track per-sentence review lifecycle, including unchanged, skipped, and failed outcomes; show the state next to the translation in details.
- Preserve selection and save confirmation during metadata-only updates.
- Pause auto-scroll only for deliberate movement away from the bottom; add Resume live.
- Keep follow enabled during new subtitles, revisions, resize and automatic scrollbar actions.

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
