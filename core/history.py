"""In-memory subtitle history for the current app session only."""

from __future__ import annotations

from collections import deque

from core.events import SubtitleUpdate

_MAX_ITEMS = 80


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()


class SessionHistory:
    def __init__(self, max_items: int = _MAX_ITEMS) -> None:
        self._items: deque[SubtitleUpdate] = deque(maxlen=max_items)

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[SubtitleUpdate]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()

    def append(self, update: SubtitleUpdate) -> bool:
        """Return True if the line was stored (not empty / not a near-duplicate)."""
        if not (update.target_text or "").strip() and not (update.native_text or "").strip():
            return False
        if self._items and self._is_duplicate(self._items[-1], update):
            return False
        self._items.append(update)
        return True

    @staticmethod
    def _is_duplicate(previous: SubtitleUpdate, current: SubtitleUpdate) -> bool:
        return _norm(previous.native_text) == _norm(current.native_text) and _norm(
            previous.target_text
        ) == _norm(current.target_text)
