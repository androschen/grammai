"""Phonetic helpers for Chinese and Thai subtitle rows."""

from __future__ import annotations

from core.config import TargetLanguage


def chinese_with_pinyin(text: str) -> tuple[str, str]:
    """Return (Chinese characters, Pinyin with tone marks)."""
    from pypinyin import Style, pinyin

    syllables = pinyin(text, style=Style.TONE, heteronym=False)
    romanized = " ".join(syllable[0] for syllable in syllables if syllable)
    return text, romanized


def thai_with_romanization(text: str) -> tuple[str, str]:
    """Return (Thai script, romanized pronunciation)."""
    from pythainlp.transliterate import romanize

    from pythainlp.tokenize import word_tokenize

    words = word_tokenize(text, engine="newmm", keep_whitespace=False)
    return text, " ".join(romanize(word) if contains_thai(word) else word for word in words)


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def contains_thai(text: str) -> bool:
    return any("\u0e00" <= ch <= "\u0e7f" for ch in text)


def phonetics_for(text: str, language: TargetLanguage) -> str:
    if not text:
        return ""
    try:
        if language is TargetLanguage.CHINESE and contains_cjk(text):
            return chinese_with_pinyin(text)[1]
        if language is TargetLanguage.THAI and contains_thai(text):
            return thai_with_romanization(text)[1]
    except ImportError as exc:
        return f"[{exc.name} not installed]"
    return ""


def phonetics_auto(text: str) -> str:
    """Pinyin for Chinese script, romanization for Thai, otherwise empty."""
    if not text:
        return ""
    try:
        if contains_cjk(text):
            return chinese_with_pinyin(text)[1]
        if contains_thai(text):
            return thai_with_romanization(text)[1]
    except ImportError as exc:
        return f"[{exc.name} not installed]"
    return ""
