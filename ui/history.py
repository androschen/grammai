"""Session-only subtitle history list (control panel, not the overlay)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.events import SubtitleUpdate
from core.revisions import revision_label




class HistoryCard(QFrame):
    study_requested = Signal(object)
    def __init__(self, update: SubtitleUpdate, parent: QWidget | None = None, featured: bool = False) -> None:
        super().__init__(parent)
        self.subtitle=update
        self.setObjectName("HistoryCard")
        self.setProperty("featured",featured)
        if not featured:
            self._build_compact(update)
            return

        target_ph = (update.phonetics or "").strip()
        native_ph = (update.native_phonetics or "").strip()
        if target_ph == native_ph:
            native_ph = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20 if featured else 16, 16, 20 if featured else 16, 16)
        layout.setSpacing(6)
        stamp = QLabel(update.created_at.strftime("%H:%M:%S"))
        stamp.setObjectName("phonetic")
        copy = QPushButton("Copy")
        copy.setObjectName("secondary")
        copy.clicked.connect(lambda: self._copy(update))
        header = QHBoxLayout()
        header.addWidget(stamp)
        if revision_label(update):
            badge=QLabel('\u270e')
            badge.setObjectName('revisionBadge')
            badge.setAccessibleName(revision_label(update))
            badge.setToolTip(revision_label(update)+'. Revised does not mean verified correct.')
            header.addWidget(badge)
        header.addStretch()
        study=QPushButton("Details")
        study.clicked.connect(lambda:self.study_requested.emit(self.subtitle))
        header.addWidget(study)
        header.addWidget(copy)
        layout.addLayout(header)

        def add_line(text: str, name: str, font: QFont) -> None:
            if not text:
                return
            label = QLabel(text)
            label.setObjectName(name)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setFont(font)
            layout.addWidget(label)

        if update.translation_status == "unavailable":
            add_line("Translation unavailable - original transcript below", "phonetic", QFont("Segoe UI", 10))
        add_line(target_ph, "phonetic", QFont("Segoe UI", 10))
        add_line((update.target_text or "").strip(), "target", QFont("Microsoft YaHei", 13, QFont.Weight.DemiBold))
        add_line(native_ph, "phonetic", QFont("Segoe UI", 10))
        native = (update.native_text or "").strip()
        if native and native != (update.target_text or "").strip():
            add_line(native, "native", QFont("Segoe UI", 11))

    def _build_compact(self, update):
        layout=QVBoxLayout(self)
        layout.setContentsMargins(10,6,10,6)
        layout.setSpacing(3)
        row=QHBoxLayout()
        row.setSpacing(8)
        stamp=QLabel(update.created_at.strftime('%H:%M'))
        stamp.setObjectName('hint')
        stamp.setFixedWidth(36)
        row.addWidget(stamp,0,Qt.AlignmentFlag.AlignTop)
        revision=revision_label(update)
        if revision:
            badge=QLabel('\u270e')
            badge.setObjectName('revisionBadge')
            badge.setToolTip(revision+'. Revised does not mean verified correct.')
            badge.setAccessibleName(revision)
            row.addWidget(badge,0,Qt.AlignmentFlag.AlignTop)
        text=update.target_text or update.native_text
        if update.translation_status == 'unavailable':
            text='Original: '+update.native_text
        target=QLabel(text)
        target.setObjectName('target')
        target.setWordWrap(True)
        target.setTextFormat(Qt.TextFormat.PlainText)
        target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(target,1)
        self.details_button=QPushButton('Details')
        self.details_button.setToolTip('Original audio, pronunciation, revisions and manual recheck')
        self.details_button.clicked.connect(lambda:self.study_requested.emit(self.subtitle))
        row.addWidget(self.details_button,0,Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)

    def _copy(self, update):
        from PySide6.QtWidgets import QApplication
        lines = [update.phonetics, update.target_text, update.native_phonetics, update.native_text]
        QApplication.clipboard().setText("\n".join(dict.fromkeys(x for x in lines if x)))


class HistoryPanel(QWidget):
    cleared = Signal()
    study_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        header = QLabel("Session history")
        header.setObjectName("field")

        self._count = QLabel("0 lines")
        self._count.setObjectName("hint")

        clear = QPushButton("Clear")
        clear.setObjectName("secondary")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._on_clear_clicked)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(header)
        top.addStretch(1)
        self._follow = QCheckBox("Auto-scroll")
        self._follow.setChecked(True)
        top.addWidget(self._follow)
        top.addWidget(self._count)
        top.addWidget(clear)

        self._empty = QLabel("No lines yet. Start translation and play audio — history stays here until you quit.")
        self._empty.setObjectName("hint")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setMinimumHeight(180)

        self._list = QVBoxLayout()
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(4)
        self._list.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self._list.addWidget(self._empty)

        inner = QWidget()
        inner.setLayout(self._list)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(220)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.timeout.connect(self._scroll_bottom)
        scroll.verticalScrollBar().rangeChanged.connect(self._schedule_follow)
        self._follow.toggled.connect(self._schedule_follow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)

    def append(self, update: SubtitleUpdate) -> None:
        self._empty.hide()
        card = HistoryCard(update)
        card.study_requested.connect(self.study_requested.emit)
        self._list.addWidget(card)
        while self._card_count() > 80:
            self._remove_oldest_card()
        self._refresh_count()
        self._schedule_follow()

    def replace_update(self,update):
        for index in range(self._list.count()):
            old=self._list.itemAt(index).widget()
            if isinstance(old,HistoryCard) and old.subtitle.uid==update.uid:
                self._list.takeAt(index)
                old.hide()
                old.deleteLater()
                card=HistoryCard(update)
                card.study_requested.connect(self.study_requested.emit)
                self._list.insertWidget(index,card)
                self._schedule_follow()
                return True
        return False

    def _schedule_follow(self, *args):
        if self._follow.isChecked() and self._card_count():
            # Let Qt finish deferred wrapping and scroll-content resizing first.
            self._follow_timer.start(16)
        else:
            self._follow_timer.stop()

    def _scroll_bottom(self):
        if not self._follow.isChecked():
            return
        # Follow the final sentence, not unused space in the scroll content.
        self._list.activate()
        for index in reversed(range(self._list.count())):
            card = self._list.itemAt(index).widget()
            if isinstance(card, HistoryCard):
                # ensureWidgetVisible may use a card's hidden details/focus child.
                # Its layout geometry is the visible sentence's actual extent.
                bar = self._scroll.verticalScrollBar()
                bar.setValue(max(0, card.geometry().bottom() + 1
                                 - self._scroll.viewport().height()))
                break

    def _on_clear_clicked(self) -> None:
        self.clear()
        self.cleared.emit()

    def clear(self) -> None:
        self._follow_timer.stop()
        index = 0
        while index < self._list.count():
            widget = self._list.itemAt(index).widget()
            if isinstance(widget, HistoryCard):
                self._list.takeAt(index)
                widget.hide()
                widget.deleteLater()
            else:
                index += 1
        self._empty.show()
        self._scroll.verticalScrollBar().setValue(0)
        self._refresh_count()

    def _card_count(self) -> int:
        return sum(
            1
            for i in range(self._list.count())
            if isinstance(self._list.itemAt(i).widget(), HistoryCard)
        )

    def _remove_oldest_card(self) -> None:
        for i in range(self._list.count()):
            widget = self._list.itemAt(i).widget()
            if isinstance(widget, HistoryCard):
                self._list.takeAt(i)
                widget.hide()
                widget.deleteLater()
                return

    def _refresh_count(self) -> None:
        n = self._card_count()
        self._count.setText("1 line" if n == 1 else f"{n} lines")
