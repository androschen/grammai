"""In-memory subtitle history for the current app session only."""

from __future__ import annotations

from collections import deque

from core.events import SubtitleUpdate

_MAX_ITEMS = 80



class SessionHistory:
    def __init__(self, max_items: int = _MAX_ITEMS) -> None:
        self._items: deque[SubtitleUpdate] = deque(maxlen=max_items)
        self._group = 0
        self._groups = {}

    def begin_context(self):
        self._group += 1

    def group_for(self, uid):
        return self._groups.get(uid)

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[SubtitleUpdate]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
        self._groups.clear()
        self.begin_context()

    def append(self, update: SubtitleUpdate) -> bool:
        """Store distinct utterances; ignore repeat delivery of the same event."""
        if not (update.target_text or "").strip() and not (update.native_text or "").strip():
            return False
        if self._items and self._is_duplicate(self._items[-1], update):
            return False
        self._items.append(update)
        self._groups[update.uid] = self._group
        retained = {item.uid for item in self._items}
        self._groups = {key:group for key,group in self._groups.items() if key in retained}
        return True

    def replace(self,update):
        for index,item in enumerate(self._items):
            if item.uid==update.uid:
                self._items[index]=update
                return True
        return False

    @staticmethod
    def _is_duplicate(previous: SubtitleUpdate, current: SubtitleUpdate) -> bool:
        return previous.uid == current.uid
