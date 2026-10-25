"""Session-only subtitle history list (control panel, not the overlay)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QCheckBox,
    QLineEdit,
    QComboBox,
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
from ui.copyable_text import CopyableLabel


def source_language_badge(language):
    """Show the sentence's source language, never the translation destination."""
    languages={'zh':('CN','Chinese'),'en':('EN','English'),
               'th':('TH','Thai'),'id':('ID','Indonesian')}
    code,name=languages.get(language,('??','Unknown'))
    badge=QLabel(code)
    badge.setObjectName('sourceLanguageBadge');badge.setProperty('language',language)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setToolTip('Original speech: '+name)
    badge.setAccessibleName('Original speech language: '+name)
    badge.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
    return badge


class SuggestionPreview(CopyableLabel):
    """Keep full copyable text while limiting the visible preview to two lines."""
    def __init__(self,text,parent=None):
        super().__init__(text,parent)
        self.setObjectName('aiSuggestionText')
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setToolTip('Local AI suggestion - not applied. Open Details for the full comparison.\n'+text)
        self.setAccessibleName('Local AI suggestion, not applied')
        self._update_limit()

    def _update_limit(self):
        margins=self.contentsMargins()
        self.setMaximumHeight(self.fontMetrics().lineSpacing()*2+self.margin()*2+margins.top()+margins.bottom())

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):
            self._update_limit()


class RevisionMarker(QLabel):
    """Icon-only provenance marker that follows theme changes."""
    def __init__(self,update,parent=None):
        super().__init__(parent)
        self._icon_name='sparkles' if update.ai_refined else 'edit'
        self.setObjectName('revisionBadge')
        self.setAccessibleName('AI refined' if update.ai_refined else revision_label(update))
        self.setToolTip(self.accessibleName()+'. Not verified correct. Open translation history for original wording.')
        self._refresh_icon()
    def _refresh_icon(self):
        from PySide6.QtGui import QIcon
        from ui.icons import LineIcon
        self.setPixmap(QIcon(LineIcon(self._icon_name)).pixmap(14,14))
    def changeEvent(self,event):
        super().changeEvent(event)
        if hasattr(self,'_icon_name') and event.type() in (QEvent.Type.StyleChange,QEvent.Type.PaletteChange):self._refresh_icon()


class HistoryCard(QFrame):
    study_requested = Signal(object)
    explain_requested = Signal(object)
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
        header = QHBoxLayout()
        header.addWidget(stamp)
        if update.suggested_translation:
            marker=QLabel('\u2726');marker.setObjectName('revisionBadge')
            marker.setToolTip('Translation suggestion available. Open Details to compare and apply.')
            marker.setAccessibleName('Translation suggestion available');header.addWidget(marker)
        header.addWidget(source_language_badge(update.source_language))
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
        layout.addLayout(header)

        def add_line(text: str, name: str, font: QFont) -> None:
            if not text:
                return
            label = CopyableLabel(text)
            label.setObjectName(name)
            if name in ('target','native'):
                original=name=='native' or update.target_text==update.native_text
                label.explain_handler=lambda phrase,original=original,text=text:self.explain_requested.emit({
                    'update':self.subtitle,'phrase':phrase,'sentence':text,
                    'language':update.source_language if original else update.target_language,
                    'text_role':'original' if original else 'translation'})
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
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
        from ui.icons import icon_button
        layout=QHBoxLayout(self);layout.setContentsMargins(14,9,12,9);layout.setSpacing(10)
        badge=source_language_badge(update.source_language);badge.setFixedWidth(28);badge.setToolTip(badge.toolTip()+' · '+update.created_at.strftime('%H:%M:%S'));layout.addWidget(badge,0,Qt.AlignmentFlag.AlignTop)
        column=QVBoxLayout();column.setContentsMargins(0,0,0,0);column.setSpacing(3)
        def label(text,name,original=False,destination=None):
            value=CopyableLabel(text,self);value.setObjectName(name);value.setWordWrap(True);value.setTextFormat(Qt.TextFormat.PlainText)
            value.explain_handler=lambda phrase:self.explain_requested.emit({'update':self.subtitle,'phrase':phrase,'sentence':text,'language':update.source_language if original else update.target_language,'text_role':'original' if original else 'translation'})
            (destination if destination is not None else column).addWidget(value);return value
        label(update.native_text,'originalSpeech',True)
        if update.native_phonetics:label(update.native_phonetics,'phonetic',True)
        translated=bool(update.target_text and update.target_text!=update.native_text)
        if translated:
            translation_row=QHBoxLayout();translation_row.setContentsMargins(0,0,0,0);translation_row.setSpacing(6)
            value=label(update.target_text,'target',destination=translation_row);translation_row.setStretch(0,1)
            if revision_label(update):translation_row.addWidget(RevisionMarker(update,self),0,Qt.AlignmentFlag.AlignTop)
            column.addLayout(translation_row)
        elif update.translation_status=='unavailable':label('Translation unavailable','hint')
        layout.addLayout(column,1)
        self.details_button=icon_button('chevron','Understand this sentence',self);self.details_button.clicked.connect(lambda:self.study_requested.emit(self.subtitle));layout.addWidget(self.details_button,0,Qt.AlignmentFlag.AlignTop)


class HistoryPanel(QWidget):
    cleared = Signal()
    study_requested = Signal(object)
    explain_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_uid=None
        header = QLabel("Session history")
        header.setObjectName("field")

        self._count = QLabel("0 lines")
        self._count.setObjectName("hint")

        from ui.icons import icon_button
        clear = icon_button("trash","Clear temporary session history",self)
        clear.setObjectName("secondary")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._on_clear_clicked)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        header.setText("Session history")
        top.addWidget(header)
        top.addStretch(1)
        self._follow = QCheckBox("Auto-scroll")
        self._follow.setChecked(True)
        top.addWidget(self._follow)
        top.addWidget(self._count)
        self._filter_toggle=icon_button("search","Search and filter history",self);self._filter_toggle.setCheckable(True);top.addWidget(self._filter_toggle)
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
        self._deferred_updates={}
        self._selection_timer=QTimer(self);self._selection_timer.setInterval(150);self._selection_timer.timeout.connect(self._flush_deferred)
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.timeout.connect(self._scroll_bottom)
        scroll.verticalScrollBar().rangeChanged.connect(self._schedule_follow)
        self._user_scroll_active=False
        self._user_scroll_before=0
        scroll.viewport().installEventFilter(self);scroll.verticalScrollBar().installEventFilter(self)
        scroll.verticalScrollBar().sliderMoved.connect(self._slider_moved)
        self._follow.toggled.connect(self._follow_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(top)
        filters=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('Search transcript, translation or pronunciation')
        self.search.setClearButtonEnabled(True);self.search.setAccessibleName('Search session history')
        self.language_filter=QComboBox();self.language_filter.setAccessibleName('Filter original speech language')
        for label,code in (('All languages',''),('Chinese','zh'),('English','en'),('Thai','th'),('Indonesian','id')):
            self.language_filter.addItem(label,code)
        filters.addWidget(self.search,1);filters.addWidget(self.language_filter)
        self._filters=QWidget();self._filters.setLayout(filters);self._filters.hide();layout.addWidget(self._filters)
        self._filter_toggle.toggled.connect(self._filters.setVisible)
        self.search.textChanged.connect(self._apply_filter)
        self.language_filter.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(scroll, 1)

    def eventFilter(self,obj,event):
        if obj in (self._scroll.viewport(),self._scroll.verticalScrollBar()):
            kind=event.type()
            scroll_key=kind==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Up,Qt.Key.Key_Down,Qt.Key.Key_PageUp,Qt.Key.Key_PageDown,Qt.Key.Key_Home,Qt.Key.Key_End)
            if kind==QEvent.Type.Wheel or scroll_key or (obj is self._scroll.verticalScrollBar() and kind==QEvent.Type.MouseButtonPress):
                self._user_scroll_before=self._scroll.verticalScrollBar().value();self._user_scroll_active=True;self._follow_timer.stop()
                if kind!=QEvent.Type.MouseButtonPress:QTimer.singleShot(0,self._finish_user_scroll)
            elif obj is self._scroll.verticalScrollBar() and kind==QEvent.Type.MouseButtonRelease:
                QTimer.singleShot(0,self._finish_user_scroll)
        return super().eventFilter(obj,event)

    def _slider_moved(self,position):
        if self._user_scroll_active and position<self._scroll.verticalScrollBar().maximum()-4:self._follow.setChecked(False)

    def _finish_user_scroll(self):
        if not self._user_scroll_active:return
        self._user_scroll_active=False
        bar=self._scroll.verticalScrollBar()
        if bar.value()!=self._user_scroll_before and bar.value()<bar.maximum()-4:self._follow.setChecked(False)
        else:self._schedule_follow()

    def _follow_changed(self,enabled):
        self._follow.setToolTip("Follow new sentences" if enabled else "Reading older sentences. Check Auto-scroll to follow again.")
        if enabled:
            self._user_scroll_active=False;self._scroll_bottom()
        self._schedule_follow()

    def append(self, update: SubtitleUpdate) -> None:
        self._empty.hide()
        card = HistoryCard(update)
        card.study_requested.connect(self.study_requested.emit)
        card.explain_requested.connect(self.explain_requested.emit)
        self._list.addWidget(card)
        while self._card_count() > 80:
            self._remove_oldest_card()
        self._apply_filter()
        self._schedule_follow()

    def _flush_deferred(self):
        for update in list(self._deferred_updates.values()):self.replace_update(update)
        if not self._deferred_updates:self._selection_timer.stop()

    def replace_update(self,update):
        for index in range(self._list.count()):
            old=self._list.itemAt(index).widget()
            if isinstance(old,HistoryCard) and old.subtitle.uid==update.uid:
                if any(label.hasSelectedText() for label in old.findChildren(CopyableLabel)):
                    self._deferred_updates[update.uid]=update;self._selection_timer.start();return True
                self._deferred_updates.pop(update.uid,None)
                self._list.takeAt(index)
                old.hide()
                old.deleteLater()
                card=HistoryCard(update);card.setProperty('selected',update.uid==self._selected_uid)
                card.study_requested.connect(self.study_requested.emit)
                card.explain_requested.connect(self.explain_requested.emit)
                self._list.insertWidget(index,card)
                self._apply_filter()
                return True
        return False

    def _schedule_follow(self, *args):
        if self._follow.isChecked() and self._card_count() and not self._user_scroll_active:
            # Let Qt finish deferred wrapping and scroll-content resizing first.
            self._follow_timer.start(16)
        else:
            self._follow_timer.stop()

    def _scroll_bottom(self):
        if not self._follow.isChecked() or self._user_scroll_active:
            return
        # Follow the final sentence, not unused space in the scroll content.
        self._list.activate()
        for index in reversed(range(self._list.count())):
            card = self._list.itemAt(index).widget()
            if isinstance(card, HistoryCard) and not card.isHidden():
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
        self._selection_timer.stop();self._deferred_updates.clear()
        self._user_scroll_active=False
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
        self._apply_filter()

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
                self._deferred_updates.pop(widget.subtitle.uid,None)
                self._list.takeAt(i)
                widget.hide()
                widget.deleteLater()
                return

    def _apply_filter(self,*args):
        query=self.search.text().strip().casefold()
        language=self.language_filter.currentData()
        total=visible=0
        for index in range(self._list.count()):
            card=self._list.itemAt(index).widget()
            if not isinstance(card,HistoryCard):
                continue
            total+=1;u=card.subtitle
            text=' '.join((u.native_text,u.target_text,u.phonetics,u.native_phonetics,u.suggested_translation)).casefold()
            match=(not language or u.source_language==language) and (not query or query in text)
            card.setVisible(match);visible+=int(match)
        self._empty.setText('No matching sentences.' if total else 'No lines yet. Start translation and play audio - history stays here until you quit.')
        self._empty.setVisible(not visible)
        self._count.setText(f'{visible} / {total} lines' if query or language else ('1 line' if total==1 else f'{total} lines'))
        self._schedule_follow()

    def select_sentence(self,uid):
        self._selected_uid=uid
        for index in range(self._list.count()):
            card=self._list.itemAt(index).widget()
            if isinstance(card,HistoryCard):
                card.setProperty('selected',card.subtitle.uid==uid);card.style().unpolish(card);card.style().polish(card);card.update()

    def _refresh_count(self) -> None:
        n = self._card_count()
        self._count.setText("1 line" if n == 1 else f"{n} lines")
