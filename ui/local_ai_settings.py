"""Local-first analysis setup and plain-language conversation preferences."""
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,
    QCheckBox,QComboBox,QLineEdit,QSpinBox,QLabel,QPushButton,QPlainTextEdit,QProgressBar,
    QFileDialog,QMessageBox)
from core.config import LANGUAGE_LABELS
from core.local_assets import MODEL_BYTES,RUNTIME_BYTES,MODEL_FILE,ASSET_ROOT,managed_paths
from core.tutor import examples


class LocalAISettings(QWidget):
    def __init__(self,config,events,parent=None):
        super().__init__(parent)
        self.config,self.service=config,getattr(events,'analysis_service',None)
        self.events=events
        layout=QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop);layout.setSpacing(12)
        self.enabled=QCheckBox('Enable on-demand sentence explanations')
        self.enabled.setChecked(config.analysis_enabled)
        layout.addWidget(self.enabled)
        note=QLabel('Translation mode lives under Translation. Here you can explain meaning and slang when you open a sentence. Automatic review uses local Qwen regardless of the optional explanation provider.')
        note.setWordWrap(True);note.setObjectName('hint');layout.addWidget(note)
        self.explanation=self._combo([(label,code.value) for code,label in LANGUAGE_LABELS.items()],config.analysis_explanation_language)
        quick=QFormLayout();quick.addRow('Explain in',self.explanation);layout.addLayout(quick)
        self.provider=QComboBox()
        self.provider.addItem('Local GPU - offline, no API fees','local')
        self.provider.addItem('Online provider - optional','online')
        self.provider.setCurrentIndex(max(0,self.provider.findData(config.analysis_provider)))
        self.provider.hide()
        tabs=QTabWidget()
        advanced=QPushButton('Advanced: model, conversation and online options');advanced.setCheckable(True)
        layout.addWidget(advanced);layout.addWidget(tabs);tabs.hide();advanced.toggled.connect(tabs.setVisible)
        runtime,form=self._tab(tabs,'Local model')
        form.addWidget(QLabel('Provider for on-demand explanations'));form.addWidget(self.provider);self.provider.show()
        info=QLabel(f'Qwen3 4B / Q4_K_M candidate: {MODEL_BYTES/1e9:.2f} GB + {RUNTIME_BYTES/1e6:.0f} MB runtime. Apache 2.0. Local GPU only. Experimental tutor: Thai and slang can still be wrong; review every refinement.')
        info.setToolTip('Files are stored in '+str(ASSET_ROOT))
        info.setWordWrap(True)
        form.addWidget(info)
        self.exe=QLineEdit(config.analysis_executable)
        self.gguf=QLineEdit(config.analysis_gguf)
        self.exe.setPlaceholderText(str(managed_paths()[0]))
        self.gguf.setPlaceholderText(str(managed_paths()[1]))
        self.files=QWidget()
        files_layout=QFormLayout(self.files)
        files_layout.setContentsMargins(0,0,0,0)
        files_layout.addRow('Vulkan llama-server',self._file_row(self.exe,'Executable (*.exe)'))
        files_layout.addRow('GGUF instruction model',self._file_row(self.gguf,'GGUF model (*.gguf)'))
        advanced=QPushButton('Choose existing runtime / model files')
        advanced.setCheckable(True)
        advanced.toggled.connect(self.files.setVisible)
        self.files.hide()
        fields=QFormLayout()
        self.context_tokens=QSpinBox()
        self.context_tokens.setRange(2048,8192)
        self.context_tokens.setSingleStep(1024)
        self.context_tokens.setValue(config.analysis_context_tokens)
        self.idle_minutes=QSpinBox()
        self.idle_minutes.setRange(0,30)
        self.idle_minutes.setSuffix(' min')
        self.idle_minutes.setSpecialValueText('Keep loaded until exit')
        self.idle_minutes.setValue(config.analysis_idle_minutes)
        fields.addRow('Context limit (tokens)',self.context_tokens)
        fields.addRow('Unload after inactivity',self.idle_minutes)
        form.addLayout(fields)
        row=QHBoxLayout()
        self.install=QPushButton('Install local model + runtime')
        self.load=QPushButton('Test local model on GPU')
        self.unload=QPushButton('Unload')
        self.stop=QPushButton('Cancel task')
        for button in (self.install,self.load,self.unload,self.stop):
            row.addWidget(button)
        form.addLayout(row)
        self.remove=QPushButton('Remove downloaded Qwen model...')
        form.addWidget(self.remove)
        self.progress=QProgressBar()
        self.progress.setRange(0,100)
        self.progress.hide()
        form.addWidget(self.progress)
        self.status=QLabel(self.service.runtime.status if self.service else 'Local model service starts with the app.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        executable,model=self.service.runtime.paths(config) if self.service else managed_paths()
        if not (self.service and self.service.runtime.loaded):
            self.status.setText('Ready - local model installed; loads when needed.' if executable.is_file() and model.is_file() else 'Local model needs setup. Open Advanced to install or choose model files.')
        layout.insertWidget(3,self.status)
        row.removeWidget(self.load);layout.insertWidget(4,self.load)
        form.addWidget(advanced)
        form.addWidget(self.files)
        form.addStretch()
        _,conversation=self._tab(tabs,'Conversation')
        self.speech=self._combo([('Everyday conversation','everyday'),('Neutral','neutral'),('Formal','formal')],config.analysis_speech_style)
        self.translation=self._combo([('Preserve speaker tone','preserve_tone'),('Natural in target language','natural'),('Literal for study','literal')],config.analysis_translation_style)
        self.sentences=QSpinBox()
        self.sentences.setRange(0,5)
        self.sentences.setValue(config.analysis_context_sentences)
        fields=QFormLayout()
        fields.addRow('Speech style',self.speech)
        fields.addRow('Translation style',self.translation)
        fields.addRow('Earlier sentences to use',self.sentences)
        conversation.addLayout(fields)
        self.slang=QCheckBox('Explain slang, idioms and implied meaning')
        self.slang.setChecked(config.analysis_explain_slang)
        conversation.addWidget(self.slang)
        self.reasoning=QCheckBox('Deeper local reasoning (slower; recommended for context)')
        self.reasoning.setChecked(config.analysis_reasoning)
        conversation.addWidget(self.reasoning)
        conversation.addWidget(QLabel('Personal glossary (up to 4,000 characters)'))
        self.glossary=QPlainTextEdit(config.analysis_glossary)
        self.glossary.setPlaceholderText('Indonesian: nggak = tidak (casual)\nEnglish: call the shots = make the decisions\nAdd names and preferred meanings; the model uses them only when relevant.')
        self.glossary.setMaximumHeight(120)
        conversation.addWidget(self.glossary)
        self.example_values=examples(config)
        self.example_summary=QLabel(f'{len(self.example_values)} / 10 saved correction examples')
        conversation.addWidget(self.example_summary)
        self.example_view=QPlainTextEdit()
        self.example_view.setReadOnly(True)
        self.example_view.setMaximumHeight(100)
        self._show_examples()
        conversation.addWidget(self.example_view)
        clear=QPushButton('Delete saved correction examples...')
        clear.clicked.connect(self._clear_examples)
        conversation.addWidget(clear)
        hint=QLabel('Save examples from History after applying a refinement. Each analysis uses up to two examples for its language route and the first 1,500 glossary characters. These guide inference, not model training. Settings/examples stay locally on disk until edited/deleted.')
        hint.setWordWrap(True)
        conversation.addWidget(hint)
        _,online=self._tab(tabs,'Online (optional)')
        self.endpoint=QLineEdit(config.analysis_endpoint)
        self.endpoint.setPlaceholderText('https://provider.example/v1/chat/completions')
        self.model=QLineEdit(config.analysis_model)
        self.key_env=QLineEdit(config.analysis_key_env)
        fields=QFormLayout()
        fields.addRow('Chat-completions URL',self.endpoint)
        fields.addRow('Provider model ID',self.model)
        fields.addRow('API-key environment variable',self.key_env)
        online.addLayout(fields)
        hint=QLabel('Used only when Online provider is explicitly selected above. Analysis sends the selected transcript, translation, context, glossary and saved examples to that provider. No audio is sent. Charges/retention policies may apply. Keys are read from the environment and never saved. There is no automatic cloud fallback.')
        hint.setWordWrap(True)
        online.addWidget(hint)
        online.addStretch()
        self.install.clicked.connect(self._install)
        self.load.clicked.connect(lambda:self._manage('load'))
        self.unload.clicked.connect(lambda:self._manage('unload'))
        self.remove.clicked.connect(self._remove)
        self.stop.clicked.connect(lambda:self.service.cancel() if self.service else None)
        if self.service:
            self.service.status_changed.connect(self.status.setText)
            self.service.progress_changed.connect(self._progress)
            self.service.management_finished.connect(self._managed)
            self.service.idle.connect(self._refresh)
        self._refresh()

    def _tab(self,tabs,title):
        widget=QWidget()
        layout=QVBoxLayout(widget)
        tabs.addTab(widget,title)
        return widget,layout

    def _combo(self,values,current):
        combo=QComboBox()
        for label,value in values:
            combo.addItem(label,value)
        combo.setCurrentIndex(max(0,combo.findData(current)))
        return combo

    def _file_row(self,edit,filter):
        row=QHBoxLayout()
        row.addWidget(edit,1)
        browse=QPushButton('Browse')
        def select():
            path,_=QFileDialog.getOpenFileName(self,'Choose local AI file','',filter)
            if path:
                edit.setText(path)
        browse.clicked.connect(select)
        row.addWidget(browse)
        return row

    def apply_to(self,c):
        import json
        c.analysis_enabled=self.enabled.isChecked()
        c.analysis_provider=self.provider.currentData()
        c.analysis_executable=self.exe.text().strip()
        c.analysis_gguf=self.gguf.text().strip()
        c.analysis_context_tokens=self.context_tokens.value()
        c.analysis_context_sentences=self.sentences.value()
        c.analysis_idle_minutes=self.idle_minutes.value()
        c.analysis_speech_style=self.speech.currentData()
        c.analysis_translation_style=self.translation.currentData()
        c.analysis_explanation_language=self.explanation.currentData()
        c.analysis_explain_slang=self.slang.isChecked()
        c.analysis_reasoning=self.reasoning.isChecked()
        c.analysis_glossary=self.glossary.toPlainText().strip()
        c.analysis_examples=json.dumps(self.example_values,ensure_ascii=False)
        c.analysis_endpoint,c.analysis_model,c.analysis_key_env=self.endpoint.text().strip(),self.model.text().strip(),self.key_env.text().strip()
        if len(c.analysis_glossary)>4000:
            raise ValueError('Keep the glossary within 4,000 characters.')
        if c.analysis_enabled and c.analysis_provider=='online':
            from ml.context_analysis import validate_endpoint
            validate_endpoint(c.analysis_endpoint)
            if not c.analysis_model or not c.analysis_key_env.isidentifier():
                raise ValueError('Online analysis requires a model ID and a valid API-key environment variable name.')
        return c

    def _manage(self,operation):
        try:
            draft=self.apply_to(replace(self.config))
            if not self.service or not self.service.manage(operation,draft):
                self.status.setText('Another analysis task is finishing. Try again shortly.')
        except ValueError as exc:
            self.status.setText(str(exc))
        self._refresh()

    def _install(self):
        if QMessageBox.question(self,'Install local AI',f'Download about {(MODEL_BYTES+RUNTIME_BYTES)/1e9:.2f} GB from official Qwen and llama.cpp repositories?\nFiles are stored in {ASSET_ROOT}. No conversation is sent.')==QMessageBox.StandardButton.Yes:
            self._manage('install')

    def _remove(self):
        path=managed_paths()[1].resolve()
        if not path.is_relative_to(ASSET_ROOT.resolve()):
            return
        if self.service and (self.service.busy or self.service.runtime.loaded):
            self.status.setText('Unload the model and wait for tasks to finish before removing it.')
            return
        if QMessageBox.question(self,'Remove local model',f'Delete only the downloaded {MODEL_FILE}? Custom models and the runtime are kept.')==QMessageBox.StandardButton.Yes:
            try:
                path.unlink(missing_ok=True)
                self.status.setText('Downloaded model removed. Install again to restore it.')
            except OSError as exc:
                self.status.setText(str(exc))

    def _progress(self,message,percent):
        self.progress.show()
        self.progress.setValue(percent)
        self.status.setText(message)

    def _managed(self,value):
        if 'error' in value:
            self.status.setText(value['error'])
        elif value.get('operation')=='install':
            self.exe.setText(value['executable'])
            self.gguf.setText(value['model'])
            self.status.setText('Installed. Click Load / verify GPU, then Apply to save settings.')
        self.progress.hide()

    def _refresh(self):
        available=self.service is not None
        busy=available and (self.service.busy or bool(self.events.property('local_translation_owned')))
        for button in (self.install,self.load,self.unload,self.remove):
            button.setEnabled(available and not busy)
        self.stop.setEnabled(bool(busy))

    def _show_examples(self):
        self.example_view.setPlainText('\n\n'.join(f"{x['source']} -> {x['target']}: {x['original']}\n{x['preferred']}" for x in self.example_values) or 'No examples saved yet.')

    def _clear_examples(self):
        if QMessageBox.question(self,'Clear learning examples','Delete all saved correction examples when you Apply these settings?')==QMessageBox.StandardButton.Yes:
            self.example_values=[]
            self.example_summary.setText('0 / 10 saved correction examples')
            self._show_examples()

    def dispose(self):
        if self.service:
            for signal,slot in ((self.service.status_changed,self.status.setText),(self.service.progress_changed,self._progress),
                (self.service.management_finished,self._managed),(self.service.idle,self._refresh)):
                signal.disconnect(slot)
