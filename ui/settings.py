"""Organized settings with explicit model changes and live noise-gate preview."""
from dataclasses import fields, replace
from pathlib import Path
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QStackedWidget, QFrame, QSpinBox, QDoubleSpinBox, QTabWidget, QVBoxLayout, QWidget, QListWidget, QSizePolicy)
from audio.capture import list_audio_sources
from core.config import AppConfig, TargetLanguage, QualityMode, LANGUAGE_LABELS, SOURCE_LANGUAGE_LABELS, QUALITY_LABELS
from core.events import EventBus
from ui.components import NoiseGateEditor
from ui.performance import LivePerformance, BenchmarkResults
from ui.theme import style_for
from ui.icons import icon_button


class SettingsContent:
    def __init__(self, config: AppConfig, events: EventBus, parent=None, page=0, replays=None, embedded=False):
        super().__init__(parent)
        self._config, self._events = config, events
        self.embedded=embedded;self._active=not embedded;self._disposed=False
        self.setObjectName('settingsPage');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self._revert_threshold = config.noise_threshold
        self._sources = []
        self.setWindowTitle('GrammAI - Settings')
        if not embedded:
            self.setStyleSheet(style_for(config.theme));self.resize(800,740);self.setMinimumSize(640,520)
        layout = QVBoxLayout(self)
        title = QLabel('Settings')
        title.setObjectName('title')
        if not embedded:layout.addWidget(title)
        subtitle=QLabel('A little tuning. A better listening experience.')
        subtitle.setObjectName('hint')
        subtitle.hide()
        layout.setContentsMargins(0,0,0,0) if embedded else layout.setContentsMargins(14,14,14,14)
        layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.categories=QListWidget();self.categories.setObjectName('settingsNavigation');self.categories.setFixedWidth(140);self.categories.setAccessibleName('Settings categories')
        workspace=QHBoxLayout();workspace.setSpacing(12);workspace.addWidget(self.categories);workspace.addWidget(self.tabs,1);layout.addLayout(workspace,1)
        if embedded:self.categories.hide()
        else:self.tabs.tabBar().hide()
        self._audio_page()
        self._language_page()
        self._appearance_page()
        self._performance_page()
        from ui.storage import StorageWidget
        storage_layout=self._page("Storage")
        self.storage=StorageWidget(config,events,replays)
        storage_layout.addWidget(self.storage)
        self.tabs.currentChanged.connect(lambda index:self.storage.set_active(index==4 and (not self.embedded or self._active)))
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
        if embedded:
            row=QHBoxLayout();row.addStretch()
            self.discard=QPushButton('Discard changes');self.discard.clicked.connect(self.reject);row.addWidget(self.discard)
            self.save_changes=QPushButton('Save changes');self.save_changes.setObjectName('primary');self.save_changes.clicked.connect(self.apply);row.addWidget(self.save_changes);layout.addLayout(row)
        else:
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
            buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply);layout.addWidget(buttons)
        self._load_values()
        self._pending_switch=None
        events.speech_switch_finished.connect(self._speech_switch_finished)
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
        layout.setSpacing(12);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.setMaximumWidth(760)
        host=QWidget();center=QHBoxLayout(host);center.setContentsMargins(0,0,0,0);center.addStretch();center.addWidget(body,1,Qt.AlignmentFlag.AlignTop);center.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(host)
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
        self._gate.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
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
        layout = self._page('Languages')
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
        for title,code in (('NLLB-200 600M / CPU','fast'),('Local Qwen / contextual translation','context')):
            self._translation_mode.addItem(title,code)
        self._translation_mode.setCurrentIndex(max(0,self._translation_mode.findData('context' if self._config.translation_mode=='context' else 'fast')))
        # The model choice is placed on Models after the language page is built.
        layout.addLayout(form)
        mode_hint=QLabel();self._mode_hint=mode_hint;mode_hint.setWordWrap(True);mode_hint.setObjectName('hint')
        descriptions={'fast':'Immediate NLLB translation. Lowest model overhead.',
            'context':'Qwen translates using up to three earlier original sentences. Uses the selected CPU/GPU setup; an installed NLLB model is the fallback. Stop live subtitles before manual local analysis.',
            'review':'NLLB subtitles appear immediately. Qwen reviews completed original sentences in the background. Refinements update automatically; open sentence details to compare versions. Transcripts are never changed automatically.'}
        self._translation_mode.currentIndexChanged.connect(lambda:mode_hint.setText(descriptions.get(self._translation_mode.currentData(),'Select a live translation model.')))
        mode_hint.setText(descriptions.get(self._translation_mode.currentData(),'Select a live translation model.'));layout.addWidget(mode_hint)
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
        subpages = QTabWidget();self.model_tabs=subpages
        outer.addWidget(subpages)
        configuration = QWidget()
        configuration_box = QVBoxLayout(configuration)
        configuration_box.setContentsMargins(0,0,0,0)
        # Construct the two pages with their real parents. Moving raw layout items
        # later leaves controls behind an empty sibling that intercepts input.
        self.component_stack=QStackedWidget(configuration)
        self._models_normal=QWidget(self.component_stack)
        self._models_normal.setObjectName('modelsOverview')
        layout=QVBoxLayout(self._models_normal)
        layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        self.component_stack.addWidget(self._models_normal)
        configuration_box.addWidget(self.component_stack)
        subpages.addTab(configuration,'Models')
        subpages.tabBar().hide()
        self._quality = QComboBox()
        for mode,label in QUALITY_LABELS.items():
            self._quality.addItem(label,mode.value)
        self._backend = QComboBox()
        self._backend.addItem('CPU - available', 'cpu')
        self._backend.addItem('GPU / Vulkan - requires local server and model', 'vulkan')
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
        self._processing=QComboBox()
        for text,value in [('Automatic','auto'),('CPU only','cpu'),('GPU preferred','gpu'),('Keep current setup','legacy')]:self._processing.addItem(text,value)
        from ui.speech_models import SpeechModelCombo
        self._speech_choice=SpeechModelCombo(self._config)
        self._learning_choice=QComboBox();self._learning_choice.addItem('Current / custom model','external');self._learning_choice.addItem('Qwen3 4B · shared local AI','qwen')
        form.addRow('Processing',self._processing)
        form.setVerticalSpacing(12);form.setHorizontalSpacing(14)
        self._selected_models=QLabel();self._selected_models.setWordWrap(True)
        self._selected_models.setTextFormat(Qt.TextFormat.PlainText)
        self._runtime_models=QLabel('Running: waiting for live status')
        self._runtime_models.setWordWrap(True)
        self._runtime_models.setTextFormat(Qt.TextFormat.PlainText)
        advanced_form=QFormLayout();advanced_form.addRow('Legacy speech engine',self._backend);advanced_form.addRow('Decoding effort',self._quality)
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
        self._role_status={}
        self._role_detail={}
        from ui.controls import ToggleSwitch
        from core.model_info import refinement_enabled
        self._refinement=ToggleSwitch('AI refinement');self._refinement.setChecked(refinement_enabled(self._config))
        self._refinement_destination=QComboBox();self._refinement_destination.addItem('History only','history');self._refinement_destination.addItem('History + subtitles','history_subtitles')
        self._refinement_destination.setCurrentIndex(max(0,self._refinement_destination.findData(self._config.refinement_destination)))
        for key,heading,control,caption,icon in (
            ('speech','Speech recognition',self._speech_choice,'Multilingual transcription','audio'),
            ('translation','Live translation',self._translation_mode,'Translates the transcript for subtitles and history','route'),
            ('learning','Learning assistant',self._learning_choice,'Word explanations and replies · on demand','sparkles')):
            section=QFrame();section.setObjectName('modelRoleCard')
            section_box=QHBoxLayout(section);section_box.setContentsMargins(14,12,14,12);section_box.setSpacing(12)
            symbol=icon_button(icon,heading,section);symbol.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);symbol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            section_box.addWidget(symbol,0,Qt.AlignmentFlag.AlignTop)
            body=QVBoxLayout();body.setSpacing(6);header=QHBoxLayout()
            title=QLabel(heading);title.setObjectName('field');header.addWidget(title,1)
            status=QLabel('Not loaded' if key=='speech' else 'On demand');status.setObjectName('badge');header.addWidget(status)
            self._role_status[key]=status;body.addLayout(header);body.addWidget(control)
            detail=QLabel(caption);detail.setObjectName('hint');detail.setWordWrap(True)
            self._role_detail[key]=detail;body.addWidget(detail)
            if key=='translation':
                self._translation_running=QLabel('No translation output this session');self._translation_running.setObjectName('hint');self._translation_running.setWordWrap(True);body.addWidget(self._translation_running)
            if key=='speech':
                from ui.model_setup import TaskWidget
                from ui.icons import set_button_icon
                self.speech_download=QPushButton('Download');set_button_icon(self.speech_download,'download');self.speech_download.setAccessibleName('Download selected speech model');self.speech_download.clicked.connect(self._download_speech)
                body.addWidget(self.speech_download,0,Qt.AlignmentFlag.AlignLeft)
                self._speech_running=QLabel('Not running');self._speech_running.setObjectName('hint');self._speech_running.setWordWrap(True);body.addWidget(self._speech_running)
                self.speech_task=TaskWidget(self._events,self);self.speech_task.progress.setObjectName('speechDownloadProgress');self.speech_task.progress.setTextVisible(False);self.speech_task.progress.setFixedHeight(5);self.speech_task.task_footer(body)
            section_box.addLayout(body,1);layout.addWidget(section)
            if key=='translation':
                refinement_card=QFrame();refinement_card.setObjectName('modelRoleCard');refine_box=QVBoxLayout(refinement_card);refine_box.setContentsMargins(14,12,14,12);refine_box.setSpacing(6)
                refine_header=QHBoxLayout();refine_header.addWidget(self._refinement,1)
                self._refinement_status=QLabel('On demand');self._refinement_status.setObjectName('badge');refine_header.addWidget(self._refinement_status);refine_box.addLayout(refine_header)
                self._refinement_model=QLabel();self._refinement_model.setObjectName('hint');self._refinement_model.setWordWrap(True);refine_box.addWidget(self._refinement_model)
                refine_hint=QLabel('Reviews original speech and nearby dialogue to improve the translation.');refine_hint.setObjectName('hint');refine_hint.setWordWrap(True);refine_box.addWidget(refine_hint)
                refine_box.addWidget(self._refinement_destination);layout.addWidget(refinement_card)
                self._refinement.toggled.connect(self._refinement_destination.setEnabled)
                self._refinement_destination.setEnabled(self._refinement.isChecked())
        self._selected_models.setObjectName('contextPreview');self._runtime_models.setObjectName('contextPreview')
        shared=QLabel('One Qwen download powers contextual translation and learning.');shared.setObjectName('hint');shared.setWordWrap(True);layout.addWidget(shared)
        self._model_help_placeholder=self._preset_help
        self._model_advanced=QWidget()
        self._model_advanced_layout=QVBoxLayout(self._model_advanced)
        self._model_advanced_layout.addLayout(advanced_form)
        advanced_toggle=QPushButton('Advanced');advanced_toggle.setObjectName('secondary');advanced_toggle.setCheckable(True)
        advanced_toggle.toggled.connect(self._model_advanced.setVisible)
        layout.addWidget(advanced_toggle);layout.addWidget(self._model_advanced)
        self._model_advanced.hide()
        hint = QLabel('GPU mode keeps the server loaded and verifies Vulkan allocation at startup. NLLB translation uses CPU; Qwen translation uses its selected CPU/GPU runtime. With Vulkan, the selected GGML file determines model size; presets control decoding effort. GPU utilization and VRAM are shown when Windows performance counters are available.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        self._model_advanced_layout.addWidget(hint)
        self._model_advanced_layout.addWidget(self._selected_models)
        self._model_advanced_layout.addWidget(self._runtime_models)
        self._model_advanced_layout.addWidget(self._preset_help)
        self._model_advanced_layout.addWidget(self._mode_hint)
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
        self._model_advanced_layout.addWidget(installed)
        from ui.model_setup import ComponentsWidget,TaskWidget,SetupDialog
        self.component_manager=ComponentsWidget(self._config,self._events,self.component_stack)
        self.component_stack.addWidget(self.component_manager);self.component_stack.setCurrentIndex(0)
        self.component_manager.back.clicked.connect(lambda:self._show_components(False))
        actions=QHBoxLayout();self.manage_components=QPushButton('Manage components');self.setup_assistant=QPushButton('Setup assistant');self.test_setup=QPushButton('Test setup')
        for button in (self.manage_components,self.test_setup,self.setup_assistant):actions.addWidget(button)
        layout.addLayout(actions)
        self.manage_components.clicked.connect(lambda:self._show_components(True));self.setup_assistant.clicked.connect(self._open_setup_assistant);self.test_setup.clicked.connect(self._test_selected_setup)
        self.model_task=TaskWidget(self._events,self);self.model_task.task_footer(layout)
        for control in (self._processing,self._speech_choice,self._learning_choice):control.currentIndexChanged.connect(self._describe_preset)
        self._translation_mode.currentIndexChanged.connect(self._describe_preset)
        self._refinement.toggled.connect(self._describe_preset)
        self._translation.toggled.connect(self._describe_preset)
        layout.addStretch()
        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.addWidget(LivePerformance(self._events))
        explanation = QLabel('Live readings update once per second. Stage timings describe the last completed speech segment and exclude audio collection and queue wait. CPU includes app child processes and is normalized to total machine capacity.')
        explanation.setWordWrap(True)
        explanation.setObjectName('hint')
        monitor_layout.addWidget(explanation)
        monitor_layout.addStretch()
        subpages.addTab(monitor,'Live monitor')
        if self.embedded:subpages.setTabVisible(1,False)
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

    def _show_components(self,opened):
        self.component_stack.setCurrentIndex(1 if opened else 0)
        if opened:self.component_manager.refresh()
        else:self._speech_choice.refresh();self._describe_preset()

    def _open_setup_assistant(self):
        from ui.model_setup import SetupDialog
        if not self.model_task.can_modify():return
        self._setup_dialog=SetupDialog(self._config,self._events,self)
        self._setup_dialog.setStyleSheet(style_for(self._config.theme))
        self._setup_dialog.accepted.connect(self._setup_applied);self._setup_dialog.open()

    def _setup_applied(self):
        c=self._config
        for control,value in ((self._processing,c.processing_mode),(self._speech_choice,c.speech_model_id),(self._learning_choice,c.learning_model_id),(self._backend,c.backend)):
            control.setCurrentIndex(max(0,control.findData(value)))
        self._exe.setText(c.vulkan_executable);self._gpu_model.setText(c.vulkan_model)
        self._translation_mode.setCurrentIndex(self._translation_mode.findData('context' if c.translation_mode=='context' else 'fast'));self._translation.setChecked(c.translation_enabled);self.analysis_settings.enabled.setChecked(c.analysis_enabled)
        from core.model_info import refinement_enabled
        self._refinement.setChecked(refinement_enabled(c));self._refinement_destination.setCurrentIndex(max(0,self._refinement_destination.findData(c.refinement_destination)))
        self._events.state_changed.emit(c.snapshot());self._describe_preset()
        if self.embedded:
            applied=SettingsContent._draft(self,validate=False)
            for name in ('processing_mode','speech_model_id','learning_model_id','backend','vulkan_executable','vulkan_model','translation_mode','translation_enabled','analysis_enabled','refinement_enabled','refinement_destination'):
                setattr(self._baseline,name,getattr(applied,name))
            self._update_save_state()

    def _refresh_speech_download(self):
        if not hasattr(self,'speech_download'):return
        from core.speech_models import components,paths
        from core.components import catalog
        key=self._speech_choice.currentData();found=paths(key,self._config);missing=[item for item in components(key) if not found.get(item)]
        self.speech_download.setVisible(bool(missing));self.speech_download.setEnabled(not self.speech_task.job)
        if missing:
            from core.components import ComponentManager
            partial=key=='speech-cpu' and ComponentManager().availability(key)=='incomplete'
            self.speech_download.setText('Repair missing files' if partial else 'Download')
            size=sum(catalog()[item].size for item in missing)/1e9
            self._role_detail['speech'].setText(f'{size:.2f} GB download · model and missing runtime'+(' · Experimental' if key=='speech-qwen' else ''))
        elif key:
            self._role_detail['speech'].setText('Installed'+(' / Experimental' if key=='speech-qwen' else ''))
    def _download_speech(self):
        from core.components import ComponentManager
        from core.speech_models import components,paths
        key=self._speech_choice.currentData();found=paths(key,self._config);missing=[item for item in components(key) if not found.get(item)];manager=ComponentManager()
        if not missing:return
        def work(progress,cancelled):
            for item in missing:
                if cancelled():raise InterruptedError('Download cancelled; retry to resume.')
                manager.install(item,progress,cancelled)
        def done(result):
            self._speech_choice.refresh();self.component_manager.refresh();self._describe_preset()
            if 'error' not in result:self.speech_task.status.setText('Installed. Save changes to switch speech models.')
        self.speech_task.start_job(work,done,requires_idle=False);self._refresh_speech_download()
    def _speech_switch_finished(self,result):
        if result.get('token')!=self._pending_switch:return
        self._pending_switch=None;self.tabs.setEnabled(True)
        if self.embedded:self.save_changes.setEnabled(True);self.discard.setEnabled(True)
        if result.get('error'):
            self._feedback.setText('Previous speech model kept. '+result['error'])
            if self.embedded:self._update_save_state()
            return
        self._speech_choice.refresh();self._load_values();self._revert_threshold=self._config.noise_threshold;self.appearance.restore()
        if self.embedded:
            self._baseline=SettingsContent._draft(self,validate=False);self._gate_dirty=False;self._update_save_state()
        self._feedback.setText('Saved. Speech model checked and selected.')

    def _test_selected_setup(self):
        from core.setup import test_configuration
        try:draft=self._draft()
        except ValueError as exc:self.model_task.status.setText(str(exc));return
        def done(result):
            if 'value' in result:
                r=result['value'];self.model_task.status.setText(f"{r['backend']} · {r['speech_ms']:.0f} ms for {r['audio_seconds']:.1f}s audio · translation {r.get('translation_ms',0):.0f} ms · {r['memory_mb']:.0f} MB app/worker memory. "+('Keeps up with this sample.' if r['keeps_up'] else 'May not keep up; consider a smaller model.')+' Compatibility/speed test, not an accuracy score.')
        self.model_task.start_job(lambda progress,cancelled:test_configuration(draft,progress,cancelled),done)

    def _load_values(self):
        c = self._config
        from core.model_info import refinement_enabled
        self._refinement.setChecked(refinement_enabled(c));self._refinement_destination.setCurrentIndex(max(0,self._refinement_destination.findData(c.refinement_destination)))
        for control,value in ((self._processing,c.processing_mode),(self._speech_choice,c.speech_model_id),(self._learning_choice,c.learning_model_id)):
            if control is self._speech_choice:
                from core.speech_models import selected_id
                value=selected_id(c)
            control.setCurrentIndex(max(0,control.findData(value)))
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
        self._backend.setItemText(1, "GPU / Vulkan" if ready else "GPU / Vulkan · setup required")
        self._describe_preset()

    def _model_metrics(self, data):
        if data.get('kind') != 'live':
            return
        engine=data.get('backend','Stopped')
        model=data.get('model','')
        self._runtime_models.setText('Running speech: '+engine+(' · '+model if model else '')+
            '\nLocal AI: '+str(data.get('analysis_status','Unloaded')))
        last=self._events.property('last_translation_info') or {}
        self._translation_running.setText('Last output: '+last['model']+' / '+last.get('backend','') if last.get('model') else 'No translated output this session')
        self._translation_running.setToolTip(last.get('fallback',''))
        from core.speech_models import TITLES
        label=str(model).lower();running=next((key for key,title in TITLES.items() if title.lower().replace(' · cpu','') in label),None)
        if not running and self._config.speech_model_id=='external':
            from core.speech_models import selected_id
            running=selected_id(self._config)
        self._speech_choice.running_id=running if engine not in ('Stopped','Not loaded','Switching speech model') else None
        self._speech_choice.refresh()
        self._speech_running.setText('Running: '+str(model)+' · '+engine if model and engine not in ('Stopped','Not loaded') else 'Not running')
        self._role_status['speech'].setText('GPU' if engine.startswith('GPU') else 'CPU' if engine.startswith('CPU') else 'Checking' if 'Switching' in engine else 'Idle')
        self._role_status['speech'].setToolTip('Currently running: '+engine+(' · '+model if model else ''))
        ai_status=str(data.get('analysis_status','Unloaded'))
        self._role_status['learning'].setText('Loaded' if 'loaded' in ai_status.lower() and 'unloaded' not in ai_status.lower() else 'Installed' if getattr(self,'_ai_ready',False) else 'Missing files')
        self._role_status['learning'].setToolTip(ai_status)
        self._refinement_status.setToolTip('Shared local AI: '+ai_status)

    def _describe_preset(self):
        if not hasattr(self,'_selected_models'):
            return
        gpu=self._backend.currentData()=='vulkan'
        selected=self._speech_choice.currentData() if hasattr(self,'_speech_choice') else 'external'
        model=({'speech-cpu':'Whisper base','speech-turbo':'Whisper large-v3-turbo'}.get(selected) or Path(self._gpu_model.text()).name) if gpu else ('small' if self._quality.currentData()=='accurate' else 'base')
        if selected=='speech-cpu':model='Whisper base';gpu=False
        elif selected in ('speech-large','speech-qwen'):
            from core.speech_models import TITLES
            model=TITLES[selected];gpu=self._processing.currentData()!='cpu'
        elif selected=='speech-turbo':model='Whisper large-v3-turbo';gpu=self._processing.currentData()!='cpu'
        from core.components import resolve
        ready=bool(resolve('speech-runtime') and resolve('speech-turbo')) if selected=='speech-turbo' else bool(resolve('speech-cpu')) if selected=='speech-cpu' else (not gpu or (Path(self._exe.text()).is_file() and Path(self._gpu_model.text()).is_file()))
        if selected in ('speech-large','speech-qwen'):
            from core.speech_models import installed
            ready=installed(selected,self._config)
        mode=self._translation_mode.currentData()
        self._refinement.setEnabled(mode!='context')
        self._refinement_destination.setEnabled(mode!='context' and self._refinement.isChecked())
        if mode=='context':self._refinement.setChecked(False)
        from core.local_assets import managed_paths
        exe,gguf=managed_paths()
        if hasattr(self,'analysis_settings'):
            exe=Path(self.analysis_settings.exe.text().strip() or str(exe))
            gguf=Path(self.analysis_settings.gguf.text().strip() or str(gguf))
        if self._learning_choice.currentData()=='qwen':
            gguf=resolve('qwen') or Path('missing-model.gguf')
            exe=(resolve('ai-cpu') if self._processing.currentData()=='cpu' else resolve('ai-vulkan') or resolve('ai-cpu')) or Path('missing-runtime.exe')
        ai_ready=exe.is_file() and gguf.is_file();self._ai_ready=ai_ready
        self._selected_models.setText('Selected speech: '+(model or 'Choose a model')+
            (' · GPU preferred' if gpu else ' · CPU')+('' if ready else ' · Files missing')+
            '\nTranslation: '+('Local Qwen · '+self._processing.currentText() if mode=='context' else 'NLLB · CPU')+
            '\nLearning: '+('Shared Qwen model' if self._learning_choice.currentData()=='qwen' else gguf.name)+
            ('\nLocal AI files missing — choose them in Advanced.' if mode in ('context','review') and not ai_ready else ''))
        if hasattr(self,'_role_detail'):
            self._role_detail['speech'].setText((model or 'Current model')+' · '+('GPU preferred' if gpu else 'CPU')+('' if ready else ' · install required'))
            from core.model_info import local_ai_name
            ai_name=local_ai_name(replace(self._config,learning_model_id=self._learning_choice.currentData(),analysis_gguf=str(gguf)))
            self._refinement_model.setText(ai_name+' / shared with Learning assistant')
            self._refinement_status.setText('Not needed' if mode=='context' else ('Enabled' if ai_ready else 'Missing files') if self._refinement.isChecked() else 'Off')
            if mode=='context':self._refinement_model.setText(ai_name+' already uses original dialogue for live translation; no extra review pass.')
            self._role_detail['translation'].setText('Translates original speech for subtitles and history. '+('Uses nearby original dialogue.' if mode=='context' else ''))
            from core.components import ComponentManager
            translation_ready=ai_ready if mode=='context' else ComponentManager().availability('translation-fast')=='installed'
            self._role_status['translation'].setText(('Installed' if translation_ready else 'Missing files') if self._translation.isChecked() else 'Off')
            self._translation_mode.setItemText(1,ai_name+' / contextual translation')
            self._role_status['learning'].setText('Installed' if ai_ready else 'Missing files')
            self._role_detail['learning'].setText((gguf.name if self._learning_choice.currentData()=='external' else 'Qwen3 4B')+' · explanations and replies on demand')
        self._refresh_speech_download()
        if selected!='external':
            self._preset_help.setText('The selected model stays unchanged. Decoding effort changes how much inference work is done. Save changes to apply.');return
        if gpu:
            self._preset_help.setText('The selected GPU file determines the speech model. Quality changes decoding effort, not model size. Changes take effect after Apply.')
            return
        descriptions = {'fast': 'Low resource: base speech model, minimal decoding effort. Lower CPU demand; may reduce accuracy.',
            'balanced': 'Balanced: base speech model with moderate decoding effort. A useful starting point for watching videos.',
            'accurate': 'Best quality: small speech model and deeper decoding. Uses more processing time.'}
        self._preset_help.setText(descriptions.get(self._quality.currentData(),''))

    def _draft(self,validate=True):
        c = replace(self._config)
        c.audio_device_id = self._device.currentData() or ''
        source = next((s for s in self._sources if s.device_id == c.audio_device_id),None)
        c.audio_device_name = source.name if source else 'Desktop audio (default)'
        c.audio_device_kind = source.kind if source else 'loopback'
        c.translation_mode = self._translation_mode.currentData()
        c.refinement_enabled = self._refinement.isChecked()
        c.refinement_destination = self._refinement_destination.currentData()
        c.translation_enabled = self._translation.isChecked()
        c.speech_detection=self._speech_detection.isChecked()
        c.speech_max_seconds=self._speech_max.value()
        c.speech_silence_seconds=self._speech_silence.value()
        c.speech_overlap_seconds=self._speech_overlap.value()
        c.speech_prompt=self._speech_prompt.text().strip()
        c.source_language = self._source.currentData()
        c.target_language = TargetLanguage(self._target.currentData())
        c.quality_mode = QualityMode(self._quality.currentData())
        c.backend = self._backend.currentData()
        c.processing_mode=self._processing.currentData();c.speech_model_id=self._speech_choice.currentData();c.learning_model_id=self._learning_choice.currentData()
        c.apply_quality()
        c.cpu_threads, c.translation_threads = self._threads.value(),self._mt_threads.value()
        c.vulkan_executable,c.vulkan_model = self._exe.text().strip(),self._gpu_model.text().strip()
        c.saved_audio_limit_mb=self.storage.audio_limit.currentData() or 250
        self.appearance.apply_to(c)
        self.analysis_settings.apply_to(c)
        from core.components import resolve
        if c.speech_model_id=='speech-cpu':
            c.backend='cpu'
            if validate and not resolve('speech-cpu'):raise ValueError('Install the selected CPU speech model in Manage components first.')
        elif c.speech_model_id=='speech-turbo':
            c.backend='cpu' if c.processing_mode=='cpu' else 'vulkan'
            runtime,model=resolve('speech-runtime'),resolve('speech-turbo')
            if runtime:c.vulkan_executable=str(runtime)
            if model:c.vulkan_model=str(model)
            if validate and (not runtime or not model):raise ValueError('Install the selected speech model and runtime in Manage components first.')
        if validate and c.learning_model_id=='qwen':
            if not resolve('qwen') or not (resolve('ai-cpu') if c.processing_mode=='cpu' else resolve('ai-vulkan') or (resolve('ai-cpu') if c.processing_mode=='auto' else None)):raise ValueError('Install the selected local AI model and matching runtime first.')
        if c.speech_model_id in ('speech-large','speech-qwen'):
            from core.speech_models import configure
            if validate:c=configure(c,c.speech_model_id)
            else:c.backend='qwen-asr' if c.speech_model_id=='speech-qwen' else 'vulkan'
        if validate:
            from core.setup import validate_selection
            validate_selection(c)
        if validate and c.backend == 'vulkan' and (not Path(c.vulkan_executable).is_file() or not Path(c.vulkan_model).is_file()):
            raise ValueError('Select an existing Vulkan whisper-server executable and GGML model first, or choose CPU.')
        return c

    def apply(self):
        try:
            c = self._draft()
        except ValueError as exc:
            self._feedback.setText(str(exc))
            self.tabs.setCurrentIndex(5 if any(word in str(exc).lower() for word in ('analysis','glossary','https','online')) else 3)
            return False
        from core.speech_models import speech_key
        if self._events.property('speech_switch_available') and speech_key(c)!=speech_key(self._config):
            from uuid import uuid4
            if self._pending_switch:return False
            self._pending_switch=uuid4().hex;self.tabs.setEnabled(False)
            if self.embedded:self.save_changes.setEnabled(False);self.discard.setEnabled(False)
            self._feedback.setText('Checking selected speech model…')
            self._events.speech_switch_requested.emit({'token':self._pending_switch,'config':c});return False
        for field in fields(c):
            setattr(self._config,field.name,getattr(c,field.name))
        if not self.embedded:self.setStyleSheet(style_for(c.theme))
        self._revert_threshold = c.noise_threshold
        self.appearance.restore()
        self._events.state_changed.emit(c.snapshot())
        self._events.overlay_toggled.emit(c.show_overlay)
        self._feedback.setText('Saved. Changes are active.')
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

    def dispose(self):
        if self._disposed:return
        self._disposed=True
        self.appearance.restore()
        if self.analysis_settings.service:
            self.analysis_settings.service.status_changed.disconnect(self._analysis_status)
            self.analysis_settings.service.progress_changed.disconnect(self._analysis_progress)
        self.analysis_settings.dispose()
        self.model_task.dispose();self.component_manager.dispose();self.speech_task.dispose()
        try:self._events.speech_switch_finished.disconnect(self._speech_switch_finished)
        except (TypeError,RuntimeError):pass
        if getattr(self,'_setup_dialog',None):self._setup_dialog.reject()
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



class SettingsDialog(SettingsContent,QDialog):
    def done(self,result):
        self.dispose();super().done(result)


class SettingsPage(SettingsContent,QWidget):
    reset_requested=Signal(int)

    def __init__(self,config,events,parent=None,page=0,replays=None):
        self._gate_dirty=False
        super().__init__(config,events,parent,page,replays,embedded=True)
        self._baseline=SettingsContent._draft(self,validate=False)
        self._feedback.setText('Save changes to apply. Audio and subtitle previews revert when you leave Settings.')
        self.save_changes.setEnabled(False)
        self._watch_settings_changes()
        self._update_save_state()

    def _watch_settings_changes(self):
        from PySide6.QtWidgets import QAbstractButton,QAbstractSlider,QPlainTextEdit,QTextEdit
        for control in self.findChildren(QWidget):
            if isinstance(control,QComboBox):signal=control.currentIndexChanged
            elif isinstance(control,(QSpinBox,QDoubleSpinBox,QAbstractSlider)):signal=control.valueChanged
            elif isinstance(control,(QLineEdit,QPlainTextEdit,QTextEdit)):signal=control.textChanged
            elif isinstance(control,QAbstractButton):
                control.toggled.connect(self._update_save_state)
                signal=control.clicked
            else:continue
            signal.connect(self._update_save_state)

    def _update_save_state(self,*args):
        if self._disposed:return
        try:
            draft=SettingsContent._draft(self,validate=False)
            # The noise gate previews live and reverts on leaving Settings;
            # compare its retained editor value rather than the previewed config.
            draft.noise_threshold=self._gate.meter.threshold/100
            dirty=draft!=self._baseline
        except ValueError:
            # Invalid edits still need Save to present their validation message.
            dirty=True
        self.save_changes.setEnabled(dirty and self._pending_switch is None)

    def _draft(self,validate=True):
        draft=SettingsContent._draft(self,validate=False)
        baseline=getattr(self,'_baseline',draft)
        merged=replace(self._config)
        for field in fields(draft):
            if getattr(draft,field.name)!=getattr(baseline,field.name):setattr(merged,field.name,getattr(draft,field.name))
        if self._gate_dirty:merged.noise_threshold=self._gate.meter.threshold/100
        if validate:
            from core.speech_models import configure
            if merged.speech_model_id in ('speech-turbo','speech-large','speech-qwen','speech-cpu'):merged=configure(merged,merged.speech_model_id)
            from core.setup import validate_selection
            validate_selection(merged)
        if validate and merged.backend=='vulkan' and (not Path(merged.vulkan_executable).is_file() or not Path(merged.vulkan_model).is_file()):
            raise ValueError('Choose existing GPU speech files in Models, or choose CPU.')
        return merged

    def _preview_gate(self,percent):
        self._gate_dirty=True
        if self._active:super()._preview_gate(percent)
        if hasattr(self,'_baseline'):self._update_save_state()

    def apply(self):
        if not super().apply():
            self._update_save_state();return False
        self._gate_dirty=False;self._baseline=SettingsContent._draft(self,validate=False)
        self._update_save_state()
        return True

    def activate(self,page=None):
        self._active=True;self._revert_threshold=self._config.noise_threshold
        # Refresh externally changed controls only when the user has no draft for them.
        for name,widget in (('audio_device_id',self._device),('source_language',self._source),('target_language',self._target),('theme',self._theme)):
            current=widget.currentData();base=getattr(self._baseline,name);base=getattr(base,'value',base)
            if current==base:
                value=getattr(self._config,name);value=getattr(value,'value',value)
                with QSignalBlocker(widget):
                    index=widget.findData(value)
                    if index<0 and name=='audio_device_id':widget.addItem(self._config.audio_device_name or 'Selected device (unavailable)',value);index=widget.count()-1
                    widget.setCurrentIndex(max(0,index))
                setattr(self._baseline,name,getattr(self._config,name))
        if not self._gate_dirty:self._gate.set_threshold(round(self._config.noise_threshold*100))
        if page is not None:self.tabs.setCurrentIndex(page)
        self.storage.set_active(self.tabs.currentIndex()==4)
        self._update_save_state()

    def suspend(self):
        self._active=False;self.storage.set_active(False);self.appearance.restore()
        if self._gate_dirty:
            self._config.noise_threshold=self._revert_threshold;self._events.state_changed.emit(self._config.snapshot())

    def reject(self):
        self.suspend();self.reset_requested.emit(self.tabs.currentIndex())

    def accept(self):
        self.apply()

    def dispose(self):
        if self._disposed:return
        self.suspend();super().dispose()
