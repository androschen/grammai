"""First-run setup and compact model management, sharing bounded background jobs."""
from dataclasses import fields,replace
from pathlib import Path
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QCheckBox,QProgressBar,QFileDialog,QMessageBox,QStackedWidget,QScrollArea,QFrame)
from core.components import ComponentManager,catalog
from core.hardware import system_info,probe_devices
from core.setup import required_components,select_configuration,test_configuration
from ui.icons import icon_button

_JOBS=set()


def active_jobs():return [j for j in _JOBS if j.isRunning()]
def cancel_jobs():
    for job in list(_JOBS):job.requestInterruption()


class ModelJob(QThread):
    progress=Signal(str,int)
    completed=Signal(object)
    def __init__(self,work):
        super().__init__();self.work=work
        _JOBS.add(self);self.finished.connect(self._finished)
    def _finished(self):
        _JOBS.discard(self);self.deleteLater()
    def requestInterruption(self):
        super().requestInterruption()
        abort=getattr(self,'abort',None)
        if abort:abort()
    def run(self):
        try:self.completed.emit({'value':self.work(self.progress.emit,self.isInterruptionRequested)})
        except Exception as exc:self.completed.emit({'error':str(exc),'cancelled':isinstance(exc,InterruptedError)})


class TaskWidget(QWidget):
    def __init__(self,events=None,parent=None):
        super().__init__(parent);self.events=events;self.job=None;self._callback=None
        self.status=QLabel();self.status.setObjectName('hint');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.hide()
        self.cancel=icon_button('stop','Cancel component task',self);self.cancel.hide();self.cancel.clicked.connect(self.cancel_job)
    def task_footer(self,layout):
        layout.addWidget(self.status);row=QHBoxLayout();row.addWidget(self.progress,1);row.addWidget(self.cancel);layout.addLayout(row)
    def cancel_job(self):
        if self.job:self.job.requestInterruption();self.status.setText('Cancelling safely…')
    def can_modify(self):
        if active_jobs():self.status.setText('Finish or cancel the current component task first.');return False
        if self.events:
            service=getattr(self.events,'analysis_service',None)
            idle=getattr(self.events,'comparison_allowed',lambda:True)
            if self.events.property('translation_running') or not idle() or (service and (service.busy or service.runtime.loaded)):
                self.status.setText('Pause translation, then use Manage components → Unload local AI before testing or changing files.');return False
        return True
    def start_job(self,work,callback=None):
        if not self.can_modify():return False
        self._callback=callback;self.progress.setValue(0);self.progress.show();self.cancel.show()
        self.job=ModelJob(work);self.job.progress.connect(self._progress);self.job.completed.connect(self._done);self.job.start();return True
    def _progress(self,message,value):self.status.setText(message);self.progress.setValue(value)
    def _done(self,result):
        self.cancel.hide();self.progress.hide();self.job=None
        if result.get('error'):self.status.setText(result['error'])
        else:self.status.setText('Finished.')
        callback,self._callback=self._callback,None
        if callback:callback(result)
    def dispose(self):self.cancel_job()


class ComponentsWidget(TaskWidget):
    def __init__(self,config,events,parent=None):
        super().__init__(events,parent);self.config=config;self.manager=ComponentManager()
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        header=QHBoxLayout();self.back=icon_button('back','Back to model settings',self);header.addWidget(self.back)
        title=QLabel('Manage components');title.setObjectName('field');header.addWidget(title,1);box.addLayout(header)
        reuse=QPushButton('Find installed models');reuse.clicked.connect(self.discover_existing);box.addWidget(reuse,0,Qt.AlignmentFlag.AlignLeft)
        # The component list stays visible, matching the approved mock. The
        # combo remains the selection model for existing import/repair actions.
        self.choice=QComboBox(self);self.choice.setAccessibleName('Component');self.choice.hide()
        self.cards_box=QVBoxLayout();self.cards_box.setSpacing(8);box.addLayout(self.cards_box)
        self.cards={}
        for identifier,spec in catalog().items():
            card=QFrame();card.setObjectName('componentCard');row=QHBoxLayout(card);row.setContentsMargins(8,6,8,6);row.setSpacing(8)
            select=QPushButton(spec.title);select.setObjectName('componentSelect');select.setCheckable(True)
            select.setAccessibleName('Select '+spec.title);select.clicked.connect(lambda checked=False,key=identifier:self.select_component(key))
            row.addWidget(select,1)
            state=QLabel();state.setObjectName('badge');row.addWidget(state)
            verify=icon_button('shield-check','Verify '+spec.title,card);verify.clicked.connect(lambda checked=False,key=identifier:self.verify_component(key));row.addWidget(verify)
            self.cards[identifier]=(card,select,state,verify);self.cards_box.addWidget(card)

        self.details=QLabel();self.details.setObjectName('hint');self.details.setWordWrap(True);self.details.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.details)
        row=QHBoxLayout();self.install=QPushButton('Install / resume');self.install.setObjectName('primary');self.verify=QPushButton('Verify');self.repair=QPushButton('Repair');self.remove=icon_button('trash','Remove selected managed component',self)
        for b in (self.install,self.verify,self.repair,self.remove):row.addWidget(b)
        box.addLayout(row)
        files=QHBoxLayout();self.import_file=QPushButton('Use existing file');self.location=QPushButton('Change model location');files.addWidget(self.import_file);files.addWidget(self.location);box.addLayout(files)
        self.folder=QLabel();self.folder.setObjectName('hint');self.folder.setWordWrap(True);self.folder.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.folder)
        self.unload=QPushButton('Unload local AI');self.unload.clicked.connect(self._unload);box.addWidget(self.unload,0,Qt.AlignmentFlag.AlignLeft)
        note=QLabel('Model files are separate from the app. Qwen is shared by translation and learning. Windows manages pronunciation voices.');note.setWordWrap(True);note.setObjectName('hint');box.addWidget(note)
        self.task_footer(box);box.addStretch()
        self.choice.currentIndexChanged.connect(self.describe)
        self.install.clicked.connect(lambda:self.operation('install'));self.verify.clicked.connect(lambda:self.operation('verify'));self.repair.clicked.connect(lambda:self.operation('repair'));self.remove.clicked.connect(self.delete_component);self.import_file.clicked.connect(self.import_component);self.location.clicked.connect(self.move)
        self.refresh()
    def refresh(self):
        selected=self.choice.currentData();self.choice.blockSignals(True);self.choice.clear()
        for identifier,spec in catalog().items():
            try:path=self.manager.path(identifier)
            except ValueError as exc:self.status.setText(str(exc));path=None
            self.choice.addItem(spec.title+(' · installed' if path else ' · not installed'),identifier)
            card,button,state,verify=self.cards[identifier]
            button.setText(spec.title+'\n'+', '.join(spec.roles)+f' · {spec.size/1e6:.0f} MB')
            state.setText('Installed' if path else 'Available');verify.setEnabled(bool(path))

        self.choice.setCurrentIndex(max(0,self.choice.findData(selected)));self.choice.blockSignals(False);self.describe()
    def select_component(self,identifier):
        self.choice.setCurrentIndex(self.choice.findData(identifier));self.describe()
    def verify_component(self,identifier):
        self.select_component(identifier);self.operation('verify')
    def describe(self,*args):
        identifier=self.choice.currentData()
        if not identifier:return
        spec=catalog()[identifier]
        for key,(_,button,_,_) in self.cards.items():button.setChecked(key==identifier)
        try:record=self.manager.records().get(identifier,{});path=self.manager.path(identifier)
        except ValueError as exc:self.status.setText(str(exc));return
        state='Managed installation' if record.get('managed') else 'External files · retained in place' if path else 'Download required'
        self.details.setText(spec.title+f' · {state}\n{spec.size/1e6:.1f} MB download · {spec.publisher}\nLicense: {spec.license} · used by '+', '.join(spec.roles))
        self.details.setToolTip(str(path or 'Pinned version: '+spec.version));self.folder.setText('Model folder: '+str(self.manager.root))
        service=getattr(self.events,'analysis_service',None) if self.events else None
        self.unload.setVisible(bool(service and service.runtime.loaded))
        self.remove.setEnabled(bool(record.get('managed')));self.verify.setEnabled(bool(path));self.repair.setEnabled(bool(record));self.install.setEnabled(not bool(path) and not bool(record.get('managed')))
    def discover_existing(self):
        self.start_job(lambda p,c:self.manager.adopt(self.config),lambda result:self.refresh())
    def operation(self,name):
        identifier=self.choice.currentData()
        if name=='repair' and QMessageBox.question(self,'Repair component?','Download and verify a replacement? External originals will be kept.')!=QMessageBox.StandardButton.Yes:return
        self.start_job(lambda p,c:getattr(self.manager,name)(identifier,p,c),lambda result:self.refresh())
    def import_component(self):
        identifier=self.choice.currentData();spec=catalog()[identifier]
        path,_=QFileDialog.getOpenFileName(self,'Choose '+spec.entry,'','Files ('+spec.entry+')')
        if not path:return
        if Path(path).name!=spec.entry:self.status.setText('Choose '+spec.entry);return
        def work(progress,cancelled):
            if spec.kind!='runtime':
                from core.components import digest
                for asset in spec.assets:
                    f=Path(path).parent/asset.name
                    if not f.is_file() or f.stat().st_size!=asset.size or digest(f,cancelled)!=asset.sha:raise ValueError('File does not match the pinned component. Advanced settings still support custom models.')
            return self.manager.register(identifier,path)
        self.start_job(work,lambda result:self.refresh())
    def _unload(self):
        service=getattr(self.events,'analysis_service',None) if self.events else None
        if service and service.manage('unload',self.config):self.status.setText('Unloading local AI. Retry your component action when it finishes.')
        else:self.status.setText('Pause live translation first, or finish the active AI request.')
    def delete_component(self):
        identifier=self.choice.currentData()
        from core.components import resolve
        referenced=any(Path(value).resolve()==self.manager.path(identifier) for value in (self.config.vulkan_model,self.config.vulkan_executable,self.config.analysis_gguf,self.config.analysis_executable) if value)
        used=referenced or (identifier==self.config.speech_model_id or (identifier=='qwen' and self.config.learning_model_id=='qwen') or (identifier=='translation-fast' and self.config.translation_enabled and self.config.translation_mode=='fast') or (identifier=='speech-runtime' and self.config.speech_model_id=='speech-turbo') or (identifier in ('ai-cpu','ai-vulkan') and self.config.learning_model_id=='qwen'))
        if used:self.status.setText('Choose and save another model before removing a selected component.');return
        if QMessageBox.question(self,'Remove component?','Remove only this managed component? Cards, recordings and external files stay.')!=QMessageBox.StandardButton.Yes:return
        self.start_job(lambda p,c:self.manager.remove(identifier),lambda result:self.refresh())
    def move(self):
        destination=QFileDialog.getExistingDirectory(self,'Choose model folder',str(self.manager.root))
        if not destination:return
        if QMessageBox.question(self,'Move managed models?','Copy, verify and move managed components to:\n'+destination+'\nExternal models, cards and recordings stay in place.')!=QMessageBox.StandardButton.Yes:return
        self.start_job(lambda p,c:self.manager.move(destination,p,c),lambda result:self.refresh())


class SetupDialog(QDialog):
    def __init__(self,config,events=None,parent=None):
        super().__init__(parent);self.config=config;self.events=events;self.manager=ComponentManager();self.result_config=None;self.checked=None;self._closing=False;self._detect_done=False
        self.setWindowTitle('Set up GrammAI');self.setObjectName('saveCardDialog');self.resize(min(630,self.screen().availableGeometry().width()-48),min(740,self.screen().availableGeometry().height()-48))
        outer=QVBoxLayout(self);outer.setContentsMargins(22,18,22,18);outer.setSpacing(14)
        heading=QLabel('Set up for your PC');heading.setObjectName('title');outer.addWidget(heading)
        self.steps=QLabel('Your PC  →  Components  →  Ready');self.steps.setObjectName('hint');outer.addWidget(self.steps)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);outer.addWidget(scroll,1)
        self.pages=QStackedWidget();scroll.setWidget(self.pages)
        pc=QWidget();pc_box=QVBoxLayout(pc);pc_box.setContentsMargins(0,0,4,0);pc_box.setSpacing(16);pc_box.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(pc)
        self.hardware=QLabel('Checking this PC…');self.hardware.setWordWrap(True);self.hardware.setTextFormat(Qt.TextFormat.PlainText);pc_box.addWidget(self.hardware)
        lead=QLabel('Choose a starting point. You can review every component before downloading.');lead.setWordWrap(True);lead.setObjectName('hint');pc_box.addWidget(lead)
        self.recommended=QPushButton('Recommended\nSpeech, translation and optional learning AI');self.recommended.setCheckable(True);self.recommended.setChecked(True);self.recommended.setObjectName('primary');pc_box.addWidget(self.recommended)
        self.essential=QPushButton('Essential\nCompact speech first · add translation and AI later');self.essential.setCheckable(True);pc_box.addWidget(self.essential)
        self.recommended.clicked.connect(lambda:self.preset(True));self.essential.clicked.connect(lambda:self.preset(False))
        self.existing=QPushButton('Use existing files');self.existing.clicked.connect(self.existing_files);pc_box.addWidget(self.existing,0,Qt.AlignmentFlag.AlignLeft)
        note=QLabel('Hardware detection is a suggestion. Acceleration is enabled only after the selected runtime passes its test.');note.setWordWrap(True);note.setObjectName('hint');pc_box.addWidget(note)
        component=QWidget();box=QVBoxLayout(component);box.setContentsMargins(0,0,4,0);box.setSpacing(12);box.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(component)
        caption=QLabel('Choose what to install');caption.setObjectName('field');box.addWidget(caption)
        self.processing=QComboBox();self.processing.addItem('Automatic · allow installed CPU fallback','auto');self.processing.addItem('CPU only','cpu');self.processing.addItem('GPU preferred · requires a working GPU','gpu');box.addWidget(self.processing)
        self.speech=QComboBox();self.speech.addItem('Whisper base · compact CPU speech','speech-cpu');self.speech.addItem('Whisper large-v3-turbo · GPU speech','speech-turbo');box.addWidget(self.speech)
        self.ai=QCheckBox('Contextual translation & learning · shared Qwen model');box.addWidget(self.ai)
        self.fast=QCheckBox('Use fast CPU translation · NLLB (instead of contextual AI)');self.fast.setChecked(True);box.addWidget(self.fast)
        self.backup=QCheckBox('Include CPU backups · shared AI weights are reused');box.addWidget(self.backup)
        self.total=QLabel();self.total.setWordWrap(True);self.total.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.total)
        location=QHBoxLayout();self.folder=QLabel();self.folder.setWordWrap(True);self.folder.setTextFormat(Qt.TextFormat.PlainText);location.addWidget(self.folder,1);self.browse=icon_button('edit','Choose model download folder',self);location.addWidget(self.browse);box.addLayout(location)
        notice=QLabel('Models download only after Install & test. Existing compatible files are reused. App updates keep your models.');notice.setObjectName('hint');notice.setWordWrap(True);box.addWidget(notice)
        ready_page=QWidget();ready_box=QVBoxLayout(ready_page);ready_box.setContentsMargins(0,0,4,0);ready_box.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(ready_page)
        done=QLabel('Ready to start');done.setObjectName('title');ready_box.addWidget(done)
        self.ready=QLabel();self.ready.setWordWrap(True);self.ready.setTextFormat(Qt.TextFormat.PlainText);ready_box.addWidget(self.ready)
        self.task=TaskWidget(events,self);self.task.task_footer(outer)
        actions=QHBoxLayout();self.back=QPushButton('Back');self.continue_button=QPushButton('Continue');self.continue_button.setObjectName('primary');self.install=QPushButton('Install & test');self.install.setObjectName('primary');self.finish=QPushButton('Start GrammAI');self.finish.setObjectName('primary');self.finish.setEnabled(False)
        actions.addWidget(self.back);actions.addStretch();actions.addWidget(self.continue_button);actions.addWidget(self.install);actions.addWidget(self.finish);outer.addLayout(actions)
        self.back.clicked.connect(lambda:self.show_step(max(0,self.pages.currentIndex()-1)));self.continue_button.clicked.connect(lambda:self.show_step(1))
        self.install.clicked.connect(self.install_and_test);self.finish.clicked.connect(self.accept_setup);self.browse.clicked.connect(self.choose_folder)
        for w in (self.processing,self.speech):w.currentIndexChanged.connect(self.changed)
        for w in (self.ai,self.fast,self.backup):w.toggled.connect(self.changed)
        self._gpu_available=False;self.show_step(0)
        self.continue_button.setEnabled(False);self.recommended.setEnabled(False);self.essential.setEnabled(False)
        self.changed();self.detect=ModelJob(self.detect_hardware);self.detect.completed.connect(self.detected);self.detect.start()
    def show_step(self,index):
        self.pages.setCurrentIndex(index);self.back.setVisible(index>0);self.continue_button.setVisible(index==0);self.install.setVisible(index==1);self.finish.setVisible(index==2)
        self.steps.setText(('Your PC  →  Components  →  Ready','Your PC  →  [Components]  →  Ready','Your PC  →  Components  →  [Ready]')[index])
    def preset(self,recommended):
        self.recommended.setChecked(recommended);self.essential.setChecked(not recommended)
        self.speech.setCurrentIndex(1 if recommended and self._gpu_available else 0);self.ai.setChecked(recommended and self._gpu_available);self.fast.setChecked(recommended and not self._gpu_available);self.backup.setChecked(False)
        self.changed()
    def detect_hardware(self,progress,cancelled):
        info=system_info()
        from core.local_assets import managed_paths
        executable=Path(self.config.analysis_executable or managed_paths()[0]);devices=[]
        if executable.is_file():
            try:devices=probe_devices(executable)
            except Exception:pass
        info['devices']=devices;return info
    def detected(self,result):
        self._detect_done=True
        self.continue_button.setEnabled(True);self.recommended.setEnabled(True);self.essential.setEnabled(True)
        info=result.get('value') or {};self.hardware.setText(str(info.get('cpu','CPU'))+' · '+f"{info.get('ram_bytes',0)/1024**3:.0f} GB RAM"+'\n'+('GPU available: '+info['devices'][0]['name'] if info.get('devices') else 'GPU support will be checked after installing a runtime. CPU setup is available.'))
        self._gpu_available=bool(info.get('devices'))
        self.preset(self.recommended.isChecked())
    def changed(self,*args):
        self.finish.setEnabled(False);self.checked=None
        ids=required_components(self.speech.currentData(),self.processing.currentData(),self.ai.isChecked(),self.fast.isChecked(),self.backup.isChecked())
        specs=catalog();missing=[i for i in ids if not self.manager.path(i)]
        self.total.setText('To download: '+f'{sum(specs[i].size for i in missing)/1e6:.1f} MB'+'\n'+'\n'.join(specs[i].title+' · '+(f'{specs[i].size/1e6:.1f} MB' if i in missing else 'reuse existing files') for i in ids)+( '\nNLLB model license: CC-BY-NC-4.0' if self.fast.isChecked() else ''))
        self.folder.setText('Model folder: '+str(self.manager.root));self.backup.setVisible(self.speech.currentData()=='speech-turbo')
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose model download folder',str(self.manager.root))
        if not folder:return
        if any(record.get('managed') for record in self.manager.records().values()) and Path(folder).resolve()!=self.manager.root:
            if QMessageBox.question(self,'Move installed managed models?','Move and verify existing managed components in the new folder? External originals stay in place.')!=QMessageBox.StandardButton.Yes:return
            self.task.start_job(lambda p,c:self.manager.move(folder,p,c),lambda result:self.changed())
        else:self.manager=ComponentManager(folder);self.changed()
    def existing_files(self):
        # Reuse recognized installed files without copying shared caches or changing preferences.
        def adopt(p,c):self.manager.adopt(self.config);return True
        def adopted(result):
            if not result.get('error'):
                if self.manager.path('speech-turbo') and self.manager.path('speech-runtime'):self.speech.setCurrentIndex(1)
                self.ai.setChecked(bool(self.manager.path('qwen') and self.manager.path('ai-vulkan')));self.fast.setChecked(not self.ai.isChecked());self.changed();self.show_step(1)
        if not self.task.start_job(adopt,adopted):return
        self.task.status.setText('Scanning recognized existing locations. For custom files, use Models > Advanced after setup.')
    def install_and_test(self):
        if self.task.job:return
        speech,processing=self.speech.currentData(),self.processing.currentData();ai,fast,backup=self.ai.isChecked(),self.fast.isChecked(),self.backup.isChecked()
        ids=required_components(speech,processing,ai,fast,backup)
        def work(progress,cancelled):
            for identifier in ids:self.manager.install(identifier,progress,cancelled)
            draft=select_configuration(self.config,speech,processing,ai,fast)
            return dict(config=draft,test=test_configuration(draft,progress,cancelled))
        if self.task.start_job(work,self.tested):
            self.set_choices_enabled(False);self.steps.setText('Your PC  →  Installing & testing  →  Ready')
    def set_choices_enabled(self,enabled):
        for w in (self.speech,self.processing,self.ai,self.fast,self.backup,self.browse,self.existing,self.install,self.back,self.continue_button):w.setEnabled(enabled)
    def tested(self,result):
        self.set_choices_enabled(True)
        if 'value' in result:
            self.checked=result['value'];value=self.checked['test'];self.finish.setEnabled(True)
            self.show_step(2)
            self.ready.setText('Speech recognition: '+value['backend']+'\nTranslation: '+('Contextual local AI' if self.checked['config'].translation_mode=='context' else 'Fast CPU translation' if self.checked['config'].translation_enabled else 'Add later')+'\nLearning assistant: '+value.get('ai_status','Add later')+'\nPronunciation: installed Windows voices')
            self.task.status.setText(f"Speech: {value['backend']} · {value['speech_ms']:.0f} ms for {value['audio_seconds']:.1f}s audio\n"+('Keeps up with this test sample.' if value['keeps_up'] else 'Loads successfully but may not keep up. Choose a smaller speech model.')+(f"\nTranslation: {value['translation_ms']:.0f} ms" if 'translation_ms' in value else '')+'\n'+value.get('ai_status','Learning AI not installed')+'\nCompatibility/speed check only; this does not measure language accuracy.')
        if self._closing:self.reject()
    def accept_setup(self):
        if not self.checked:return
        from core.preferences import save_config
        self.result_config=self.checked['config'];save_config(self.result_config)
        for field in fields(self.config):setattr(self.config,field.name,getattr(self.result_config,field.name))
        self.accept()
    def reject(self):
        if self.task.job:
            self._closing=True;self.task.cancel_job();return
        if not self._detect_done and self.detect.isRunning():self.detect.requestInterruption();self._closing=True;self.detect.finished.connect(self.reject);return
        super().reject()
