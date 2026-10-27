"""Compact feature selection, resumable downloads and verified first-run readiness."""
from dataclasses import fields
from pathlib import Path
import math,shutil
from PySide6.QtCore import Qt,Signal,QTimer,Slot
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QComboBox,QCheckBox,QScrollArea,QFrame,QStackedWidget,QProgressBar,QFileDialog,QMessageBox)
from core.components import ComponentManager,catalog
from core.onboarding import SetupPlan,inventory,disk_estimate,format_bytes,nearest_existing,component_percent
from ui.icons import icon_button

class SetupDialog(QDialog):
    component_progress=Signal(str,str,int)
    def __init__(self,config,events=None,parent=None):
        super().__init__(parent)
        from ui.model_setup import ModelJob,TaskWidget
        from ui.theme import style_for
        self.config=config;self.events=events;self.manager=ComponentManager();self.result_config=None;self.checked=None
        self._closing=False;self._detect_done=False;self._gpu_available=False;self._touched=False;self._loading=True
        self._pending_action=None;self._phase='choose';self._active_id=None;self._rows=[];self._complete=set();self._fraction={}
        self.setWindowTitle('Set up GrammAI');self.setObjectName('saveCardDialog');self.setStyleSheet(style_for(config.theme))
        area=self.screen().availableGeometry();self.resize(min(650,area.width()-48),min(780,area.height()-48))
        outer=QVBoxLayout(self);outer.setContentsMargins(24,20,24,18);outer.setSpacing(12)
        brand=QLabel('GrammAI');brand.setObjectName('field');outer.addWidget(brand)
        self.steps=QLabel();self.steps.setObjectName('hint');outer.addWidget(self.steps)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);outer.addWidget(scroll,1)
        self.pages=QStackedWidget();scroll.setWidget(self.pages);self.scroll=scroll
        choice=QWidget();box=QVBoxLayout(choice);box.setContentsMargins(0,0,4,0);box.setSpacing(10);box.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(choice)
        title=QLabel('Make GrammAI yours.');title.setObjectName('title');box.addWidget(title)
        self._hint(box,'Choose what you want to use. Add or remove models later.')
        presets=QHBoxLayout();self.recommended=QPushButton('Recommended');self.essential=QPushButton('Small download')
        for button in (self.recommended,self.essential):button.setCheckable(True);presets.addWidget(button)
        box.addLayout(presets);self.recommended.setChecked(True)
        self.recommended.clicked.connect(lambda:self.preset(True));self.essential.clicked.connect(lambda:self.preset(False))
        self.speech=QComboBox();self.speech.addItem('Whisper base · CPU / 148 MB','speech-cpu');self.speech.addItem('Whisper Turbo · CPU or GPU / 574 MB','speech-turbo')
        self.ai=QCheckBox('Learning assistant');self.fast=QCheckBox('Subtitle translation');self.fast.setChecked(True);self.backup=QCheckBox('Include Whisper base CPU backup')
        self.speech_caption=QLabel();self.translation_caption=QLabel();self.learning_caption=QLabel()
        self._feature(box,'Transcription',self.speech_caption,info='Turns audio into original speech text. A model download alone does not confirm GPU support.')
        self._feature(box,self.fast,self.translation_caption,info='NLLB translates subtitles on CPU. Contextual translation and refinement can be enabled later in Models.')
        self._feature(box,self.ai,self.learning_caption,info='Qwen3 4B explains words and context and suggests replies. The same model can power translation refinement; stored once.')
        self.hardware=QLabel('Checking this PC…');self.hardware.setObjectName('hint');self.hardware.setWordWrap(True);self.hardware.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.hardware)
        self._advanced=QWidget();advanced=QVBoxLayout(self._advanced);advanced.setContentsMargins(0,0,0,0)
        advanced_toggle=QPushButton('Advanced setup');advanced_toggle.setObjectName('secondary');advanced_toggle.setCheckable(True);advanced_toggle.toggled.connect(self._advanced.setVisible);box.addWidget(advanced_toggle);box.addWidget(self._advanced);self._advanced.hide()
        self.processing=QComboBox()
        for text,value in [('Automatic','auto'),('GPU preferred','gpu'),('CPU only','cpu')]:self.processing.addItem(text,value)
        row=QHBoxLayout();row.addWidget(QLabel('Processing'));row.addWidget(self.processing,1);advanced.addLayout(row)
        advanced.addWidget(self.speech);advanced.addWidget(self.backup)
        location=QHBoxLayout();self.folder=QLabel();self.folder.setObjectName('hint');self.folder.setWordWrap(True);self.folder.setTextFormat(Qt.TextFormat.PlainText);location.addWidget(self.folder,1)
        self.browse=icon_button('edit','Change model folder',self);self.browse.clicked.connect(self.choose_folder);location.addWidget(self.browse);advanced.addLayout(location)
        self.existing=QPushButton('Use existing models');self.existing.clicked.connect(self.existing_files);advanced.addWidget(self.existing,0,Qt.AlignmentFlag.AlignLeft)
        self._hint(advanced,'NLLB: CC-BY-NC-4.0. CPU/GPU runtimes are included automatically. No download starts until you choose Download & test.')
        downloads=QWidget();flow=QVBoxLayout(downloads);flow.setContentsMargins(0,0,4,0);flow.setSpacing(12);flow.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(downloads)
        self.download_heading=QLabel('Getting things ready.');self.download_heading.setObjectName('title');flow.addWidget(self.download_heading)
        self.transfer_status=self._hint(flow,'Download models, then test them on this PC.')
        self.overall=QProgressBar();self.overall.setRange(0,100);self.overall.setTextVisible(False);self.overall.setFixedHeight(7);self.overall.setObjectName('speechDownloadProgress');flow.addWidget(self.overall)
        self.progress_caption=self._hint(flow,'');self.download_rows={}
        for key,title in [('speech','Transcription'),('translation','Translation'),('learning','Learning assistant')]:
            frame=QFrame();frame.setObjectName('modelRoleCard');row=QHBoxLayout(frame);row.setContentsMargins(14,12,14,12)
            text=QVBoxLayout();heading=QLabel(title);heading.setObjectName('field');text.addWidget(heading);caption=QLabel();caption.setObjectName('hint');caption.setWordWrap(True);caption.setTextFormat(Qt.TextFormat.PlainText);text.addWidget(caption);row.addLayout(text,1)
            status=QLabel('Waiting');status.setObjectName('hint');status.setMinimumWidth(100);status.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row.addWidget(status);flow.addWidget(frame);self.download_rows[key]=(frame,caption,status)
        self.recovery=QFrame();self.recovery.setObjectName('modelRoleCard');recover=QVBoxLayout(self.recovery);recover.setContentsMargins(14,12,14,12)
        self.recovery_title=QLabel();self.recovery_title.setObjectName('field');recover.addWidget(self.recovery_title)
        self.recovery_note=self._hint(recover,'Saved progress stays. Retry continues the download.')
        buttons=QHBoxLayout();self.retry=QPushButton('Retry now');self.retry.clicked.connect(lambda:self.request_action('retry'));buttons.addWidget(self.retry)
        self.later=QPushButton('Set up learning later');self.later.setObjectName('secondary');self.later.clicked.connect(lambda:self.request_action('defer'));buttons.addWidget(self.later);recover.addLayout(buttons);flow.addWidget(self.recovery);self.recovery.hide()
        self.retry_cpu=QPushButton('Try CPU instead');self.retry_cpu.clicked.connect(lambda:self.request_action('cpu'));flow.addWidget(self.retry_cpu,0,Qt.AlignmentFlag.AlignLeft);self.retry_cpu.hide()
        ready_page=QWidget();ready=QVBoxLayout(ready_page);ready.setContentsMargins(0,0,4,0);ready.setSpacing(14);ready.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(ready_page)
        self.ready_title=QLabel('You’re ready to learn.');self.ready_title.setObjectName('title');ready.addWidget(self.ready_title)
        self.ready=QLabel();self.ready.setWordWrap(True);self.ready.setTextFormat(Qt.TextFormat.PlainText);self.ready.hide()
        self.ready_rows={}
        for key,title in [('speech','Transcription'),('translation','Translation'),('learning','Learning assistant')]:
            frame=QFrame();frame.setObjectName('modelRoleCard');row=QHBoxLayout(frame);row.setContentsMargins(14,12,14,12)
            labels=QVBoxLayout();label=QLabel(title);label.setObjectName('field');labels.addWidget(label)
            caption=QLabel();caption.setObjectName('hint');caption.setWordWrap(True);labels.addWidget(caption);row.addLayout(labels,1)
            state=QLabel();state.setObjectName('hint');state.setWordWrap(True);state.setMinimumWidth(160);state.setMaximumWidth(230);state.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row.addWidget(state);ready.addWidget(frame);self.ready_rows[key]=(caption,state)
        self.ready_note=self._hint(ready,'');self.ready_retry=QPushButton('Retry GPU test');self.ready_retry.clicked.connect(lambda:self.request_action('gpu'));ready.addWidget(self.ready_retry,0,Qt.AlignmentFlag.AlignLeft);self.ready_retry.hide()
        self._hint(ready,'Models and recordings stay on this PC. Change models anytime in Settings.')
        # Technical detail remains expandable on every step, not mixed into the main choices.
        details_toggle=QPushButton('Setup details');details_toggle.setObjectName('secondary');details_toggle.setCheckable(True);outer.addWidget(details_toggle)
        details=QWidget();detail_box=QVBoxLayout(details);detail_box.setContentsMargins(0,0,0,0);outer.addWidget(details);details.hide();details_toggle.toggled.connect(details.setVisible);detail_box.addWidget(self.ready)
        self.task=TaskWidget(events,self);self.task.task_footer(detail_box)
        self.total=QLabel();self.total.setObjectName('hint');self.total.setWordWrap(True);self.total.setTextFormat(Qt.TextFormat.PlainText);outer.addWidget(self.total)
        actions=QHBoxLayout();self.back=QPushButton('Back');self.continue_button=QPushButton('Download & test');self.install=QPushButton('Retry download');self.finish=QPushButton('Start GrammAI');self.finish.setEnabled(False)
        self.cancel_download=QPushButton('Cancel download');self.cancel_download.clicked.connect(lambda:self.request_action('cancel'))
        for button in (self.continue_button,self.install,self.finish):button.setObjectName('primary')
        actions.addWidget(self.back);actions.addStretch();actions.addWidget(self.cancel_download);actions.addWidget(self.continue_button);actions.addWidget(self.install);actions.addWidget(self.finish);outer.addLayout(actions)
        self.back.clicked.connect(lambda:self.request_action('back'));self.continue_button.clicked.connect(self.install_and_test);self.install.clicked.connect(self.install_and_test);self.finish.clicked.connect(self.accept_setup)
        self.component_progress.connect(self._component_changed)
        for widget in (self.processing,self.speech):widget.currentIndexChanged.connect(self.changed)
        for widget in (self.ai,self.fast,self.backup):widget.toggled.connect(self.changed)
        self._loading=False;self.show_step(0);self.changed(mark=False)
        self.detect=ModelJob(self.detect_hardware);self.detect.completed.connect(self.detected);self.detect.finished.connect(self._detection_finished);self.detect.start()
    @staticmethod
    def _hint(layout,text):
        label=QLabel(text);label.setObjectName('hint');label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(label);return label
    def _feature(self,layout,heading,caption,info):
        frame=QFrame();frame.setObjectName('modelRoleCard');body=QVBoxLayout(frame);body.setContentsMargins(14,10,14,10);body.setSpacing(5)
        header=QHBoxLayout();title=heading if isinstance(heading,QWidget) else QLabel(heading)
        if isinstance(title,QLabel):title.setObjectName('field')
        header.addWidget(title,1);button=icon_button('info','About '+(heading if isinstance(heading,str) else heading.text()),frame);button.setToolTip(info);header.addWidget(button);body.addLayout(header)
        caption.setObjectName('hint');caption.setWordWrap(True);caption.setTextFormat(Qt.TextFormat.PlainText);body.addWidget(caption);layout.addWidget(frame)
    def plan(self):return SetupPlan(self.speech.currentData(),self.processing.currentData(),self.ai.isChecked(),self.fast.isChecked(),self.backup.isChecked())
    def show_step(self,index):
        self.pages.setCurrentIndex(index);busy=bool(self.task.job)
        self.steps.setText(('Choose features  →  Download & test  →  Ready','Choose features  →  [Download & test]  →  Ready','Choose features  →  Download & test  →  [Ready]')[index])
        self.back.setVisible(index>0);self.back.setEnabled(True);self.continue_button.setVisible(index==0);self.install.setVisible(index==1 and not busy);self.finish.setVisible(index==2);self.cancel_download.setVisible(index==1 and busy)
        self.total.setVisible(index==0);self.scroll.verticalScrollBar().setValue(0)
    def preset(self,recommended,user=True):
        if user:self._touched=True
        self._loading=True
        self.recommended.setChecked(recommended);self.essential.setChecked(not recommended)
        self.speech.setCurrentIndex(1 if recommended and self._gpu_available else 0);self.ai.setChecked(recommended and self._gpu_available);self.fast.setChecked(True);self.backup.setChecked(False)
        self._loading=False;self.changed(mark=False)
    def detect_hardware(self,progress,cancelled):
        from ui.model_setup import system_info,probe_devices
        from core.local_assets import managed_paths
        info=system_info();executable=Path(self.config.analysis_executable or managed_paths()[0]);devices=[]
        if executable.is_file():
            try:devices=probe_devices(executable)
            except Exception:pass
        info['devices']=devices;return info
    @Slot(object)
    def detected(self,result):
        info=result.get('value') or {};adapters=info.get('display_adapters') or []
        self._gpu_available=bool(info.get('devices') or adapters)
        names=[d['name'] for d in info.get('devices',[])] or adapters
        self.hardware.setText(('Detected: '+', '.join(names)+' · Test pending') if names else 'Automatic processing · GPU support will be checked during setup.')
        self.hardware.setToolTip(str(info.get('cpu','CPU'))+f" / {info.get('ram_bytes',0)/1024**3:.0f} GB RAM. A device name is not proof of GPU allocation.")
        if not self._touched and not self.task.job:self.preset(True,user=False)
    @Slot()
    def _detection_finished(self):
        self._detect_done=True
        if self._closing:self.reject();return
        self.changed(mark=False)
    def changed(self,*args,mark=True):
        if self._loading:return
        if mark:self._touched=True
        self.finish.setEnabled(False);self.checked=None
        self.speech_caption.setText('Whisper Turbo · CPU or GPU · 574 MB' if self.speech.currentData()=='speech-turbo' else 'Whisper base · CPU · 148 MB')
        self.translation_caption.setText('NLLB · Fast translations on CPU · 647 MB' if self.fast.isChecked() else 'Add subtitle translation later in Settings')
        self.learning_caption.setText('Qwen3 4B · Word explanations & replies · 2.50 GB · Optional' if self.ai.isChecked() else 'Optional · Add word explanations and replies later')
        self.folder.setText('Models: '+str(self.manager.root));self.backup.setVisible(self.speech.currentData()=='speech-turbo')
        try:
            rows=inventory(self.plan(),self.manager);download,reserve=disk_estimate(rows)
            self.continue_button.setText('Download & test' if self._detect_done else 'Checking this PC…')
            self.total.setText(('Download ≈ '+format_bytes(download)+' · Allow '+str(max(1,math.ceil(reserve/1e9)))+' GB free for setup') if download else 'Existing files found · They will be checked before testing')
            self.total.setToolTip('\n'.join(catalog()[r['id']].title+(' · reuse' if r['present'] else ' · '+format_bytes(r['size']-r['saved'])+' remaining') for r in rows))
            self.continue_button.setEnabled(self._detect_done)
        except (OSError,ValueError) as exc:self.total.setText('Cannot read model inventory. Open Setup details.');self.task.status.setText(str(exc));self.continue_button.setEnabled(False)
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose model folder',str(self.manager.root))
        if not folder:return
        if any(r.get('managed') for r in self.manager.records().values()) and Path(folder).resolve()!=self.manager.root:
            if QMessageBox.question(self,'Move installed models?','Move and verify managed models in the new folder? External originals stay in place.')!=QMessageBox.StandardButton.Yes:return
            self.task.start_job(lambda p,c:self.manager.move(folder,p,c),lambda result:self.changed(mark=False))
        else:self.manager=ComponentManager(folder);self.changed()
    def existing_files(self):
        def adopted(result):
            if not result.get('error'):
                if self.manager.availability('speech-turbo')=='installed' and self.manager.availability('speech-runtime')=='installed':self.speech.setCurrentIndex(1)
                self.changed(mark=False);self.task.status.setText('Matching files found. Download & test checks the selected setup.')
        self.task.start_job(lambda p,c:self.manager.adopt(self.config),adopted)
    @staticmethod
    def _role(identifier):
        return 'learning' if identifier in ('qwen','ai-cpu','ai-vulkan') else 'translation' if identifier=='translation-fast' else 'speech'
    def install_and_test(self):
        if self.task.job:return
        self.checked=None;self.finish.setEnabled(False);self._phase='download';self._active_id=None;self._complete=set();self._fraction={}
        plan=self.plan();self._plan=plan
        try:
            self._rows=inventory(plan,self.manager);remaining,reserve=disk_estimate(self._rows)
            if shutil.disk_usage(nearest_existing(self.manager.root)).free<reserve:raise ValueError('Not enough free space. Allow '+str(math.ceil(reserve/1e9))+' GB or change the model folder.')
        except (ValueError,OSError) as exc:self.total.setText(str(exc));self.task.status.setText(str(exc));self.show_step(0);return
        self.recovery.hide();self.retry_cpu.hide();self.download_heading.setText('Getting things ready.');self.transfer_status.setText('Download models, then test CPU/GPU support.');self.overall.setRange(0,100);self.overall.setValue(0)
        self._update_rows();self._update_progress()
        def work(progress,cancelled):
            for identifier in plan.identifiers:
                if cancelled():raise InterruptedError('Cancelled; saved progress stays.')
                self.component_progress.emit(identifier,'Checking existing files' if self.manager.path(identifier) else 'Downloading',0)
                self.manager.install(identifier,lambda message,value,key=identifier:self.component_progress.emit(key,message,component_percent(key,self.manager,value)),cancelled)
                self.component_progress.emit(identifier,'Downloaded and checked',100)
            if cancelled():raise InterruptedError('Cancelled')
            self.component_progress.emit('test','Testing CPU/GPU compatibility',0)
            draft=plan.configuration(self.config)
            from ui.model_setup import test_configuration
            return dict(config=draft,test=test_configuration(draft,progress,cancelled))
        if self.task.start_job(work,self.tested):self.set_choices_enabled(False);self.show_step(1)
    def _update_rows(self):
        plan=self._plan
        for role,(frame,caption,status) in self.download_rows.items():
            frame.setVisible(role=='speech' or (role=='translation' and plan.translation) or (role=='learning' and plan.learning))
            identifiers=[r['id'] for r in self._rows if self._role(r['id'])==role]
            caption.setText('Whisper Turbo + required runtime' if role=='speech' and plan.speech=='speech-turbo' else 'Whisper base · CPU' if role=='speech' else 'NLLB · CPU' if role=='translation' else 'Qwen3 4B + required runtimes · stored once')
            done=identifiers and all(i in self._complete for i in identifiers)
            status.setText('Downloaded' if done else 'Waiting')
    def _update_progress(self):
        total=sum(r['size'] for r in self._rows);done=sum(r['size'] if r['id'] in self._complete else max(r['saved'],int(r['size']*self._fraction.get(r['id'],0)/100)) for r in self._rows)
        self.overall.setValue(min(100,int(100*done/max(1,total))));self.progress_caption.setText(format_bytes(done)+' / '+format_bytes(total)+' · '+str(min(100,int(100*done/max(1,total))))+'%')
    def _component_changed(self,identifier,message,value):
        self.task.status.setText(message)
        if identifier=='test':
            self._phase='test';self.transfer_status.setText('Files checked. Testing actual CPU/GPU model loading…');self.overall.setRange(0,0);self.recovery.hide();self.later.hide();return
        self._active_id=identifier;self._fraction[identifier]=value
        if value==100:self._complete.add(identifier)
        self._update_rows();self._update_progress()
        frame,caption,status=self.download_rows[self._role(identifier)]
        status.setText('Downloaded' if identifier in self._complete and all(r['id'] in self._complete for r in self._rows if self._role(r['id'])==self._role(identifier)) else 'Checking' if 'Checking' in message or 'Verified' in message else 'Downloading')
        from urllib.parse import urlsplit
        spec=catalog()[identifier];host=urlsplit(spec.assets[0].url).hostname
        role_title={'speech':'Transcription','translation':'Translation','learning':'Learning assistant'}[self._role(identifier)]
        self.transfer_status.setText(role_title+' · '+spec.title)
        if identifier not in self._complete:caption.setText(caption.text()+'\n'+format_bytes(int(spec.size*value/100))+' / '+format_bytes(spec.size)+' · '+host)
        reconnect='Connection interrupted' in message
        self.recovery.setVisible(reconnect);self.recovery_title.setText('Reconnecting…');self.recovery_note.setText((message[message.lower().rfind('retry'):]+'\n' if 'retry' in message.lower() else '')+'Saved progress stays. No need to start over.')
        self.later.setVisible(self._role(identifier)=='learning' and self._plan.learning)
    def set_choices_enabled(self,enabled):
        for widget in (self.speech,self.processing,self.ai,self.fast,self.backup,self.browse,self.existing,self.recommended,self.essential,self.continue_button):widget.setEnabled(enabled)
    def request_action(self,action):
        if self.task.job:self._pending_action=action;self.task.cancel_job();self.transfer_status.setText('Stopping safely; saved download progress stays.');return
        self._apply_action(action)
    def _apply_action(self,action):
        if action=='back':self.show_step(0);return
        if action=='cancel':return
        if action=='defer':self.ai.setChecked(False)
        if action in ('cpu','gpu'):self.processing.setCurrentIndex(self.processing.findData(action))
        QTimer.singleShot(0,self._restart_when_idle)
    def _restart_when_idle(self):
        from ui.model_setup import active_jobs
        if self._closing:return
        if active_jobs():QTimer.singleShot(25,self._restart_when_idle);return
        self.install_and_test()
    def tested(self,result):
        self.set_choices_enabled(True);self.overall.setRange(0,100)
        if self._closing:self.reject();return
        if self._pending_action:
            action,self._pending_action=self._pending_action,None
            if action!='cancel':self._apply_action(action);return
        if 'value' in result:
            self.checked=result['value'];value=self.checked['test'];self.finish.setEnabled(True);self.show_step(2)
            backend=value['backend'];cpu='CPU' in backend.upper();self.ready_title.setText('Ready, using CPU.' if cpu and self.checked['config'].speech_model_id!='speech-cpu' and self.checked['config'].processing_mode!='cpu' else 'You’re ready to learn.')
            c=self.checked['config'];self.ready.setText('Transcription · '+('Whisper Turbo' if c.speech_model_id=='speech-turbo' else 'Whisper base')+'\n'+backend+' · Tested\n\nTranslation · '+('NLLB / CPU · Tested' if c.translation_enabled else 'Add later')+'\n\nLearning assistant · '+(value.get('ai_status','Tested') if c.analysis_enabled else 'Add later'))
            speech_name='Whisper base backup' if 'backup' in backend.lower() else 'Whisper Turbo' if c.speech_model_id=='speech-turbo' else 'Whisper base'
            for role,caption,state in [('speech',speech_name,backend+' · Tested'),('translation','NLLB · Fast subtitles','CPU · Tested' if c.translation_enabled else 'Add later'),('learning','Qwen3 4B · Words, context & replies',value.get('ai_status','Tested') if c.analysis_enabled else 'Add later')]:
                self.ready_rows[role][0].setText(caption);self.ready_rows[role][1].setText(state)
            self.ready_note.setText(('GPU startup did not succeed. The CPU test passed.\n' if cpu and c.processing_mode!='cpu' and c.speech_model_id!='speech-cpu' else '')+('Keeps up with this short test sample.' if value['keeps_up'] else 'Passed model loading, but may not keep up. Consider a smaller model.')+'\nCompatibility/speed check only; not an accuracy score.')
            self.ready_retry.setVisible(cpu and c.speech_model_id!='speech-cpu');self.task.status.setText(value.get('speech_note','')+'\n'+f"Speech: {value['speech_ms']:.0f} ms for {value['audio_seconds']:.1f}s audio"+(f" / Translation: {value['translation_ms']:.0f} ms" if 'translation_ms' in value else ''))
        else:
            self.show_step(1);self.recovery.show();self.recovery_title.setText('Download paused.' if result.get('cancelled') else 'Setup needs attention.')
            self.recovery_note.setText('Saved progress stays. Retry to continue.' if self._phase=='download' else 'Files are kept. Check Setup details or try CPU processing.')
            self.transfer_status.setText(('Stopped while preparing '+catalog()[self._active_id].title) if self._phase=='download' and self._active_id else 'Compatibility test did not finish.')
            self.retry.setText('Resume' if result.get('cancelled') else 'Retry');self.install.setText('Resume & test' if result.get('cancelled') else 'Retry & test');self.install.hide()
            self.retry_cpu.setVisible(self._phase=='test' and self.processing.currentData()!='cpu');self.later.setVisible(bool(self._plan.learning and self._active_id and self._role(self._active_id)=='learning' and self._phase=='download'))
    def accept_setup(self):
        if not self.checked:return
        from core.preferences import save_config
        self.result_config=self.checked['config'];save_config(self.result_config)
        for field in fields(self.config):setattr(self.config,field.name,getattr(self.result_config,field.name))
        self.accept()
    def reject(self):
        from shiboken6 import isValid
        if not isValid(self):return
        self._closing=True
        if self.task.job:self._closing=True;self.task.cancel_job();return
        if not self._detect_done:
            self.detect.requestInterruption();return
        super().reject()
