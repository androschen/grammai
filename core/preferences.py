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
    names = {"processing_mode","speech_model_id","learning_model_id","translation_model_id","gpu_device","setup_completed","saved_audio_limit_mb", "target_language", "source_language", "audio_device_id", "audio_device_name",
             "audio_device_kind", "noise_threshold", "quality_mode", "cpu_threads",
             "translation_mode", "translation_enabled", "translation_threads", "backend", "vulkan_executable", "vulkan_model",
             "theme", "show_overlay", "show_pronunciation", "subtitle_font_size", "overlay_opacity",
             "overlay_position", "analysis_enabled", "analysis_endpoint", "analysis_model", "analysis_key_env",
             "analysis_provider", "analysis_executable", "analysis_gguf", "analysis_context_tokens",
             "analysis_context_sentences", "analysis_idle_minutes", "analysis_speech_style",
             "analysis_translation_style", "analysis_explanation_language", "analysis_explain_slang",
             "analysis_glossary", "analysis_examples", "analysis_reasoning",
             "overlay_hud_opacity", "overlay_show_hud", "overlay_show_original", "overlay_text_outline",
             "overlay_text_shadow", "overlay_padding", "overlay_corner_radius", "overlay_max_width",
             "speech_detection","speech_max_seconds","speech_silence_seconds","speech_overlap_seconds","speech_prompt"}
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
    if config.processing_mode not in ('legacy','auto','cpu','gpu'):config.processing_mode='legacy'
    if 'setup_completed' not in saved and saved:config.setup_completed=True
    if config.translation_mode not in ("fast", "context", "review"):
        config.translation_mode = "fast"
    if config.theme not in ("dark", "light"):
        config.theme = "dark"
    if config.saved_audio_limit_mb not in (100,250,500):config.saved_audio_limit_mb=250
    config.cpu_threads = max(1, min(16, config.cpu_threads))
    config.translation_threads = max(1, min(8, config.translation_threads))
    config.noise_threshold = max(.01, min(.8, config.noise_threshold))
    config.subtitle_font_size = max(16, min(48, config.subtitle_font_size))
    config.overlay_opacity = max(0, min(255, config.overlay_opacity))
    config.overlay_hud_opacity = max(0,min(100,config.overlay_hud_opacity))
    config.overlay_padding = max(8,min(36,config.overlay_padding))
    config.overlay_corner_radius = max(0,min(32,config.overlay_corner_radius))
    config.overlay_max_width = max(35,min(95,config.overlay_max_width))
    if config.backend not in ("cpu", "vulkan"):
        config.backend = "cpu"
    if config.source_language not in ("auto", "auto_trio", "auto_four", "en", "zh", "th", "id"):
        config.source_language = "auto"
    if config.overlay_position not in ("top", "bottom"):
        config.overlay_position = "bottom"
    config.apply_quality()
    config.speech_max_seconds=max(2.,min(8.,config.speech_max_seconds))
    config.speech_silence_seconds=max(.24,min(1.,config.speech_silence_seconds))
    config.speech_overlap_seconds=max(0.,min(.8,config.speech_overlap_seconds))
    config.speech_prompt=config.speech_prompt[:300]
    if config.analysis_provider not in ('local', 'online'):
        config.analysis_provider = 'local'
    if config.analysis_speech_style not in ('everyday', 'neutral', 'formal'):
        config.analysis_speech_style = 'everyday'
    if config.analysis_translation_style not in ('preserve_tone', 'natural', 'literal'):
        config.analysis_translation_style = 'preserve_tone'
    if config.analysis_explanation_language not in ('id','en','zh','th'):
        config.analysis_explanation_language = 'id'
    config.analysis_context_tokens = max(2048, min(8192, config.analysis_context_tokens))
    config.analysis_context_sentences = max(0, min(5, config.analysis_context_sentences))
    config.analysis_idle_minutes = max(0, min(30, config.analysis_idle_minutes))
    config.analysis_glossary = config.analysis_glossary[:4000]
    from core.tutor import examples
    config.analysis_examples = json.dumps(examples(config), ensure_ascii=False)
    return config
