"""Subtitle label stack and audio meter used by the overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core.events import SubtitleUpdate


class SubtitleStack(QWidget):
    """Top: phonetics. Middle: target language. Bottom: native transcript."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.phonetics = QLabel("")
        self.target = QLabel("Waiting for audio…")
        self.native_phonetics = QLabel("")
        self.native = QLabel("")

        self.phonetics.setFont(QFont("Segoe UI", 14))
        self.target.setFont(QFont("Microsoft YaHei", 28, QFont.Weight.DemiBold))
        self.native_phonetics.setFont(QFont("Segoe UI", 12))
        self.native.setFont(QFont("Segoe UI", 16))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(4)
        for label, color in (
            (self.phonetics, "#D0D0D0"),
            (self.target, "#FFFFFF"),
            (self.native_phonetics, "#A8A8A8"),
            (self.native, "#E8E8E8"),
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setStyleSheet(f"background: transparent; color: {color};")
            layout.addWidget(label)

    def apply(self, update: SubtitleUpdate) -> None:
        target_ph = (update.phonetics or "").strip()
        native_ph = (update.native_phonetics or "").strip()
        if target_ph == native_ph:
            native_ph = ""
        self.phonetics.setText(target_ph)
        self.phonetics.setVisible(bool(target_ph))
        self.target.setText(update.target_text)
        self.native_phonetics.setText(native_ph)
        self.native_phonetics.setVisible(bool(native_ph))
        self.native.setText(update.native_text)
        self.native.setVisible(bool(update.native_text.strip()))

    def reset(self, message: str = "Subtitles on") -> None:
        self.phonetics.setText("")
        self.phonetics.setVisible(False)
        self.target.setText(message)
        self.native_phonetics.setText("")
        self.native_phonetics.setVisible(False)
        self.native.setText("")
        self.native.setVisible(False)


class AudioMeterWidget(QWidget):
    """Live level bar with an overlaid noise-gate marker.

    Stylesheet swaps only on threshold crossings. When interactive, drag
    on the bar to set the gate (Discord/OBS-style input sensitivity).
    """

    threshold_changed = Signal(int)
    clicked = Signal()

    INACTIVE_STYLE = """
        QProgressBar {
            background-color: #1E1E1E;
            border: 1px solid #3A3A3A;
            border-radius: 6px;
            color: transparent;
            text-align: center;
            min-height: 16px;
            max-height: 16px;
        }
        QProgressBar::chunk {
            background-color: #8A8A8A;
            border-radius: 6px;
        }
    """

    ACTIVE_STYLE = """
        QProgressBar {
            background-color: #1E1E1E;
            border: 1px solid #3A3A3A;
            border-radius: 6px;
            color: transparent;
            text-align: center;
            min-height: 16px;
            max-height: 16px;
        }
        QProgressBar::chunk {
            background-color: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #4CAF50,
                stop:1 #81C784
            );
            border-radius: 6px;
        }
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        threshold: int = 12,
        interactive: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(22 if interactive else 18)
        self.setMinimumWidth(120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.threshold = max(0, min(100, int(threshold)))
        self._is_active = False
        self._interactive = interactive
        self._dragging = False
        self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor if interactive else Qt.CursorShape.PointingHandCursor))

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.progress_bar.setStyleSheet(self.INACTIVE_STYLE)

        self._marker_layer = QWidget(self)
        self._marker_layer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._marker_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._marker = QFrame(self._marker_layer)
        self._marker.setFixedWidth(4 if interactive else 2)
        self._marker.setStyleSheet("QFrame { background-color: #E53935; border: none; border-radius: 1px; }")

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(self.progress_bar)
        stack.addWidget(self._marker_layer)

    def set_threshold(self, percent: int) -> None:
        self.threshold = max(1, min(80, int(percent)))
        self._place_marker()
        self.update_volume(self.progress_bar.value())

    def update_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        self.progress_bar.setValue(volume)

        active = volume >= self.threshold
        if active == self._is_active:
            return
        self._is_active = active
        self.progress_bar.setStyleSheet(self.ACTIVE_STYLE if active else self.INACTIVE_STYLE)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._interactive:
            self._dragging = True
            self._set_threshold_from_x(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._interactive and self._dragging:
            self._set_threshold_from_x(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._interactive:
            self._dragging = False
        else:
            self.clicked.emit()
        event.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_marker()

    def _set_threshold_from_x(self, x: float) -> None:
        width = max(self.width(), 1)
        percent = int(round(100.0 * x / width))
        self.set_threshold(percent)
        self.threshold_changed.emit(self.threshold)

    def _place_marker(self) -> None:
        width = max(self._marker_layer.width(), 1)
        height = self._marker_layer.height()
        marker_w = self._marker.width()
        x = int(round((width - marker_w) * self.threshold / 100.0))
        x = max(0, min(width - marker_w, x))
        self._marker.setGeometry(x, 0, marker_w, height)


GATE_PRESETS: tuple[tuple[str, int], ...] = (
    ("Sensitive", 6),
    ("Default", 12),
    ("Strict", 28),
)


class NoiseGateEditor(QWidget):
    """Settings control: live detector + draggable gate, with presets."""

    threshold_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None, threshold: int = 12) -> None:
        super().__init__(parent)
        self._volume = 0

        title = QLabel("Noise gate")
        title.setObjectName("field")
        hint = QLabel("Play audio, then drag the red marker so speech/media sits to the right of it.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.meter = AudioMeterWidget(self, threshold=threshold, interactive=True)
        self.meter.threshold_changed.connect(self._on_meter_threshold)

        self._status = QLabel("Waiting for audio…")
        self._status.setObjectName("hint")

        self._presets: dict[int, QPushButton] = {}
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(8)
        for name, value in GATE_PRESETS:
            button = QPushButton(name)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, v=value: self._apply_preset(v))
            self._presets[value] = button
            preset_row.addWidget(button)
        preset_row.addStretch(1)

        self.calibrate = QPushButton("Set from current level")
        self.calibrate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calibrate.clicked.connect(self._calibrate)
        preset_row.addWidget(self.calibrate)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.meter)
        layout.addWidget(self._status)
        layout.addLayout(preset_row)
        self._sync_presets(threshold)

    def set_threshold(self, percent: int) -> None:
        self.meter.set_threshold(percent)
        self._sync_presets(self.meter.threshold)
        self._refresh_status()

    def update_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self.meter.update_volume(self._volume)
        self._refresh_status()

    def _on_meter_threshold(self, percent: int) -> None:
        self._sync_presets(percent)
        self._refresh_status()
        self.threshold_changed.emit(percent)

    def _apply_preset(self, percent: int) -> None:
        self.set_threshold(percent)
        self.threshold_changed.emit(self.meter.threshold)

    def _calibrate(self) -> None:
        # Sit the gate just above the current floor so only louder speech opens it.
        percent = min(80, max(4, self._volume + 8))
        self.set_threshold(percent)
        self.threshold_changed.emit(self.meter.threshold)

    def _sync_presets(self, percent: int) -> None:
        for value, button in self._presets.items():
            button.blockSignals(True)
            button.setChecked(value == percent)
            button.blockSignals(False)

    def _refresh_status(self) -> None:
        if self._volume < 2:
            self._status.setText(f"Gate at {self.meter.threshold}% — waiting for audio")
            return
        if self._volume >= self.meter.threshold:
            self._status.setText(f"Gate open · level {self._volume}% (threshold {self.meter.threshold}%)")
        else:
            self._status.setText(f"Gate closed · level {self._volume}% is below {self.meter.threshold}%")
