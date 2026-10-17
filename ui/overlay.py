"""Frameless, always-on-top, click-through subtitle overlay with a live HUD."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.config import LANGUAGE_HUD, AppConfig
from core.events import AppState, EventBus, SubtitleUpdate
from ui.components import AudioMeterWidget, SubtitleStack


def _device_hud(kind: str, name: str) -> str:
    icon = "🎧" if kind == "loopback" else "🎤"
    short = name.strip() or ("Desktop Audio" if kind == "loopback" else "Microphone")
    if len(short) > 36:
        short = short[:33] + "…"
    return f"{icon} {short}"


def _route_hud(source: str, target: str) -> str:
    left = LANGUAGE_HUD.get(source, f"🌐 {source}")
    right = LANGUAGE_HUD.get(target, target)
    return f"{left}  ➔  {right}"


class OverlayHUD(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.device = QLabel("🎧 Desktop Audio")
        self.route = QLabel(_route_hud("auto", "zh"))
        self.meter = AudioMeterWidget(self)

        for label in (self.device, self.route):
            label.setStyleSheet("background: transparent; color: #C8C8C8;")
            label.setFont(QFont("Segoe UI", 10))

        self.device.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.route.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.route.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self.device, 0)
        row.addWidget(self.route, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 8, 28, 0)
        layout.setSpacing(6)
        layout.addLayout(row)
        layout.addWidget(self.meter)

    def apply_state(self, state: AppState) -> None:
        self.device.setText(_device_hud(state.device_kind, state.device_name))
        self.route.setText(_route_hud(state.source_language, state.target_language))
        self.meter.set_threshold(int(round(state.noise_threshold * 100)))


class SubtitleOverlay(QWidget):
    def __init__(self, events: EventBus, config: AppConfig) -> None:
        super().__init__(None)
        self._config = config
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._hud = OverlayHUD(self)
        self._stack = SubtitleStack(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._hud)
        layout.addWidget(self._stack)
        self._place_at_bottom()

        events.audio_level_changed.connect(self._on_audio_level)
        events.state_changed.connect(self.apply_state)
        self.apply_state(config.snapshot())

    def _place_at_bottom(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 210)
            return
        geo = screen.availableGeometry()
        width = int(geo.width() * 0.72)
        height = min(geo.height() - 64, max(210, self.layout().heightForWidth(width)))
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + 24 if self._config.overlay_position == "top" else geo.y() + geo.height() - height - 48
        self.setGeometry(x, y, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, self._config.overlay_opacity))
        painter.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 12, 12)
        super().paintEvent(event)

    @Slot(float)
    def _on_audio_level(self, level: float) -> None:
        self._hud.meter.update_volume(int(round(max(0.0, min(1.0, float(level))) * 100)))

    @Slot(object)
    def apply_subtitle(self, update: SubtitleUpdate) -> None:
        self._stack.apply(update)
        if not self._config.show_pronunciation:
            self._stack.phonetics.hide()
            self._stack.native_phonetics.hide()
        QTimer.singleShot(0, self, self._place_at_bottom)

    @Slot(object)
    def apply_state(self, state: AppState) -> None:
        self._hud.apply_state(state)
        self._stack.target.setFont(QFont("Microsoft YaHei", self._config.subtitle_font_size, QFont.Weight.DemiBold))
        self._stack.phonetics.setVisible(self._config.show_pronunciation and bool(self._stack.phonetics.text()))
        self._stack.native_phonetics.setVisible(self._config.show_pronunciation and bool(self._stack.native_phonetics.text()))
        self._place_at_bottom()
        self.update()

    def reset_text(self) -> None:
        self._stack.reset()
