"""Frameless, always-on-top, click-through subtitle overlay with a live HUD."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

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

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0,0,0,150))
        painter.drawRoundedRect(self.rect(),12,12)

    def apply_state(self, state: AppState) -> None:
        self.device.setText(_device_hud(state.device_kind, state.device_name))
        self.route.setText(_route_hud(state.source_language, state.target_language) if state.translation_enabled else f"{LANGUAGE_HUD.get(state.source_language, state.source_language)} -> Transcript only")
        self.meter.set_threshold(int(round(state.noise_threshold * 100)))


class SubtitleOverlay(QWidget):
    def __init__(self, events: EventBus, config: AppConfig, parent=None, preview=False) -> None:
        super().__init__(parent)
        self._config = config
        self._preview=preview
        self._preview_config=None
        if not preview:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._hud = OverlayHUD(self)
        self._hud_effect=QGraphicsOpacityEffect(self._hud)
        self._hud.setGraphicsEffect(self._hud_effect)
        self._stack = SubtitleStack(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._hud,0,Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._stack,0,Qt.AlignmentFlag.AlignHCenter)
        self._place_at_bottom()

        events.audio_level_changed.connect(self._on_audio_level)
        events.state_changed.connect(self.apply_state)
        events.overlay_appearance_preview.connect(self.preview_appearance)
        self.apply_state(config.snapshot())

    @property
    def appearance(self):
        return self._preview_config or self._config

    def fit_content(self,max_width,max_height=10000):
        config=self.appearance
        max_width=max(120,int(max_width)-16)
        labels=(self._stack.target,self._stack.phonetics,self._stack.native,self._stack.native_phonetics)
        text_width=max((max((label.fontMetrics().horizontalAdvance(line) for line in label.text().splitlines()),default=0)
            +label.margin()*2 for label in labels if not label.isHidden()),default=180)
        width=min(max_width,max(180,text_width+2*config.overlay_padding+8))
        self._stack.setFixedWidth(width)
        if not self._hud.isHidden():
            hud_width=min(max_width,max(width,self._hud.minimumSizeHint().width()))
            self._hud.setFixedWidth(hud_width)
            width=max(width,hud_width)
        height=max(1,self.layout().heightForWidth(width+16))
        return width+16,min(max_height,height)

    def _place_at_bottom(self) -> None:
        if self._preview:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 210)
            return
        geo = screen.availableGeometry()
        width,height=self.fit_content(geo.width()*self.appearance.overlay_max_width/100,geo.height()-72)
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + 24 if self.appearance.overlay_position == "top" else geo.y() + geo.height() - height - 48
        self.setGeometry(x, y, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, self.appearance.overlay_opacity))
        painter.drawRoundedRect(self._stack.geometry(), self.appearance.overlay_corner_radius, self.appearance.overlay_corner_radius)
        super().paintEvent(event)

    @Slot(float)
    def _on_audio_level(self, level: float) -> None:
        self._hud.meter.update_volume(int(round(max(0.0, min(1.0, float(level))) * 100)))

    @Slot(object)
    def apply_subtitle(self, update: SubtitleUpdate) -> None:
        self._stack.apply(update)
        self._apply_appearance()
        QTimer.singleShot(0, self, self._place_at_bottom)

    @Slot(object)
    def apply_state(self, state: AppState) -> None:
        self._hud.apply_state(state)
        self._apply_appearance()

    def _apply_appearance(self):
        config=self.appearance
        for label,family,size,color in (
            (self._stack.target,'Microsoft YaHei',config.subtitle_font_size,'#ffffff'),
            (self._stack.phonetics,'Segoe UI',max(11,round(config.subtitle_font_size*.5)),'#d0d0d0'),
            (self._stack.native,'Segoe UI',max(12,round(config.subtitle_font_size*.6)),'#e8e8e8'),
            (self._stack.native_phonetics,'Segoe UI',max(10,round(config.subtitle_font_size*.43)),'#a8a8a8'),
        ):
            weight=QFont.Weight.DemiBold if label is self._stack.target else QFont.Weight.Normal
            label.setFont(QFont(family,size,weight))
            style=f"background: transparent; color: {color}; font-family: '{family}'; font-size: {size}pt; font-weight: {600 if label is self._stack.target else 400};"
            if label.styleSheet()!=style:
                label.setStyleSheet(style)
        self._stack.phonetics.setVisible(config.show_pronunciation and bool(self._stack.phonetics.text()))
        self._stack.native_phonetics.setVisible(config.overlay_show_original and config.show_pronunciation and bool(self._stack.native_phonetics.text()))
        self._stack.native.setVisible(config.overlay_show_original and bool(self._stack.native.text()) and self._stack.native.text()!=self._stack.target.text())
        for label in (self._stack.target,self._stack.phonetics,self._stack.native,self._stack.native_phonetics):
            label.set_readability(config.overlay_text_outline,config.overlay_text_shadow)
        padding=config.overlay_padding
        self._stack.layout().setContentsMargins(padding+4,padding,padding+4,padding)
        self._hud.setVisible(config.overlay_show_hud and config.overlay_hud_opacity>0)
        self._hud_effect.setOpacity(config.overlay_hud_opacity/100)
        self._place_at_bottom()
        self.update()

    @Slot(object)
    def preview_appearance(self,config):
        self._preview_config=config
        self._apply_appearance()

    def reset_text(self) -> None:
        self._stack.reset()
        self._apply_appearance()
