"""Advanced settings: device, language routing, and live noise gate."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from audio.capture import AudioSource, list_audio_sources
from core.config import LANGUAGE_LABELS, SOURCE_LANGUAGE_LABELS, AppConfig, TargetLanguage
from core.events import EventBus
from ui.components import NoiseGateEditor


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, events: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._events = events
        self._sources: list[AudioSource] = []
        self._revert = replace(config)
        self._device_before = config.audio_device_id

        self.setWindowTitle("GrammAI settings")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(
            """
            QDialog { background: #161616; color: #E8E8E8; }
            QLabel { color: #E8E8E8; }
            QLabel#hint { color: #B0B0B0; font-size: 12px; }
            QLabel#field { color: #E8E8E8; font-size: 13px; }
            QComboBox { color: #FFFFFF; }
            QComboBox {
                background: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton {
                background: #2A2A2A;
                color: #E8E8E8;
                border: 1px solid #3A3A3A;
                border-radius: 8px;
                padding: 6px 12px;
            }
            QPushButton:checked {
                background: #1F6FEB;
                color: #FFFFFF;
                border-color: #1F6FEB;
            }
            QPushButton:hover { background: #333333; }
            """
        )
        self._build_ui()
        self._load_devices()
        self._sync_from_config()

        events.audio_level_changed.connect(self._on_audio_level)

    def _build_ui(self) -> None:
        self._device = QComboBox()
        self._source = QComboBox()
        self._target = QComboBox()
        self._gate = NoiseGateEditor(self, threshold=int(round(self._config.noise_threshold * 100)))

        for code, label in SOURCE_LANGUAGE_LABELS.items():
            self._source.addItem(label, code)
        for lang, label in LANGUAGE_LABELS.items():
            self._target.addItem(label, lang.value)

        self._device.currentIndexChanged.connect(self._emit_live_state)
        self._source.currentIndexChanged.connect(self._emit_live_state)
        self._target.currentIndexChanged.connect(self._emit_live_state)
        self._gate.threshold_changed.connect(self._on_gate_changed)

        form = QFormLayout()
        form.addRow("Audio input", self._device)
        form.addRow("Source language", self._source)
        form.addRow("Target language", self._target)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addLayout(form)
        layout.addWidget(self._gate)
        layout.addWidget(buttons)

    def _load_devices(self) -> None:
        self._device.blockSignals(True)
        self._device.clear()
        try:
            self._sources = list_audio_sources()
        except Exception:
            self._sources = []
        if not self._sources:
            self._device.addItem("🎧 Desktop Audio (default)", "")
        for source in self._sources:
            icon = "🎧" if source.kind == "loopback" else "🎤"
            self._device.addItem(f"{icon} {source.name}", source.device_id)
        self._device.blockSignals(False)

    def _sync_from_config(self) -> None:
        self._device.blockSignals(True)
        self._source.blockSignals(True)
        self._target.blockSignals(True)

        index = self._device.findData(self._config.audio_device_id)
        if index >= 0:
            self._device.setCurrentIndex(index)
        source_index = self._source.findData(self._config.source_language)
        if source_index >= 0:
            self._source.setCurrentIndex(source_index)
        target_index = self._target.findData(self._config.target_language.value)
        if target_index >= 0:
            self._target.setCurrentIndex(target_index)
        self._gate.set_threshold(int(round(self._config.noise_threshold * 100)))

        self._device.blockSignals(False)
        self._source.blockSignals(False)
        self._target.blockSignals(False)

    @Slot(float)
    def _on_audio_level(self, level: float) -> None:
        self._gate.update_volume(int(round(max(0.0, min(1.0, float(level))) * 100)))

    @Slot(int)
    def _on_gate_changed(self, percent: int) -> None:
        self._config.noise_threshold = percent / 100.0
        self._events.state_changed.emit(self._config.snapshot())

    def _selected_source(self) -> AudioSource | None:
        device_id = str(self._device.currentData() or "")
        for source in self._sources:
            if source.device_id == device_id:
                return source
        return None

    def _apply_to_config(self) -> None:
        source = self._selected_source()
        if source is not None:
            self._config.audio_device_id = source.device_id
            self._config.audio_device_name = source.name
            self._config.audio_device_kind = source.kind
        self._config.source_language = str(self._source.currentData())
        self._config.target_language = TargetLanguage(str(self._target.currentData()))
        self._config.noise_threshold = self._gate.meter.threshold / 100.0

    def _emit_live_state(self) -> None:
        self._apply_to_config()
        self._events.state_changed.emit(self._config.snapshot())
        self._events.target_language_changed.emit(self._config.target_language.value)

    def accept(self) -> None:
        self._apply_to_config()
        self._events.state_changed.emit(self._config.snapshot())
        self._events.target_language_changed.emit(self._config.target_language.value)
        super().accept()

    def reject(self) -> None:
        self._config.audio_device_id = self._revert.audio_device_id
        self._config.audio_device_name = self._revert.audio_device_name
        self._config.audio_device_kind = self._revert.audio_device_kind
        self._config.source_language = self._revert.source_language
        self._config.target_language = self._revert.target_language
        self._config.noise_threshold = self._revert.noise_threshold
        self._events.state_changed.emit(self._config.snapshot())
        self._events.target_language_changed.emit(self._config.target_language.value)
        super().reject()

    def done(self, result: int) -> None:  # noqa: N802
        try:
            self._events.audio_level_changed.disconnect(self._on_audio_level)
        except (TypeError, RuntimeError):
            pass
        super().done(result)

    def device_changed(self) -> bool:
        return self._config.audio_device_id != self._device_before
