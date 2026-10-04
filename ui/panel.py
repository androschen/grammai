"""Desktop control panel that turns the overlay pipeline on and off."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont, QIcon, QPainter, QPixmap
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

from core.config import LANGUAGE_LABELS, AppConfig, TargetLanguage
from core.events import AppState, EventBus
from ui.components import AudioMeterWidget
from ui.settings import SettingsDialog

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


def _tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("#1A1A1A"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#FFFFFF"))
    painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()
    return QIcon(pixmap)


class ControlPanel(QWidget):
    def __init__(self, config: AppConfig, events: EventBus) -> None:
        super().__init__(None)
        self._config = config
        self._events = events
        self._quitting = False

        self.setWindowTitle("GrammAI")
        self.setFixedSize(420, 360)
        self.setStyleSheet(_PANEL_STYLE)

        self._build_ui()
        self._tray = self._build_tray()
        self.set_subtitles_on(False)

        events.status_changed.connect(self.set_status)
        events.pipeline_error.connect(self.set_status)
        events.audio_level_changed.connect(self._on_audio_level)
        events.state_changed.connect(self._on_app_state)

    def _build_ui(self) -> None:
        title = QLabel("GrammAI")
        title.setObjectName("title")

        hint = QLabel(
            "The meter shows live system audio. Click it to set the noise gate "
            "in Settings. Turn subtitles on for the overlay."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        lang_label = QLabel("Target language")
        lang_label.setObjectName("field")

        self._language = QComboBox()
        for lang, label in LANGUAGE_LABELS.items():
            self._language.addItem(label, lang.value)
        index = self._language.findData(self._config.target_language.value)
        if index >= 0:
            self._language.setCurrentIndex(index)
        self._language.currentIndexChanged.connect(self._on_language_changed)

        meter_label = QLabel("Input level / noise gate")
        meter_label.setObjectName("field")
        self._meter = AudioMeterWidget(self)
        self._meter.clicked.connect(self._open_settings)

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
        quit_btn.clicked.connect(self._events.quit_requested.emit)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("secondary")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(4)
        layout.addWidget(lang_label)
        layout.addWidget(self._language)
        layout.addWidget(meter_label)
        layout.addWidget(self._meter)
        layout.addWidget(self._toggle)
        layout.addWidget(self._status)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addWidget(settings_btn)
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
        quit_action.triggered.connect(self._events.quit_requested.emit)

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
        self._events.subtitles_toggled.emit(self._toggle.isChecked())

    @Slot()
    def _on_language_changed(self) -> None:
        value = str(self._language.currentData())
        self._config.target_language = TargetLanguage(value)
        self._events.target_language_changed.emit(value)
        self._events.state_changed.emit(self._config.snapshot())

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, self._events, self)
        dialog.exec()
        target_index = self._language.findData(self._config.target_language.value)
        if target_index >= 0:
            self._language.blockSignals(True)
            self._language.setCurrentIndex(target_index)
            self._language.blockSignals(False)

    @Slot(float)
    def _on_audio_level(self, level: float) -> None:
        self._meter.update_volume(int(round(max(0.0, min(1.0, float(level))) * 100)))

    @Slot(object)
    def _on_app_state(self, state: AppState) -> None:
        self._meter.set_threshold(int(round(state.noise_threshold * 100)))

    def set_subtitles_on(self, enabled: bool) -> None:
        self._toggle.blockSignals(True)
        self._toggle.setChecked(enabled)
        self._toggle.blockSignals(False)
        self._toggle.setText("Turn subtitles off" if enabled else "Turn subtitles on")
        self._toggle.setProperty("active", "true" if enabled else "false")
        self._toggle.style().unpolish(self._toggle)
        self._toggle.style().polish(self._toggle)
        self._tray_toggle.setText("Turn subtitles off" if enabled else "Turn subtitles on")
        self._tray.setToolTip("GrammAI — subtitles on" if enabled else "GrammAI — subtitles off")

    @Slot(str)
    def set_status(self, message: str) -> None:
        text = message if message.lower().startswith("status") else f"Status: {message}"
        self._status.setText(text)

    def mark_quitting(self) -> None:
        self._quitting = True
        self._tray.hide()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._quitting or not self._tray.isVisible():
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


def quit_application() -> None:
    app = QApplication.instance()
    if app is not None:
        app.quit()
