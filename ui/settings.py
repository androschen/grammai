"""Organized settings with explicit model changes and live noise-gate preview."""
from dataclasses import fields, replace
from pathlib import Path
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)
from audio.capture import list_audio_sources
from core.config import AppConfig, TargetLanguage, QualityMode, LANGUAGE_LABELS, SOURCE_LANGUAGE_LABELS, QUALITY_LABELS
from core.events import EventBus
from ui.components import NoiseGateEditor
from ui.performance import LivePerformance, BenchmarkResults
from ui.theme import style_for


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, events: EventBus, parent=None, page=0):
        super().__init__(parent)
        self._config, self._events = config, events
        self._revert_threshold = config.noise_threshold
        self._sources = []
        self.setWindowTitle('GrammAI - Settings')
        self.setStyleSheet(style_for(config.theme))
        self.resize(740, 700)
        self.setMinimumSize(640, 520)
        layout = QVBoxLayout(self)
        title = QLabel('Settings')
        title.setObjectName('title')
        layout.addWidget(title)
        subtitle=QLabel('A little tuning. A better listening experience.')
        subtitle.setObjectName('hint')
        layout.addWidget(subtitle)
        layout.setContentsMargins(24,24,24,24)
        layout.setSpacing(14)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._audio_page()
        self._language_page()
        self._appearance_page()
        self._performance_page()
        self.tabs.setCurrentIndex(page)
        self._feedback = QLabel('Model and device changes take effect when you select Apply. Noise filtering previews live.')
        self._feedback.setObjectName('hint')
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self._load_values()
        events.audio_level_changed.connect(self._on_audio_level)
        events.benchmark_finished.connect(self.results.show_result)
        events.benchmark_progress.connect(self._benchmark_progress)
        events.benchmark_busy.connect(self._benchmark_busy)
        self._benchmark_busy(bool(events.property("benchmark_busy")))

    def _page(self, title):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, title)
        return layout

    def _audio_page(self):
        layout = self._page('Audio')
        self._device = QComboBox()
        self._device.addItem('Desktop audio (system default)', '')
        try:
            self._sources = list_audio_sources()
        except Exception:
            pass
        for source in self._sources:
            self._device.addItem(('Desktop: ' if source.kind == 'loopback' else 'Microphone: ') + source.name, source.device_id)
        form = QFormLayout()
        form.addRow('Listen to', self._device)
        layout.addLayout(form)
        self._gate = NoiseGateEditor(self, round(self._config.noise_threshold * 100))
        self._gate.threshold_changed.connect(self._preview_gate)
        layout.addWidget(self._gate)
        layout.addStretch()

    def _language_page(self):
        layout = self._page('Languages')
        self._source, self._target = QComboBox(), QComboBox()
        for code, name in SOURCE_LANGUAGE_LABELS.items():
            self._source.addItem(name, code)
        for code, name in LANGUAGE_LABELS.items():
            self._target.addItem(name, code.value)
        self._pronunciation = QCheckBox('Show Chinese pinyin and Thai pronunciation on the overlay')
        form = QFormLayout()
        form.addRow('Spoken language', self._source)
        form.addRow('Translate into', self._target)
        layout.addLayout(form)
        layout.addWidget(self._pronunciation)
        hint = QLabel('Choose the spoken language when you know it. Auto-detect is useful when the language changes. History keeps pronunciation for later reading.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        layout.addWidget(hint)
        layout.addStretch()

    def _appearance_page(self):
        layout = self._page('Appearance')
        self._theme = QComboBox()
        self._theme.addItem('Dark','dark')
        self._theme.addItem('Light','light')
        self._font = QSpinBox()
        self._font.setRange(16,48)
        self._opacity = QSpinBox()
        self._opacity.setRange(40,240)
        self._position = QComboBox()
        self._position.addItem('Bottom of screen', 'bottom')
        self._position.addItem('Top of screen', 'top')
        self._show_overlay = QCheckBox('Show floating subtitles while translating')
        form = QFormLayout()
        form.addRow('App theme',self._theme)
        form.addRow('Subtitle font size',self._font)
        form.addRow('Background opacity (40-240)',self._opacity)
        form.addRow('Position',self._position)
        layout.addLayout(form)
        layout.addWidget(self._show_overlay)
        layout.addStretch()

    def _file_row(self, edit, executable=False):
        row = QHBoxLayout()
        row.addWidget(edit,1)
        button = QPushButton('Browse')
        def browse():
            path, _ = QFileDialog.getOpenFileName(self, 'Select whisper-server' if executable else 'Select GGML Whisper model', '', 'Executable (*.exe)' if executable else 'GGML model (*.bin)')
            if path:
                edit.setText(path)
        button.clicked.connect(browse)
        row.addWidget(button)
        return row

    def _performance_page(self):
        outer = self._page('Performance')
        subpages = QTabWidget()
        outer.addWidget(subpages)
        configuration = QWidget()
        layout = QVBoxLayout(configuration)
        subpages.addTab(configuration, 'Configuration')
        self._quality = QComboBox()
        for mode,label in QUALITY_LABELS.items():
            self._quality.addItem(label,mode.value)
        self._backend = QComboBox()
        self._backend.addItem('CPU - available', 'cpu')
        self._backend.addItem('Radeon / Vulkan - requires local server and model', 'vulkan')
        self._threads, self._mt_threads = QSpinBox(), QSpinBox()
        self._threads.setRange(1,16)
        self._mt_threads.setRange(1,8)
        self._exe, self._gpu_model = QLineEdit(), QLineEdit()
        self._exe.setPlaceholderText('Path to a Vulkan build of whisper-server.exe')
        self._gpu_model.setPlaceholderText('Path to a multilingual ggml-*.bin Whisper model')
        self._preset_help = QLabel()
        self._preset_help.setWordWrap(True)
        self._preset_help.setObjectName('hint')
        self._quality.currentIndexChanged.connect(self._describe_preset)
        form = QFormLayout()
        form.addRow('Quality preset',self._quality)
        form.addRow('Speech recognition backend',self._backend)
        form.addRow('Speech CPU threads',self._threads)
        form.addRow('Translation CPU threads',self._mt_threads)
        self._gpu_setup = QWidget()
        gpu_form = QFormLayout(self._gpu_setup)
        gpu_form.setContentsMargins(0,0,0,0)
        gpu_form.addRow('Vulkan server',self._file_row(self._exe,True))
        gpu_form.addRow('Vulkan speech model',self._file_row(self._gpu_model))
        form.addRow(self._gpu_setup)
        self._backend.currentIndexChanged.connect(self._backend_visibility)
        self._exe.textChanged.connect(self._backend_visibility)
        self._gpu_model.textChanged.connect(self._backend_visibility)
        layout.addLayout(form)
        layout.addWidget(self._preset_help)
        hint = QLabel('GPU mode keeps the server loaded and verifies Vulkan allocation at startup. Translation uses CPU. With Vulkan, the selected GGML file determines model size; presets control decoding effort. GPU utilization and VRAM monitoring are unavailable.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.addWidget(LivePerformance(self._events))
        explanation = QLabel('Live readings update once per second. Stage timings describe the last completed speech segment and exclude audio collection and queue wait. CPU includes app child processes and is normalized to total machine capacity.')
        explanation.setWordWrap(True)
        explanation.setObjectName('hint')
        monitor_layout.addWidget(explanation)
        monitor_layout.addStretch()
        subpages.addTab(monitor, 'Live monitor')
        comparison = QWidget()
        layout = QVBoxLayout(comparison)
        subpages.addTab(comparison, 'Compare')
        self.benchmark = QPushButton('Run benchmark with selected settings')
        self.benchmark.clicked.connect(self._run_benchmark)
        layout.addWidget(self.benchmark)
        self._bench_status = QLabel('Measures model loading separately, then three warmed runs. Live translation pauses during the test.')
        self._bench_status.setObjectName('hint')
        self._bench_status.setWordWrap(True)
        layout.addWidget(self._bench_status)
        self.results = BenchmarkResults()
        layout.addWidget(self.results,1)
        self._retry = QPushButton('Retry model loading')
        self._retry.clicked.connect(self._events.retry_requested.emit)
        layout.addWidget(self._retry)

    def _load_values(self):
        c = self._config
        for widget,value in ((self._device,c.audio_device_id),(self._source,c.source_language),
            (self._target,c.target_language.value),(self._quality,c.quality_mode.value),
            (self._backend,c.backend),(self._position,c.overlay_position)):
            widget.setCurrentIndex(max(0,widget.findData(value)))
        self._threads.setValue(c.cpu_threads)
        self._mt_threads.setValue(c.translation_threads)
        self._theme.setCurrentIndex(max(0,self._theme.findData(c.theme)))
        self._font.setValue(c.subtitle_font_size)
        self._opacity.setValue(c.overlay_opacity)
        self._exe.setText(c.vulkan_executable)
        self._gpu_model.setText(c.vulkan_model)
        self._pronunciation.setChecked(c.show_pronunciation)
        self._show_overlay.setChecked(c.show_overlay)
        self._describe_preset()
        self._backend_visibility()

    def _backend_visibility(self):
        self._gpu_setup.setVisible(self._backend.currentData() == "vulkan")
        ready = Path(self._exe.text()).is_file() and Path(self._gpu_model.text()).is_file()
        self._backend.setItemText(1, "Radeon / Vulkan - verify on Start" if ready else "Radeon / Vulkan - setup required")

    def _describe_preset(self):
        descriptions = {'fast': 'Low resource: base speech model, minimal decoding effort. Lower CPU demand; may reduce accuracy.',
            'balanced': 'Balanced: base speech model with moderate decoding effort. A useful starting point for watching videos.',
            'accurate': 'Best quality: small speech model and deeper decoding. Uses more processing time.'}
        self._preset_help.setText(descriptions.get(self._quality.currentData(),''))

    def _draft(self):
        c = replace(self._config)
        c.audio_device_id = self._device.currentData() or ''
        source = next((s for s in self._sources if s.device_id == c.audio_device_id),None)
        c.audio_device_name = source.name if source else 'Desktop audio (default)'
        c.audio_device_kind = source.kind if source else 'loopback'
        c.source_language = self._source.currentData()
        c.target_language = TargetLanguage(self._target.currentData())
        c.quality_mode = QualityMode(self._quality.currentData())
        c.apply_quality()
        c.backend = self._backend.currentData()
        c.cpu_threads, c.translation_threads = self._threads.value(),self._mt_threads.value()
        c.vulkan_executable,c.vulkan_model = self._exe.text().strip(),self._gpu_model.text().strip()
        c.theme = self._theme.currentData()
        c.subtitle_font_size,c.overlay_opacity = self._font.value(),self._opacity.value()
        c.overlay_position = self._position.currentData()
        c.show_overlay,c.show_pronunciation = self._show_overlay.isChecked(),self._pronunciation.isChecked()
        if c.backend == 'vulkan' and (not Path(c.vulkan_executable).is_file() or not Path(c.vulkan_model).is_file()):
            raise ValueError('Select an existing Vulkan whisper-server executable and GGML model first, or choose CPU.')
        return c

    def apply(self):
        try:
            c = self._draft()
        except ValueError as exc:
            self._feedback.setText(str(exc))
            self.tabs.setCurrentIndex(3)
            return False
        for field in fields(c):
            setattr(self._config,field.name,getattr(c,field.name))
        self.setStyleSheet(style_for(c.theme))
        self._revert_threshold = c.noise_threshold
        self._events.state_changed.emit(c.snapshot())
        self._events.overlay_toggled.emit(c.show_overlay)
        self._feedback.setText('Applied. Preferences are saved automatically.')
        return True

    def accept(self):
        if self.apply():
            super().accept()

    def reject(self):
        self._config.noise_threshold = self._revert_threshold
        self._events.state_changed.emit(self._config.snapshot())
        super().reject()

    @Slot(float)
    def _on_audio_level(self, level):
        self._gate.update_volume(round(max(0,min(1,level))*100))

    def _preview_gate(self, percent):
        self._config.noise_threshold = percent/100
        self._events.state_changed.emit(self._config.snapshot())

    def _run_benchmark(self):
        try:
            self._events.benchmark_requested.emit(self._draft())
        except ValueError as exc:
            self._bench_status.setText(str(exc))

    @Slot(str)
    def _benchmark_progress(self,message):
        self._bench_status.setText(message)

    @Slot(bool)
    def _benchmark_busy(self,busy):
        self.benchmark.setEnabled(not busy)
        self.benchmark.setText('Benchmark running...' if busy else 'Run benchmark with selected settings')
        if not busy:
            self._bench_status.setText('Finished. Results are separate from live-session measurements.')

    def done(self,result):
        for signal,slot in ((self._events.audio_level_changed,self._on_audio_level),
            (self._events.benchmark_progress,self._benchmark_progress),
            (self._events.benchmark_busy,self._benchmark_busy),
            (self._events.benchmark_finished,self.results.show_result)):
            try:
                signal.disconnect(slot)
            except (TypeError,RuntimeError):
                pass
        super().done(result)
