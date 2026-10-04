"""
GrammAI MVP — control panel + click-through subtitle overlay.

The overlay cannot host buttons (it is input-transparent). A normal desktop
window starts/stops the bar and the background pipeline thread.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------


class TargetLanguage(str, Enum):
    ENGLISH = "en"
    CHINESE = "zh"
    THAI = "th"


LANGUAGE_LABELS: dict[TargetLanguage, str] = {
    TargetLanguage.ENGLISH: "English",
    TargetLanguage.CHINESE: "Chinese",
    TargetLanguage.THAI: "Thai",
}


def chinese_with_pinyin(text: str) -> tuple[str, str]:
    """Return (Chinese characters, Pinyin with tone marks)."""
    from pypinyin import Style, pinyin

    syllables = pinyin(text, style=Style.TONE, heteronym=False)
    romanized = " ".join(syllable[0] for syllable in syllables if syllable)
    return text, romanized


def thai_with_romanization(text: str) -> tuple[str, str]:
    """Return (Thai script, romanized pronunciation)."""
    from pythainlp.transliterate import romanize

    return text, romanize(text)


def phonetics_for(text: str, language: TargetLanguage) -> str:
    """Phonetic line for the overlay, or empty when not applicable."""
    if not text:
        return ""
    try:
        if language is TargetLanguage.CHINESE:
            return chinese_with_pinyin(text)[1]
        if language is TargetLanguage.THAI:
            return thai_with_romanization(text)[1]
    except ImportError as exc:
        return f"[{exc.name} not installed]"
    return ""


# ---------------------------------------------------------------------------
# Subtitle payload (same shape the future Whisper pipeline will emit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubtitleUpdate:
    phonetics: str
    target_text: str
    native_text: str


# Rotating mock pair: native (source) English + target Chinese.
# Replace this list when the audio/Whisper loop is connected.
MOCK_PAIRS: list[tuple[str, str]] = [
    ("Hello, how are you today?", "你好，你今天怎么样？"),
    ("The meeting starts in five minutes.", "会议五分钟后开始。"),
    ("Please turn on the subtitles.", "请打开字幕。"),
]


# ---------------------------------------------------------------------------
# Background pipeline thread
# ---------------------------------------------------------------------------


class TranslationWorker(QThread):
    """
    Captures / transcribes / translates on a background thread.

    Phase 1 emits mock SubtitleUpdate payloads every 3 seconds.
    Later this run() loop will buffer ~3–4s of WASAPI loopback audio
    and pass it to faster-whisper.
    """

    subtitle_ready = Signal(object)  # SubtitleUpdate
    status_changed = Signal(str)

    def __init__(self, target_language: TargetLanguage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_language = target_language

    def run(self) -> None:
        self.status_changed.emit("Listening (mock pipeline — audio/Whisper not wired yet).")
        index = 0
        while not self.isInterruptionRequested():
            native, chinese = MOCK_PAIRS[index % len(MOCK_PAIRS)]
            index += 1

            target_text, phonetics = self._mock_target_and_phonetics(native, chinese)
            self.subtitle_ready.emit(
                SubtitleUpdate(
                    phonetics=phonetics,
                    target_text=target_text,
                    native_text=native,
                )
            )

            # 3s cadence matches the planned audio buffer length.
            self.msleep(3000)

        self.status_changed.emit("Idle")

    def _mock_target_and_phonetics(self, native: str, chinese: str) -> tuple[str, str]:
        """Stand-in for Whisper translate + phonetic post-process."""
        lang = self._target_language
        if lang is TargetLanguage.CHINESE:
            return chinese, phonetics_for(chinese, lang)
        if lang is TargetLanguage.THAI:
            thai = "สวัสดี นี่คือข้อความทดสอบ"
            return thai, phonetics_for(thai, lang)
        return native, ""

    def stop(self) -> None:
        self.requestInterruption()


# ---------------------------------------------------------------------------
# Overlay UI (no controls — clicks pass through)
# ---------------------------------------------------------------------------


class SubtitleOverlay(QWidget):
    """Frameless, always-on-top, click-through subtitle bar at the bottom."""

    def __init__(self) -> None:
        super().__init__(None)
        self._set_window_flags()
        self._build_ui()
        self._place_at_bottom()

    def _set_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _build_ui(self) -> None:
        self._phonetics = QLabel("")
        self._target = QLabel("Waiting for audio…")
        self._native = QLabel("")

        for label in (self._phonetics, self._target, self._native):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setStyleSheet("background: transparent; color: white;")

        self._phonetics.setFont(QFont("Segoe UI", 14))
        self._phonetics.setStyleSheet("background: transparent; color: #D0D0D0;")

        self._target.setFont(QFont("Microsoft YaHei", 28, QFont.Weight.DemiBold))
        self._target.setStyleSheet("background: transparent; color: #FFFFFF;")

        self._native.setFont(QFont("Segoe UI", 16))
        self._native.setStyleSheet("background: transparent; color: #E8E8E8;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(4)
        layout.addWidget(self._phonetics)
        layout.addWidget(self._target)
        layout.addWidget(self._native)

    def _place_at_bottom(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 160)
            return
        geo = screen.availableGeometry()
        width = int(geo.width() * 0.72)
        height = 168
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - 48
        self.setGeometry(x, y, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 12, 12)
        super().paintEvent(event)

    @Slot(object)
    def apply_subtitle(self, update: SubtitleUpdate) -> None:
        self._phonetics.setText(update.phonetics)
        self._phonetics.setVisible(bool(update.phonetics.strip()))
        self._target.setText(update.target_text)
        self._native.setText(update.native_text)

    def reset_text(self) -> None:
        self._phonetics.setText("")
        self._phonetics.setVisible(False)
        self._target.setText("Subtitles on")
        self._native.setText("")


# ---------------------------------------------------------------------------
# Desktop control panel
# ---------------------------------------------------------------------------

_PANEL_STYLE = """
ControlPanel {
    background: #161616;
}
QLabel#title {
    color: #FFFFFF;
    font-size: 20px;
    font-weight: 600;
}
QLabel#hint, QLabel#status {
    color: #B0B0B0;
    font-size: 12px;
}
QLabel#field {
    color: #E8E8E8;
    font-size: 13px;
}
QComboBox {
    background: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 28px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #2A2A2A;
    color: #FFFFFF;
    selection-background-color: #3D3D3D;
}
QPushButton#toggle {
    background: #2F2F2F;
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 600;
    padding: 14px;
}
QPushButton#toggle[active="true"] {
    background: #1F6FEB;
}
QPushButton#secondary {
    background: transparent;
    color: #C8C8C8;
    border: 1px solid #3A3A3A;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton#secondary:hover {
    background: #2A2A2A;
    color: #FFFFFF;
}
"""


class ControlPanel(QWidget):
    """Normal window that owns the overlay and starts/stops the pipeline."""

    def __init__(self, target_language: TargetLanguage) -> None:
        super().__init__(None)
        self._target_language = target_language
        self._subtitles_on = False
        self._quitting = False
        self._worker: TranslationWorker | None = None

        self.setWindowTitle("GrammAI")
        self.setFixedSize(420, 300)
        self.setStyleSheet(_PANEL_STYLE)

        self._overlay = SubtitleOverlay()
        self._build_ui()
        self._tray = self._build_tray()
        self._sync_ui()

    def _build_ui(self) -> None:
        title = QLabel("GrammAI")
        title.setObjectName("title")

        hint = QLabel("Turn subtitles on to show the overlay. Close this window to hide it in the tray.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        lang_label = QLabel("Target language")
        lang_label.setObjectName("field")

        self._language = QComboBox()
        for lang, label in LANGUAGE_LABELS.items():
            self._language.addItem(label, lang.value)
        index = self._language.findData(self._target_language.value)
        if index >= 0:
            self._language.setCurrentIndex(index)
        self._language.currentIndexChanged.connect(self._on_language_changed)

        self._toggle = QPushButton("Turn subtitles on")
        self._toggle.setObjectName("toggle")
        self._toggle.setCheckable(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle_clicked)

        self._status = QLabel("Status: Idle — overlay hidden")
        self._status.setObjectName("status")
        self._status.setWordWrap(True)

        quit_btn = QPushButton("Quit GrammAI")
        quit_btn.setObjectName("secondary")
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.clicked.connect(self.quit_app)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(4)
        layout.addWidget(lang_label)
        layout.addWidget(self._language)
        layout.addWidget(self._toggle)
        layout.addWidget(self._status)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(quit_btn)
        layout.addLayout(bottom)

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(_tray_icon(), self)
        tray.setToolTip("GrammAI")
        menu = QMenu()

        show_action = QAction("Show GrammAI", menu)
        show_action.triggered.connect(self.reveal)

        self._tray_toggle = QAction("Turn subtitles on", menu)
        self._tray_toggle.triggered.connect(self._toggle.click)

        quit_action = QAction("Quit GrammAI", menu)
        quit_action.triggered.connect(self.quit_app)

        menu.addAction(show_action)
        menu.addAction(self._tray_toggle)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.reveal()

    def reveal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def _on_toggle_clicked(self) -> None:
        self.set_subtitles_enabled(self._toggle.isChecked())

    @Slot()
    def _on_language_changed(self) -> None:
        value = self._language.currentData()
        self._target_language = TargetLanguage(value)
        if self._subtitles_on:
            self._stop_pipeline()
            self._start_pipeline()

    def set_subtitles_enabled(self, enabled: bool) -> None:
        if enabled == self._subtitles_on:
            self._sync_ui()
            return
        self._subtitles_on = enabled
        if enabled:
            self._overlay.reset_text()
            self._overlay.show()
            self._start_pipeline()
        else:
            self._stop_pipeline()
            self._overlay.hide()
        self._sync_ui()

    def _start_pipeline(self) -> None:
        self._stop_pipeline()
        worker = TranslationWorker(self._target_language)
        worker.subtitle_ready.connect(self._overlay.apply_subtitle)
        worker.status_changed.connect(self._on_pipeline_status)
        self._worker = worker
        worker.start()

    def _stop_pipeline(self) -> None:
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        worker.stop()
        worker.wait(2000)

    @Slot(str)
    def _on_pipeline_status(self, message: str) -> None:
        if not self._subtitles_on:
            return
        self._status.setText(f"Status: {message}")

    def _sync_ui(self) -> None:
        on = self._subtitles_on
        self._toggle.blockSignals(True)
        self._toggle.setChecked(on)
        self._toggle.blockSignals(False)
        self._toggle.setText("Turn subtitles off" if on else "Turn subtitles on")
        self._toggle.setProperty("active", "true" if on else "false")
        self._toggle.style().unpolish(self._toggle)
        self._toggle.style().polish(self._toggle)
        self._tray_toggle.setText("Turn subtitles off" if on else "Turn subtitles on")
        if on:
            self._status.setText("Status: Overlay on — mock pipeline running")
            self._tray.setToolTip("GrammAI — subtitles on")
        else:
            self._status.setText("Status: Idle — overlay hidden")
            self._tray.setToolTip("GrammAI — subtitles off")

    def quit_app(self) -> None:
        self._quitting = True
        self._stop_pipeline()
        self._overlay.close()
        self._tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._quitting or not self._tray.isVisible():
            self._stop_pipeline()
            self._overlay.close()
            event.accept()
            return
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "GrammAI is still running",
            "The control panel is in the tray. Subtitles stay on if you left them on.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )


def _tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("#1A1A1A"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#FFFFFF"))
    painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()
    return QIcon(pixmap)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GrammAI subtitle overlay MVP")
    parser.add_argument(
        "--target",
        choices=[lang.value for lang in TargetLanguage],
        default=TargetLanguage.CHINESE.value,
        help="Target subtitle language (default: zh).",
    )
    parser.add_argument(
        "--start-on",
        action="store_true",
        help="Start with the subtitle overlay already visible.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    target = TargetLanguage(args.target)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("GrammAI")

    panel = ControlPanel(target)
    panel.show()
    if args.start_on:
        panel.set_subtitles_enabled(True)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
