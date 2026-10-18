# GrammAI for Windows

## Install and launch

Run `dist/GrammAI-Setup-0.7.1.exe`. This per-user installer creates a Start menu
entry, an optional desktop shortcut, and an uninstaller. No administrator rights,
Python installation, terminal, or repository checkout are needed to run the app.
The first release is unsigned; Windows can identify the publisher as unknown.

Alternatively, extract `dist/GrammAI-Portable-0.7.1.zip`, keep the entire
extracted `GrammAI` directory together, and launch `GrammAI.exe`. Its `_internal` directory contains the bundled runtime and DLLs.
Copying only the exe will not work.

Launching again activates the existing instance. Closing the main window hides
it to the tray when available; choose Quit GrammAI to stop capture and workers.

## Sentence details

**Settings > Translation > Advanced** includes a comparison of NLLB and local Qwen.
It compares source text locally using already installed models. Live translation uses the selected Fast, Context-aware, or Fast + review mode. Stop live subtitles before running the comparison. Manual
ratings and custom text remain in RAM only and are cleared when the window closes.

Details opens a resizable panel beside history. Select another sentence to switch
without dismissing a dialog. On narrow screens the setup sidebar is temporarily
hidden so history and sentence details remain usable.

Original speech and its pronunciation appear above the translation card. Play,
0.8x playback, Stop, and Recheck are grouped together. Edit transcript reveals the
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

The current release is **0.7.1**, tagged **v0.7.1** in Git. Version values are synchronized in `core/version.py`, `packaging/version.txt`, and `packaging/installer.iss`. Build the installer and portable archive with `python -m scripts.build_windows --installer`. These generated binaries and model weights are not committed to the repository. See `CHANGELOG.md` for release notes.
