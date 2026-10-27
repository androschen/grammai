# GrammAI for Windows

## Install and launch

Run `dist/GrammAI-Setup-0.13.0.exe`. This per-user installer creates a Start menu
entry, an optional desktop shortcut, and an uninstaller. No administrator rights,
Python installation, terminal, or repository checkout are needed to run the app.
This release is unsigned; Windows can identify the publisher as unknown.

Alternatively, extract `dist/GrammAI-Portable-0.13.0.zip`, keep the entire
extracted `GrammAI` directory together, and launch `GrammAI.exe`. Its `_internal` directory contains the bundled runtime and DLLs.
Copying only the exe will not work.

Launching again activates the existing instance. Closing the main window hides
it to the tray when available; choose Quit GrammAI to stop capture and workers.

## Sentence details

**Settings > Translation > Advanced** includes a comparison of NLLB and local Qwen.
It compares source text locally using already installed models. Live translation uses the selected Fast, Context-aware, or Fast + review mode. Stop live subtitles before running the comparison. Manual
ratings and custom text remain in RAM only and are cleared when the window closes.

Details opens a resizable panel beside history. Select another sentence to switch
without dismissing a dialog. On narrow screens, use the inline Back action to return to conversation history.

Original speech and its pronunciation appear above the translation card. One Play/Stop control replays the audio; speed and recheck tools are nearby. Edit transcript reveals the
editor and language choices. Compare original highlights changed wording.
Recheck suggestions still require Apply revision; revisions never claim verified
accuracy. Meaning & context presents analysis as readable sections.

## Models, preferences and updates

Model weights are deliberately excluded from the installer. Existing preferences
and explicitly configured external model paths are reused. For this development
machine, the build's `--register-models` option records the existing model folder
in `%LOCALAPPDATA%\GrammAI\model-locations.json`; this personal path is never
included in the distributed app. Existing models stay in their current location,
so keep that folder or configure replacement paths before deleting it.

New managed GPU/context assets go under `%LOCALAPPDATA%\GrammAI\models` in the
packaged app. Shared Whisper/Hugging Face and existing NLLB caches are reused.
First model setup requires an internet connection; cached inference stays local.
Updating or uninstalling the app preserves preferences, model files and existing
saved phrases. The installer replaces application files only. Session history
and audio buffers stay temporary.

Diagnostics are bounded under `%LOCALAPPDATA%\GrammAI\logs`; `startup.log`
captures early loading errors and `grammai.log` records unexpected exceptions.

## Build

Build on Windows with Python 3.14 and the application's requirements installed.
Install `requirements-build.txt`, then install Inno Setup 6 and put ISCC.exe on
PATH (or use its normal installation location). Build tools may also live under
the ignored `.build-tools/python` and `.build-tools/inno` folders.

```powershell
python -m scripts.build_windows --installer
```

Use `--register-models` only on your own development machine when switching to
the packaged app. Each build uses a fresh staging folder to avoid Windows/OneDrive locks on old
test bundles. The staging path is recorded in ignored `build/latest-bundle.txt`.
The build performs library discovery offline, bundles the
required runtime libraries, generates the Windows icon, and excludes model and
personal-data directories. No online service, API credentials or recordings are
included. Version fields are in `core/version.py`, `packaging/version.txt`, and
`packaging/installer.iss`; update them together for a release.

The executable supports an offline, no-capture packaging check:

```powershell
<extracted-folder>\GrammAI\GrammAI.exe --smoke-test --smoke-report=C:\Temp\grammai-check.json
```

Add `--verify-models` to additionally load existing Vulkan speech/context models
and translate a synthetic greeting with the existing NLLB cache. It performs no
model downloads and exits after closing the owned servers. It requires those
models to have been set up first. This is not a substitute for testing WASAPI
capture, click-through overlay behavior and hardware drivers on a clean PC.

## Release versioning

The current release is **0.13.0**, tagged **v0.13.0** in Git. Version values are synchronized in `core/version.py`, `packaging/version.txt`, and `packaging/installer.iss`. Build the installer and portable archive with `python -m scripts.build_windows --installer`. These generated binaries and model weights are not committed to the repository. See `CHANGELOG.md` for release notes.

## Modular setup (local builds from 0.14.0)

New installations open **Your PC → Components → Ready**. Review model sizes and location, then choose **Install & test**. Setup verifies downloads and measures compatibility/speed before Start. Essential setup supports transcription without translation or the learning model.

Existing installations keep their configured files and skip onboarding. Open **Settings → Models → Setup assistant** to reconfigure, or **Manage components → Find installed models** to register recognized files in place. Import custom runtimes/models through Advanced. External originals are never removed by component cleanup.

Speech recognition, fast CPU translation and shared learning AI are separate components. Qwen weights are shared by contextual translation, explanations and reply suggestions. CPU and Vulkan runtimes are independent downloads. CUDA-specific packages are not included in this release.

Automatic mode may use an already installed CPU backup when GPU speech fails; smaller-model fallback can change accuracy. GPU preferred requires verified GPU allocation. Test setup reports speed on a bundled synthetic English sample, not a multilingual accuracy score. Pause translation and unload AI before component tests or file changes.

Component downloads can resume and require pinned checksums before activation. Repair restores the previous managed version on failure. Change location copies and verifies managed files before committing the new location; cards, recordings and external model files stay where they were. Review each model license before use; NLLB weights use CC-BY-NC-4.0.

## Speech model selection (local builds from 0.15.0)

Open **Settings → Models → Speech recognition**. A download icon marks missing components; a check marks installed files. The running label reflects live telemetry. Select a model, download if needed, then **Save changes**. Downloading does not switch models. Save pauses recognition while loading and testing the candidate; a failed test keeps the previous selection.

Turbo Q5 is about 574 MB, full large-v3 Q5 about 1.08 GB, and Qwen3-ASR-1.7B Q8 about 2.51 GB. Missing speech runtimes are additional downloads. These file sizes are not RAM/VRAM requirements. Qwen speech uses the separately pinned CrispASR community runtime and is experimental; the first Vulkan inference may spend extra time compiling shaders. CPU mode uses the same selected Qwen weights and can be substantially slower. The text Qwen3-4B model is separate.

### Clear model roles (0.15.1)

Settings > Models separates Live translation from AI refinement. Live translation chooses NLLB on CPU or the shared local Qwen model. Optional refinement reviews original speech and nearby dialogue; choose history only or history plus the currently displayed subtitle. When Qwen already translates live with context, an additional review pass is disabled to avoid competing for the same runtime.

Hover, focus, or click the info icon beside Sentence to see the models actually used, CPU/GPU backend, refinement result, and any fallback. Existing sentences retain their own metadata when settings change. Missing legacy metadata is reported as not recorded rather than inferred from current settings. Installed Whisper base cache files are reused in place; no duplicate download is required.

### New PC setup (0.15.4)

GrammAI opens setup for an empty profile and when required model files are missing, including copied preferences from another PC. Choose Recommended or Essential, review components, then Install & test. Start is enabled only after the compatibility check succeeds. Models, runtimes, and learning AI can also be downloaded from Settings > Models without editing file paths.

For NVIDIA, AMD, or Intel hardware, a display adapter name is only a recommendation; the Vulkan runtime must confirm GPU model allocation. CPU only intentionally keeps speech on CPU. Use GPU switches the draft to GPU preferred; Save changes tests acceleration before applying it. Automatic can use an installed CPU backup and displays the reason. NLLB live translation still runs on CPU independently of GPU speech recognition.

### Manage models (0.16.0)

Settings > Models groups choices into Transcription, Translation and Learning assistant. Downloading installs missing runtimes together with the model; shared Qwen weights are stored once. Save changes applies model selections after the existing compatibility checks.

Open Manage models for categorized disk usage, verification and deletion. Not downloaded means no matching files were detected, Incomplete means required files or sizes do not match, and Files detected is not a compatibility or GPU claim. Verify runs a checksum check in the background. Actual processing is shown by running telemetry in Models settings.

Selected models cannot be deleted until their features are switched or disabled and saved. Supporting runtimes stay protected while installed models depend on them. Disconnect removes an external file from GrammAI's catalog without deleting the original. Supporting runtimes and Advanced expose repair, import and location tools. Cards, recordings and preferences are separate from model storage.

### Friendly first-run setup (0.17.0)

The Windows installer installs the app first. Its welcome page includes install location and desktop-shortcut controls; Install & open launches GrammAI after installation. Silent updates retain the existing no-auto-launch behavior.

On first launch, choose Transcription, optional Subtitle translation and optional Learning assistant. Recommended uses hardware detection as a suggestion; Small download keeps compact CPU speech and lets you add learning later. Advanced setup contains processing, speech model, backup and location controls. Download & test starts only the selected features and required shared runtimes; it checks existing files first.

Download progress is grouped by feature. Retry resumes partial downloads where the server supports it; Cancel retains saved bytes. Set up learning later stops the current operation safely, keeps the partial Qwen download, and downloads/tests the remaining choices. GPU test failures can be retried explicitly on CPU. Start GrammAI enables only after successful testing; the Ready page reports the backend actually tested. Device names and completed downloads alone do not confirm GPU compatibility or conversation accuracy.

### Storage and learning backups (0.18.0)

Settings > Storage separates saved recordings, learning cards and model files. The quota gauge distinguishes recordings referenced by cards from unused files. Quota edits take effect with Save changes; at capacity, existing recordings stay and new cards can be saved without audio.

Clean up opens a preview. Confirmation re-reads current card references and removes only unchanged, reviewed unused clips. Cards and linked audio stay. RAM-only replay, benchmark summaries and explicit card deletion are under Advanced. Deleting cards here retains the recordings for a separate cleanup review.

Back up creates a local ZIP containing phrases.json, a versioned manifest with checksums, and each linked available recording once. Models, preferences and unused recordings are excluded. Missing recordings are reported. To restore manually with GrammAI closed, preserve your existing data first, then copy phrases.json and audio/ from the archive into the app data folder; this replaces the deck rather than merging it. There is no automatic restore operation in this version.

Model-size scans include managed components, recognized legacy/cache locations and configured external files. Shared/hardlinked files are counted once; downloaded/partial files retained for resume are listed separately. Size scans are bounded and partial results are marked. Manage models opens the existing per-model management page.
