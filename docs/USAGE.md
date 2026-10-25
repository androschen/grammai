# Using GrammAI

## Conversation and local models

Chinese, Thai, English, and Indonesian are supported, with automatic language options. Chinese pinyin and Thai romanization use local pronunciation helpers.

Open **Settings > Models** to choose speech and translation settings. The selected GPU speech-model file determines the model being used; choosing a quality preset does not download or replace that file. Technical paths and thread controls are under Advanced. Live monitoring shows the active backend, timing, queues, CPU, and memory.

Translation modes:

- **Fast:** NLLB on CPU/int8.
- **Context-aware:** the configured local Qwen model uses bounded original-language dialogue; NLLB is the fallback if local translation fails.
- **Fast + review:** show the fast translation, then automatically review completed sentences with local Qwen. An AI marker identifies refinement; sentence details retain the first translation.

AMD GPUs on Windows can use the configured Vulkan runtimes. Learning explanations, live Qwen translation, and automatic review share a serialized local runtime. When context-aware translation owns that runtime, pause it before requesting a manual learning explanation. No additional model is downloaded for learning cards.

Model output can be mistaken. Source-coverage validation checks that breakdown entries match the original speech; it does not prove the meanings are correct. Selected translated text is never treated as evidence of what was spoken.

## Learning deck

Select an expression in Conversation or Sentence details, right-click, and choose **Create learning card (local AI)**. Check the suggested meaning, add your notes, and save. The Save to deck workflow remains a popup. It closes automatically after a successful card/audio save; errors keep your notes and edits. Deck rows and card details show the original saved time in your local time zone. Editing notes or saving the same card again keeps its creation time.

Use the sidebar bookmark to browse cards in the main window. Search expressions, meanings, or notes and filter by language. Select a card to read its conversation example and explanation. The pencil opens expression/meaning editing; notes can be saved directly. Text corrections reset the practice schedule and invalidate the old explanation; note-only changes preserve both.

For cards without a breakdown, choose **Explain sentence**. The sparkle action refreshes existing breakdowns. Local Qwen generates a bounded original-speech explanation with up to 24 word/phrase entries, with one correction attempt if source coverage is incomplete. Longer inputs use a clearly identified excerpt. Generation respects the existing deeper-reasoning preference when the context limit allows it.

Saved explanations are reused. Follow-up **Ask** replies are temporary; copy useful details into notes before quitting. Search, selected cards, unsaved drafts, and Practice progress remain in memory when switching sidebar pages. Save notes explicitly to keep them after quitting.

![Save to deck remains a separate popup](docs/images/grammai-save.png)

### Practice

Choose **Understand meaning** or **Recall expression**, then practise up to 10 due, reviewed cards. Answers, pronunciation, explanations, and notes stay hidden until Reveal. Reading an already saved answer requires no model call.

- Again schedules a retry after 10 minutes.
- Remembered starts at one day and doubles the interval up to 365 days.
- Skip leaves the schedule unchanged.

This is a lightweight recall scheduler, not a full Anki implementation. Card text is limited to **1,000 cards / 2 MB** in total. You can also keep original sentence audio: leave **Include original audio** on in Save to deck while the clip is available. Play it from the card or Practice using the same Play/Stop control and 1× / 0.8× speed. Recall-expression Practice unlocks audio after Reveal; this preserves the exercise. Older cards without recordings remain text-only.

## Where data is saved

The installed Windows app uses `%LOCALAPPDATA%\GrammAI`:

- `phrases.json`: saved cards, examples, notes, explanations, and review schedules.
- `audio/`: optional compressed Opus recordings shared by cards from the same sentence.
- `preferences.json`: app preferences and model selections.
- `benchmarks.json`: benchmark summaries.

Cards and recordings explicitly included with them persist across PC restarts. Back up both `phrases.json` and the `audio/` folder to preserve recordings. Session history, unsaved edits, Practice-session progress, follow-up replies, and unsaved session replay audio are temporary. The live history is bounded to 80 entries; replay audio has its own bounded RAM buffer. Quitting clears temporary data.

**Settings → Storage** shows saved-audio usage and a 100 / 250 / 500 MB budget (250 MB by default). Clean unused recordings removes files with no card reference. Removing a recording from a card keeps its text, notes and schedule; other cards sharing it keep their audio. A full audio budget offers text-only saving instead of deleting referenced recordings. Expired session clips cannot be recovered.

The `GRAMMAI_DATA_DIR` environment variable can override the data directory for development or tests. Close the app before manually restoring a saved-card backup. Local preferences, cards, recovery backups, downloaded models, recordings, and packaging outputs are excluded from Git.

Closing the main window hides it to the tray when available. Use **Quit GrammAI** in the tray to exit.

## Sentence tools and diagnostics

Sentence details retain original speech, pronunciation, translation history, replay, and source-first Meaning & context. Text supports mouse selection, right-click Copy, Ctrl+C, and Ctrl+A. The floating overlay remains click-through.

Manual audio recheck uses retained audio when available and reports text-only retranslation when it has expired. Original wording is retained with revisions. Automatic AI refinement changes translations; it does not verify or reconstruct the original audio.

**Settings > Translation > Advanced** includes the NLLB/Qwen comparison tool. It compares the same original sentence locally without conversation context. Stop live inference before timing comparisons.

```powershell
python -m scripts.compare_translators --samples 8
python -m unittest discover -s tests -v
```

Synthetic diagnostics are examples, not an accuracy percentage. Settings > Storage reports local storage use; model scans do not delete shared caches. See [Windows setup](WINDOWS.md) for model/runtime setup and packaging details.

### Speaking reply suggestions

In Sentence details, click the speech-bubble icon **How could I reply?** to request two short responses. Replies use the original transcript and nearby original dialogue, with Pinyin for Chinese, Thai romanization and meanings in the explanation language chosen in Settings. Choose a response that fits your situation and practice saying it aloud. Nothing is sent and no answer is scored.

This reuses the existing local Qwen model. Requests run only when clicked, serialize with other local model work and cache in the session. If context translation owns the model, pause translation with the existing Play/Pause control before requesting replies. If the original transcript is unclear, check it before relying on suggestions.

The bookmark on each reply opens Save to deck. Check its meaning, add notes and save; the popup closes after success. Saved replies are clearly AI-generated, retain the heard question as context, and have no original audio attached. The question's recording is not a recording of the reply.

### Listen to pronunciation

Reply suggestions, learning cards and Practice offer **Listen / Stop** with normal or slower speech. This uses installed Windows speech voices, runs only when clicked, and requires no Qwen inference, additional GPU model or saved speech files. Recall practice unlocks Listen after Reveal.

GrammAI selects a voice matching English, Mandarin Chinese, Thai or Indonesian. An unavailable language shows **voice not installed**; it never falls back to an unrelated language. Add the matching voice under Windows Settings → Time & language → Speech → Manage voices, then use the refresh icon next to Listen. Only voices accessible through the Windows desktop speech engine can be selected; Narrator-only voices may not appear.

Listen generates pronunciation of the displayed expression. **Original sentence** controls replay the separate saved conversation recording. Starting either stops the other, and capture is suppressed during playback to avoid feedback. Synthesized pronunciation is not a recording of the original speaker.
