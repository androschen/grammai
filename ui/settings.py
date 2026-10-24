"""Organized settings with explicit model changes and live noise-gate preview."""
from dataclasses import fields, replace
from pathlib import Path
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QDoubleSpinBox, QTabWidget, QVBoxLayout, QWidget, QListWidget)
from audio.capture import list_audio_sources
from core.config import AppConfig, TargetLanguage, QualityMode, LANGUAGE_LABELS, SOURCE_LANGUAGE_LABELS, QUALITY_LABELS
from core.events import EventBus
from ui.components import NoiseGateEditor
from ui.performance import LivePerformance, BenchmarkResults
from ui.theme import style_for


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, events: EventBus, parent=None, page=0, replays=None):
        super().__init__(parent)
        self._config, self._events = config, events
        self._revert_threshold = config.noise_threshold
        self._sources = []
        self.setWindowTitle('GrammAI - Settings')
        self.setStyleSheet(style_for(config.theme))
        self.resize(800, 740)
        self.setMinimumSize(640, 520)
        layout = QVBoxLayout(self)
        title = QLabel('Settings')
        title.setObjectName('title')
        layout.addWidget(title)
        subtitle=QLabel('A little tuning. A better listening experience.')
        subtitle.setObjectName('hint')
        subtitle.hide()
        layout.setContentsMargins(14,14,14,14)
        layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.categories=QListWidget();self.categories.setObjectName('settingsNavigation');self.categories.setFixedWidth(140);self.categories.setAccessibleName('Settings categories')
        workspace=QHBoxLayout();workspace.setSpacing(12);workspace.addWidget(self.categories);workspace.addWidget(self.tabs,1);layout.addLayout(workspace,1)
        self.tabs.tabBar().hide()
        self._audio_page()
        self._language_page()
        self._appearance_page()
        self._performance_page()
        from ui.storage import StorageWidget
        storage_layout=self._page("Storage")
        self.storage=StorageWidget(config,events,replays)
        storage_layout.addWidget(self.storage)
        self.tabs.currentChanged.connect(lambda index:self.storage.set_active(index==4))
        self.tabs.setCurrentIndex(page)
        self._analysis_page()
        for index in range(self.tabs.count()):self.categories.addItem(self.tabs.tabText(index))
        self.categories.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.categories.setCurrentRow)
        self.tabs.setCurrentIndex(page);self.categories.setCurrentRow(self.tabs.currentIndex())
        self._feedback = QLabel('Model and device changes take effect when you select Apply. Noise filtering previews live.')
        self._feedback.setObjectName('hint')
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)
        if self.analysis_settings.service:
            self.analysis_settings.service.status_changed.connect(self._analysis_status)
            self.analysis_settings.service.progress_changed.connect(self._analysis_progress)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self._load_values()
        events.metrics_changed.connect(self._model_metrics)
        history=events.property("resource_history") or ()
        if history:self._model_metrics(history[-1][1])
        events.audio_level_changed.connect(self._on_audio_level)
        events.benchmark_finished.connect(self.results.show_result)
        events.benchmark_progress.connect(self._benchmark_progress)
        events.benchmark_busy.connect(self._benchmark_busy)
        self._benchmark_busy(bool(events.property("benchmark_busy")))

    def _page(self, title):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(8)
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
        self._speech_detection=QCheckBox('Use speech-aware boundaries (recommended)')
        self._speech_detection.setChecked(self._config.speech_detection)
        layout.addWidget(self._speech_detection)
        timing=QFormLayout()
        self._speech_max=QDoubleSpinBox()
        self._speech_max.setRange(2,8)
        self._speech_max.setSingleStep(.4)
        self._speech_max.setValue(self._config.speech_max_seconds)
        self._speech_max.setSuffix(' s')
        self._speech_silence=QDoubleSpinBox()
        self._speech_silence.setRange(.24,1)
        self._speech_silence.setSingleStep(.04)
        self._speech_silence.setValue(self._config.speech_silence_seconds)
        self._speech_silence.setSuffix(' s')
        self._speech_overlap=QDoubleSpinBox()
        self._speech_overlap.setRange(0,.8)
        self._speech_overlap.setSingleStep(.08)
        self._speech_overlap.setValue(self._config.speech_overlap_seconds)
        self._speech_overlap.setSuffix(' s')
        timing.addRow('Speech segment target',self._speech_max)
        timing.addRow('Pause before final subtitle',self._speech_silence)
        timing.addRow('Overlap at continuous-speech cuts',self._speech_overlap)
        timing_host=QWidget();timing_layout=QVBoxLayout(timing_host);timing_layout.setContentsMargins(0,0,0,0);timing_layout.addLayout(timing)
        timing_toggle=QPushButton('Advanced timing');timing_toggle.setCheckable(True);timing_toggle.toggled.connect(timing_host.setVisible);layout.addWidget(timing_toggle);layout.addWidget(timing_host);timing_host.hide()
        hint=QLabel('The noise threshold controls when speech starts. Speech detection preserves quieter syllables afterward. Shorter pauses reduce delay; very short segments can reduce recognition accuracy. Speech-aware targets of 4 seconds or more allow up to 0.8 seconds of extra endpoint buffering.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        timing_layout.addWidget(hint)
        layout.addStretch()

    def _language_page(self):
        layout = self._page('Translation')
        self._source, self._target = QComboBox(), QComboBox()
        for code, name in SOURCE_LANGUAGE_LABELS.items():
            self._source.addItem(name, code)
        for code, name in LANGUAGE_LABELS.items():
            self._target.addItem(name, code.value)
        self._translation = QCheckBox("Translate speech")
        self._pronunciation = QCheckBox('Show Chinese pinyin and Thai pronunciation on the overlay')
        form = QFormLayout()
        form.addRow('Spoken language', self._source)
        form.addRow('Translate into', self._target)
        self._translation_mode=QComboBox()
        for title,code in (('Fast - NLLB on CPU','fast'),('Context-aware - local Qwen on GPU','context'),('Fast + review - automatic AI refinement','review')):
            self._translation_mode.addItem(title,code)
        self._translation_mode.setCurrentIndex(max(0,self._translation_mode.findData(self._config.translation_mode)))
        # The model choice is placed on Models after the language page is built.
        layout.addLayout(form)
        mode_hint=QLabel();self._mode_hint=mode_hint;mode_hint.setWordWrap(True);mode_hint.setObjectName('hint')
        descriptions={'fast':'Immediate NLLB translation. Lowest model overhead.',
            'context':'Qwen translates using up to three earlier original sentences. Uses your GPU; falls back to NLLB if unavailable. Stop live subtitles before manual local analysis.',
            'review':'NLLB subtitles appear immediately. Qwen reviews completed original sentences in the background. Refinements update automatically; open sentence details to compare versions. Transcripts are never changed automatically.'}
        self._translation_mode.currentIndexChanged.connect(lambda:mode_hint.setText(descriptions[self._translation_mode.currentData()]))
        mode_hint.setText(descriptions[self._translation_mode.currentData()]);layout.addWidget(mode_hint)
        layout.addWidget(self._translation)
        layout.addWidget(self._pronunciation)
        hint = QLabel('Choose the spoken language when you know it. Auto-detect is useful when the language changes. History keeps pronunciation for later reading.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        layout.addWidget(hint)
        self._speech_prompt=QLineEdit(self._config.speech_prompt)
        self._speech_prompt.setMaxLength(300)
        self._speech_prompt.setPlaceholderText('Optional names, terminology, or desired written form; up to 300 characters')
        layout.addWidget(QLabel('Speech-recognition vocabulary hint'))
        layout.addWidget(self._speech_prompt)
        translator=QLabel('Speech recognition is separate from translation. Qwen modes reuse your local model; there are no automatic downloads or online fallbacks. Model choices and runtime status: Models.')
        translator.setWordWrap(True);translator.setObjectName('hint');layout.addWidget(translator)
        self._compare_translators=QPushButton('Compare NLLB and local Qwen')
        self._compare_translators.clicked.connect(self._open_translation_comparison)
        advanced=QPushButton('Advanced: compare translation engines');advanced.setCheckable(True)
        self._compare_translators.hide();advanced.toggled.connect(self._compare_translators.setVisible)
        layout.addWidget(advanced);layout.addWidget(self._compare_translators)
        layout.addStretch()

    def _open_translation_comparison(self):
        from ui.translation_compare import TranslationComparisonDialog
        dialog=TranslationComparisonDialog(self._config,self._events,self)
        dialog.exec()
        dialog.deleteLater()

    def _appearance_page(self):
        from ui.appearance import AppearanceEditor
        layout=self._page('Appearance')
        self.appearance=AppearanceEditor(self._config,self._events,self)
        layout.addWidget(self.appearance)
        self.appearance.pronunciation.toggled.connect(self._pronunciation.setChecked)
        self._pronunciation.toggled.connect(self.appearance.pronunciation.setChecked)
        self._theme=self.appearance.theme
        self._position=self.appearance.position
        self._show_overlay=self.appearance.show_overlay

    def _analysis_page(self):
        from ui.local_ai_settings import LocalAISettings
        layout=self._page('Understanding')
        self.analysis_settings=LocalAISettings(self._config,self._events,self)
        layout.addWidget(self.analysis_settings)
        # One set of file controls, shared by refinement and explanations.
        self._model_advanced_layout.addWidget(QLabel('Local Qwen runtime and model'))
        self._model_advanced_layout.addWidget(self.analysis_settings.files)
        self.analysis_settings.files.show()
        for button in self.analysis_settings.findChildren(QPushButton):
            if button.text() == 'Choose existing runtime / model files':
                button.hide()
        self.analysis_settings.exe.textChanged.connect(self._describe_preset)
        self.analysis_settings.gguf.textChanged.connect(self._describe_preset)

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

    def _analysis_status(self,message):
        if self.tabs.currentIndex()==5:
            self._feedback.setText(message)

    def _analysis_progress(self,message,percent):
        self._analysis_status(f'{message}: {percent}%')

    def _performance_page(self):
        outer = self._page('Models')
        subpages = QTabWidget()
        outer.addWidget(subpages)
        configuration = QWidget()
        layout = QVBoxLayout(configuration)
        subpages.addTab(configuration, 'Models')
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
        form.addRow('Translation',self._translation_mode)
        self._selected_models=QLabel();self._selected_models.setWordWrap(True)
        self._selected_models.setTextFormat(Qt.TextFormat.PlainText)
        self._runtime_models=QLabel('Running: waiting for live status')
        self._runtime_models.setWordWrap(True)
        self._runtime_models.setTextFormat(Qt.TextFormat.PlainText)
        advanced_form=QFormLayout()
        advanced_form.addRow('Speech CPU threads',self._threads)
        advanced_form.addRow('Translation CPU threads',self._mt_threads)
        self._gpu_setup = QWidget()
        gpu_form = QFormLayout(self._gpu_setup)
        gpu_form.setContentsMargins(0,0,0,0)
        gpu_form.addRow('Vulkan server',self._file_row(self._exe,True))
        gpu_form.addRow('Vulkan speech model',self._file_row(self._gpu_model))
        advanced_form.addRow(self._gpu_setup)
        self._backend.currentIndexChanged.connect(self._backend_visibility)
        self._exe.textChanged.connect(self._backend_visibility)
        self._gpu_model.textChanged.connect(self._backend_visibility)
        layout.addLayout(form)
        layout.addWidget(self._selected_models)
        layout.addWidget(self._runtime_models)
        layout.addWidget(self._preset_help)
        layout.addWidget(self._mode_hint)
        self._model_advanced=QWidget()
        self._model_advanced_layout=QVBoxLayout(self._model_advanced)
        self._model_advanced_layout.addLayout(advanced_form)
        advanced_toggle=QPushButton('Advanced');advanced_toggle.setCheckable(True)
        advanced_toggle.toggled.connect(self._model_advanced.setVisible)
        layout.addWidget(advanced_toggle);layout.addWidget(self._model_advanced)
        self._model_advanced.hide()
        hint = QLabel('GPU mode keeps the server loaded and verifies Vulkan allocation at startup. NLLB translation uses CPU; Qwen translation uses the local GPU model. With Vulkan, the selected GGML file determines model size; presets control decoding effort. GPU utilization and VRAM are shown when Windows performance counters are available.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        self._model_advanced_layout.addWidget(hint)
        installed=QPushButton('Use installed GPU speech model')
        def select_installed():
            from core.speech_assets import installed_paths
            executable,model=installed_paths()
            if executable.is_file() and model.is_file():
                self._exe.setText(str(executable.resolve()))
                self._gpu_model.setText(str(model.resolve()))
                self._backend.setCurrentIndex(self._backend.findData('vulkan'))
            else:
                self._feedback.setText('GPU speech assets are not installed. See the local speech setup instructions in README.')
        installed.clicked.connect(select_installed)
        layout.insertWidget(1,installed)
        self._translation_mode.currentIndexChanged.connect(self._describe_preset)
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
        self._exe.setText(c.vulkan_executable)
        self._gpu_model.setText(c.vulkan_model)
        self._translation.setChecked(c.translation_enabled)
        self._pronunciation.setChecked(c.show_pronunciation)
        self._show_overlay.setChecked(c.show_overlay)
        self._describe_preset()
        self._backend_visibility()

    def _backend_visibility(self):
        self._gpu_setup.setVisible(self._backend.currentData() == "vulkan")
        ready = Path(self._exe.text()).is_file() and Path(self._gpu_model.text()).is_file()
        self._backend.setItemText(1, "Radeon / Vulkan" if ready else "Radeon / Vulkan · setup required")
        self._describe_preset()

    def _model_metrics(self, data):
        if data.get('kind') != 'live':
            return
        engine=data.get('backend','Stopped')
        model=data.get('model','')
        self._runtime_models.setText('Running speech: '+engine+(' · '+model if model else '')+
            '\nLocal AI: '+str(data.get('analysis_status','Unloaded')))

    def _describe_preset(self):
        if not hasattr(self,'_selected_models'):
            return
        gpu=self._backend.currentData()=='vulkan'
        model=Path(self._gpu_model.text()).name if gpu else ('small' if self._quality.currentData()=='accurate' else 'base')
        ready=not gpu or (Path(self._exe.text()).is_file() and Path(self._gpu_model.text()).is_file())
        mode=self._translation_mode.currentData()
        from core.local_assets import managed_paths
        exe,gguf=managed_paths()
        if hasattr(self,'analysis_settings'):
            exe=Path(self.analysis_settings.exe.text().strip() or str(exe))
            gguf=Path(self.analysis_settings.gguf.text().strip() or str(gguf))
        ai_ready=exe.is_file() and gguf.is_file()
        self._selected_models.setText('Selected speech: '+(model or 'Choose a model')+
            (' · Radeon GPU' if gpu else ' · CPU')+('' if ready else ' · Files missing')+
            '\nTranslation: '+('Local Qwen · GPU (NLLB fallback)' if mode=='context' else 'NLLB · CPU')+
            '\nRefinement: '+('Off' if mode!='review' else gguf.name+' · GPU')+
            ('\nLocal AI files missing — choose them in Advanced.' if mode in ('context','review') and not ai_ready else ''))
        if gpu:
            self._preset_help.setText('The selected GPU file determines the speech model. Quality changes decoding effort, not model size. Changes take effect after Apply.')
            return
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
        c.translation_mode = self._translation_mode.currentData()
        c.translation_enabled = self._translation.isChecked()
        c.speech_detection=self._speech_detection.isChecked()
        c.speech_max_seconds=self._speech_max.value()
        c.speech_silence_seconds=self._speech_silence.value()
        c.speech_overlap_seconds=self._speech_overlap.value()
        c.speech_prompt=self._speech_prompt.text().strip()
        c.source_language = self._source.currentData()
        c.target_language = TargetLanguage(self._target.currentData())
        c.quality_mode = QualityMode(self._quality.currentData())
        c.apply_quality()
        c.backend = self._backend.currentData()
        c.cpu_threads, c.translation_threads = self._threads.value(),self._mt_threads.value()
        c.vulkan_executable,c.vulkan_model = self._exe.text().strip(),self._gpu_model.text().strip()
        self.appearance.apply_to(c)
        self.analysis_settings.apply_to(c)
        if c.backend == 'vulkan' and (not Path(c.vulkan_executable).is_file() or not Path(c.vulkan_model).is_file()):
            raise ValueError('Select an existing Vulkan whisper-server executable and GGML model first, or choose CPU.')
        return c

    def apply(self):
        try:
            c = self._draft()
        except ValueError as exc:
            self._feedback.setText(str(exc))
            self.tabs.setCurrentIndex(5 if any(word in str(exc).lower() for word in ('analysis','glossary','https','online')) else 3)
            return False
        for field in fields(c):
            setattr(self._config,field.name,getattr(c,field.name))
        self.setStyleSheet(style_for(c.theme))
        self._revert_threshold = c.noise_threshold
        self.appearance.restore()
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
        self.appearance.restore()
        if self.analysis_settings.service:
            self.analysis_settings.service.status_changed.disconnect(self._analysis_status)
            self.analysis_settings.service.progress_changed.disconnect(self._analysis_progress)
        self.analysis_settings.dispose()
        self.storage.set_active(False)
        for signal,slot in ((self._events.metrics_changed,self._model_metrics),
            (self._events.audio_level_changed,self._on_audio_level),
            (self._events.benchmark_progress,self._benchmark_progress),
            (self._events.benchmark_busy,self._benchmark_busy),
            (self._events.benchmark_finished,self.results.show_result)):
            try:
                signal.disconnect(slot)
            except (TypeError,RuntimeError):
                pass
        super().done(result)
