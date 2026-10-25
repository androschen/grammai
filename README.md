# GrammAI

Learn languages from real conversations, locally on Windows.

**[Download v0.15.3](https://github.com/androschen/grammai/releases/tag/v0.15.3)** · [Windows setup](WINDOWS.md) · [User guide](docs/USAGE.md) · [Changelog](CHANGELOG.md)

![GrammAI learning deck with conversation examples and pronunciation](docs/images/grammai-desktop.png)

*Actual app UI with synthetic examples; no personal cards or conversations.*

## Features

- Live transcription and translation from desktop audio or a microphone.
- Switch speech models: Whisper base, large-v3-turbo, large-v3 or experimental Qwen3-ASR.
- Separate live translation and optional AI refinement, with model information in sentence details.
- Chinese, Thai, English and Indonesian, with Pinyin and Thai romanization.
- Compact subtitles, a unified light/dark interface, and CPU/GPU resource graphs.
- Saved vocabulary, notes, word explanations, original audio and recall practice.
- Local AI reply suggestions and a Listen/Stop pronunciation button.

Speech recognition, translation and AI explanations run locally after model setup. Listen uses a matching installed Windows voice. Models and extra voices are separate downloads.

## Get started

Install the Windows package from [Releases](https://github.com/androschen/grammai/releases/latest), configure your models, select an audio source and languages, then press Play. Use CC to show or hide desktop subtitles.

For the latest source version:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Your data

Cards, recordings and settings stay in `%LOCALAPPDATA%\GrammAI`. Back up `phrases.json` and `audio/` together. Session conversations are temporary.

See the [user guide](docs/USAGE.md) for learning tools and [Windows setup](WINDOWS.md) for models and building the app.
