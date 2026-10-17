"""Persist preferences and benchmark summaries; never subtitle history."""
from __future__ import annotations
import json
import os
from dataclasses import asdict
from pathlib import Path
from core.config import AppConfig, QualityMode, TargetLanguage


def data_dir() -> Path:
    override = os.environ.get("GRAMMAI_DATA_DIR")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GrammAI"


def read_json(name: str, default):
    try:
        return json.loads((data_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name: str, value) -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / (name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(folder / name)


def save_config(config: AppConfig) -> None:
    write_json("preferences.json", asdict(config))


def load_config() -> AppConfig:
    config = AppConfig()
    saved = read_json("preferences.json", {})
    if not isinstance(saved, dict):
        return config
    # Capture format is internal; only restore user-facing preferences.
    names = {"target_language", "source_language", "audio_device_id", "audio_device_name",
             "audio_device_kind", "noise_threshold", "quality_mode", "cpu_threads",
             "translation_threads", "backend", "vulkan_executable", "vulkan_model",
             "theme", "show_overlay", "show_pronunciation", "subtitle_font_size", "overlay_opacity",
             "overlay_position"}
    for name in names:
        if name not in saved:
            continue
        value = saved[name]
        default = getattr(config, name)
        try:
            if name == "quality_mode":
                value = QualityMode(value)
            elif name == "target_language":
                value = TargetLanguage(value)
            elif type(value) is not type(default):
                continue
            setattr(config, name, value)
        except (TypeError, ValueError):
            continue
    if config.theme not in ("dark", "light"):
        config.theme = "dark"
    config.cpu_threads = max(1, min(16, config.cpu_threads))
    config.translation_threads = max(1, min(8, config.translation_threads))
    config.noise_threshold = max(.01, min(.8, config.noise_threshold))
    config.subtitle_font_size = max(16, min(48, config.subtitle_font_size))
    config.overlay_opacity = max(40, min(240, config.overlay_opacity))
    if config.backend not in ("cpu", "vulkan"):
        config.backend = "cpu"
    if config.source_language not in ("auto", "en", "zh", "th"):
        config.source_language = "auto"
    if config.overlay_position not in ("top", "bottom"):
        config.overlay_position = "bottom"
    config.apply_quality()
    return config
