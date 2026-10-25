"""Local NLLB translation via CTranslate2 (CPU int8)."""

from __future__ import annotations

from pathlib import Path

from core.config import AppConfig
from core.events import EventBus
from ml.phonetics import contains_cjk, contains_thai

_CT2_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"

NLLB_LANG = {
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "th": "tha_Thai",
    "id": "ind_Latn",
}


def whisper_to_short_code(language: str | None, text: str) -> str:
    raw = (language or "").lower()
    if raw:
        return "zh" if raw.startswith("zh") else raw
    if contains_cjk(text):
        return "zh"
    if contains_thai(text):
        return "th"
    return "unknown"



class NllbTranslator:
    """Lazy-loads a quantized NLLB-200 distilled model for en/zh/th/id."""

    def __init__(self, config: AppConfig, events: EventBus | None = None) -> None:
        self._config = config
        self._events = events
        self._translator = None
        self._tokenizer = None
        self._failure: str | None = None

    def configure(self, config: AppConfig) -> None:
        if self._config.translation_threads != config.translation_threads:
            self._translator = None
        self._config = config

    @property
    def is_ready(self) -> bool:
        return self._translator is not None and self._tokenizer is not None

    def ensure_loaded(self) -> None:
        if self.is_ready:
            return
        if self._failure:
            raise RuntimeError(self._failure)
        try:
            self._load()
        except Exception as exc:
            self._failure = str(exc)
            self._notify(f"Translator unavailable ({exc}). Use Retry models to try again.")
            raise

    def translate(self, text: str, source: str, target: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if source == target:
            return text
        src = NLLB_LANG.get(source)
        tgt = NLLB_LANG.get(target)
        if src is None or tgt is None:
            raise ValueError(f"Unsupported translation route: {source} -> {target}")
        self.ensure_loaded()
        assert self._translator is not None
        assert self._tokenizer is not None
        self._tokenizer.src_lang = src
        source_tokens = self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode(text))
        results = self._translator.translate_batch(
            [source_tokens],
            target_prefix=[[tgt]],
            beam_size=self._config.translation_beam_size,
            max_decoding_length=256,
        )
        hypothesis = results[0].hypotheses[0]
        if hypothesis and hypothesis[0] == tgt:
            hypothesis = hypothesis[1:]
        ids = self._tokenizer.convert_tokens_to_ids(hypothesis)
        return self._tokenizer.decode(ids, skip_special_tokens=True).strip()

    def _notify(self, message: str) -> None:
        if self._events is not None:
            self._events.status_changed.emit(message)

    def _load(self) -> None:
        import ctranslate2
        from transformers import AutoTokenizer

        model_dir = self._resolve_model_dir()
        self._notify("Loading NLLB translator (first run may download)…")
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, use_fast=False)
        self._translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            intra_threads=self._config.translation_threads,
        )
        self._notify("Translator ready.")

    def _resolve_model_dir(self) -> Path:
        from core.components import resolve
        managed=resolve('translation-fast')
        if managed:return managed.parent
        cache = Path.home() / ".grammai" / "models" / "nllb-200-distilled-600M-int8"
        if _looks_like_ct2(cache):
            return cache
        cache.mkdir(parents=True, exist_ok=True)
        raise ValueError('Fast translation model is missing. Install NLLB in Models > Manage components; downloads require an explicit setup action.')

    def _download_preconverted(self, dest: Path) -> Path:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=_CT2_REPO, local_dir=str(dest))
        if not _looks_like_ct2(dest):
            raise RuntimeError("Downloaded folder is not a CTranslate2 model.")
        return dest

    def close(self):
        self._translator = None
        self._tokenizer = None

    def reset_failure(self) -> None:
        self._failure = None



def _looks_like_ct2(path: Path) -> bool:
    if not path.is_dir():
        return False
    weights = path / "model.bin"
    vocabulary = any((path / name).is_file() for name in ("shared_vocabulary.json", "shared_vocabulary.txt"))
    return weights.is_file() and weights.stat().st_size > 0 and (path / "config.json").is_file() and vocabulary
