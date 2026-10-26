# Changelog

Versions 0.7.2–0.9.7 below describe local desktop builds first published together in v0.9.8.

## 0.16.1

- Retry interrupted model/runtime transfers up to five attempts, resuming verified-size partial downloads with cancellable backoff.
- Retain bytes from interrupted reads and identify the failed file and download host with actionable retry guidance.
- Share recovery between model management and legacy learning setup while preserving SHA-256 checks, strict resume validation and normal TLS verification.

## 0.16.0

- Organize Models settings by Transcription, live Translation, and Learning assistant, with direct downloads and shared Qwen weights.
- Replace the flat component list with a separate Manage models page: categorized storage totals, per-model verification, deletion/disconnection and advanced runtime tools.
- Distinguish not downloaded, incomplete and detected files; validate sizes and required runtime files without hashing models on the UI thread.
- Protect selected/shared models and runtimes, preserve external originals when disconnecting, and rediscover nested runtime installations.
- Include the first-run setup, learning downloads and CPU/GPU fallback improvements prepared in 0.15.4.

## 0.15.4

- Show first-run setup when configuration is partial or required models/runtimes are missing, even if a copied setup flag says complete. Preserve working existing installations.
- Detect Windows display adapters before model runtimes exist; recommend GPU-capable setup provisionally and verify actual allocation in the compatibility test.
- Add direct Learning assistant downloads for Qwen and the selected CPU/Vulkan runtimes. Automatic mode includes a CPU runtime without duplicating shared weights.
- Show CPU-only selection, GPU fallback reasons, GPU retry, and the backend actually verified during a speech-model switch.
- Resolve legacy model paths dynamically after model-folder changes and add isolated clean-PC onboarding and installation regressions.

## 0.15.3

- Disable Settings Save changes until configuration is edited. Reverting changes, successful saves, and completed model switches clear the unsaved state; failed saves retain edits for retry.
- Track live noise/appearance previews, language and model choices, storage limits, and learning settings without polling or inference work.

## 0.15.2

- Fix invisible task helpers intercepting Settings tab clicks during ordinary navigation. Task footers now own their controls and occupy their intended layout positions.
- Verify navigation with real window-level pointer clicks, including task progress, both themes, and display scaling.

## 0.15.1

- Separate live translation model selection from optional AI refinement; choose history only or history and current subtitles.
- Reuse existing pinned Whisper base caches without another download; distinguish incomplete model files from installed models.
- Show actual per-sentence speech, translation, refinement, and fallback information behind an accessible info icon. Keep translation history visible and refinement markers compact.
- Preserve legacy refinement preferences and Qwen ASR backend selection across restarts.

## 0.15.0 — Switch local speech models

- Add Whisper large-v3 and experimental Qwen3-ASR-1.7B alongside Turbo and the CPU base model. Native dropdown rows show download/check icons, accessible installation labels and a separate running marker.
- Download only after an explicit click, with pinned sizes, checksums, resume and cancellation. Optional speech downloads leave the active recognizer running.
- Save speech changes through a serialized load-and-transcribe check. The old worker releases its model first; failed checks retain the previous selection and resume the prior recognizer.
- Run Qwen speech locally through a separate resident, authenticated loopback CrispASR CPU/Vulkan process. Existing Qwen3-4B text translation and learning remain separate.
- Fix the bundled benchmark fixture's missing Path import. Add regression coverage for dropdown stability, downloads, switching, rollback and GPU confirmation.

## 0.14.1 — Models interaction and layout fix

- Fix an empty sibling widget intercepting mouse input on Settings → Models. Construct overview and component pages with correct widget ownership instead of moving raw layout items.
- Match the approved Models design more closely with compact role cards, visible running/shared-model badges, fewer nested tabs and a visible component list.
- Add window-level pointer regression tests for selectors, component navigation, setup and test actions, plus packaged input hit-testing.

## 0.14.0 — Modular setup and models

- Add a first-launch setup assistant with explicit component selection, download sizes, storage location and real compatibility/speed checks. Existing preferences retain their model paths and skip onboarding.
- Separate pinned CPU speech, GPU speech, fast translation, shared Qwen weights and CPU/Vulkan runtimes. Downloads resume, verify checksums and activate atomically; model downloads never start implicitly during inference.
- Add inline component management, verification, repair rollback and verified managed-model relocation. External files are reused in place and never removed by the manager.
- Remove AMD-only AI selection and fixed thread assumptions; add explicit CPU inference, generic Vulkan device selection and optional installed CPU fallback. CUDA-specific packages remain a later addition.
- Keep selected and running status separate, preserve model selection when changing decoding effort, and block conflicting inference while component tasks run.

## 0.13.1 — Detect installed language voices

- Enumerate Windows speech voices across every supported installed locale instead of only the default language. Chinese, Thai and Indonesian voices no longer remain hidden behind the English locale.
- Select the matching locale before selecting its voice for playback, and reject mismatched or Cantonese-only voices for Mandarin pronunciation.
- Keep the same Listen controls and capture/replay safeguards. No registry edits, voice downloads or additional models are required.

## 0.13.0 — Local pronunciation

- Add compact Listen/Stop and normal/slower Windows pronunciation to reply suggestions, saved card details and Practice. Recall mode unlocks pronunciation only after Reveal.
- Choose an installed voice matching Chinese, Thai, English or Indonesian; show a missing-voice state and recheck control instead of using the wrong language. No automatic voice downloads, model inference or persisted speech files.
- Keep generated pronunciation separate from saved original conversation audio. Coordinate playback, cancellation, page changes and capture suppression so the app does not transcribe its own voice.

## 0.12.0 — Speaking reply suggestions

- Add an on-demand reply icon to Sentence details. Local Qwen suggests two short replies using only the original transcript and nearby original dialogue, with local Pinyin/Thai romanization and meanings in the configured explanation language.
- Reuse the existing serialized model service and bounded session cache. No model runs when opening details or saving. Active context translation must be paused explicitly before its model is used for replies; hiding/closing requests cancels them.
- Validate bounded reply drafts, reject clear language mismatches and show incomplete-context responses instead of guessing. Suggestions remain AI drafts, never sent or graded.
- Save checked generated replies in a separate popup with notes and the heard question as context. Mark their provenance in the deck and later explanations; never attach the question's recording to a generated response.
- Invalidate replies and pending save confirmation when the original transcript changes. Preserve existing cards, audio, preferences and review schedules.

## 0.11.1 — Saved time and smoother card saving

- Show the original save date/time on deck rows and card details, with full local date, seconds and UTC offset in the tooltip. Existing recorded timestamps are reused; missing or invalid timestamps are clearly unavailable.
- Keep creation timestamps unchanged when editing notes or saving the same card again.
- Close vocabulary and sentence Save to deck popups only after the card and selected audio commit successfully. Failures retain the popup, meaning and notes.
- Show a brief Card saved confirmation and refresh visible deck cards without discarding unsaved note drafts, filters or Practice progress.

## 0.11.0 — Saved original audio

- Save original sentence audio with vocabulary and sentence cards, with a default-on opt-in toggle and preview when the session clip is available.
- Replay saved recordings in card details and Practice with one Play/Stop button and 1× / 0.8× speed. Recall mode unlocks audio after Reveal.
- Keep compressed Opus recordings locally across restarts; cards sharing the same recording use one file. Encoding and decoding run in background jobs, and replay reuses capture feedback suppression.
- Add a 100 / 250 / 500 MB budget (250 MB default), storage usage and explicit unused-recording cleanup in Settings → Storage. Removing a card's audio preserves its text, notes and schedule; shared recordings remain until their final reference is removed.
- Support expired clips, missing files and text-only cards without losing card content. Existing cards cannot recover recordings that were never saved.

## 0.10.2 — 2026-10-24

- Apply one compact Save to deck form to selected expressions and full sentences: language badge, expression, pronunciation, editable meaning, conversation example, notes, confirmation and a full-width Save action.
- Keep word explanations and original context available in an expandable section; selecting translated text remains clearly distinguished from original speech.
- Prevent save fields from stretching with popup height, keep short meanings free of unnecessary scrollbars, and preserve original conversation snapshots and notes during revisions and retries.

## 0.10.1 — 2026-10-24

- Center noise-threshold markers on the visible audio track in both the header and Audio settings while retaining the larger drag target.
- Add an explicit gap between the learning card browser and detail pane, with consistent inner padding and aligned reading sections.

## 0.10.0 — 2026-10-24

- Unify all workspaces with one mint-accented light/dark theme, common typography, icons, reading sections, and theme-aware meters and revision highlights.
- Keep Settings and Resources inside the sidebar shell, alongside Conversation and Learning deck. Capture, subtitles and theme controls stay in the shared header.
- Preserve unsaved settings drafts when navigating; save merges intentional edits with newer external changes. Audio and subtitle previews revert when leaving Settings. Discard restores saved settings.
- Show selected conversation rows, retain their highlight after AI refinements, and use a single sentence detail panel with compact-window Back navigation.
- Simplify subtitle appearance controls, put layout details under Advanced, and present real app CPU, RAM, GPU and GPU memory history in a shared resource page.
- Keep learning card notes, due dates, Practice state, inference settings, and saved data compatible with previous versions.

## 0.9.9 — 2026-10-24

- Refresh the embedded learning deck with a focused expression header, soft lavender accents, separated word rows, visible notes, and compact language-colored card previews.
- Add a completed-card progress bar to Practice; retain existing Again/Remembered scheduling and Skip without rescheduling.
- Keep saved data, on-demand AI requests, keyboard copying, and compact single-window navigation intact. No model or storage format changes.

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
