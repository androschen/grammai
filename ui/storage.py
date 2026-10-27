"""Compact learning storage with reviewed cleanup and explicit local backups."""
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QObject,QRunnable,QThreadPool,Signal,Slot,QTimer,QUrl,Qt,QRectF
from PySide6.QtGui import QDesktopServices,QPainter,QColor,QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QMessageBox,
    QComboBox,QFrame,QDialog,QFileDialog,QCheckBox)
from core.preferences import data_dir,write_json
from core.phrasebook import Phrasebook
from ui.icons import icon_button,set_button_icon


def size_text(value):
    if value>=1024**3:return f'{value/1024**3:.2f} GB'
    if value>=1024**2:return f'{value/1024**2:.1f} MB'
    return f'{value/1024:.1f} KB'


class ScanSignals(QObject):ready=Signal(object)

class ModelScan(QRunnable):
    def __init__(self,config):super().__init__();self.signals=ScanSignals();self.config=replace(config)
    def run(self):
        try:
            from core.storage_metrics import scan_model_storage
            result=scan_model_storage(self.config)
        except Exception as exc:result={'error':str(exc)}
        self.signals.ready.emit(result)


class StorageGauge(QWidget):
    def __init__(self,theme,parent=None):
        super().__init__(parent);self.used=self.unused=0;self.limit=1;self.theme=theme;self.setFixedHeight(7);self.setAccessibleName('Saved recording storage')
    def set_theme(self,theme):self.theme=theme;self.update()
    def set_usage(self,total,unused,limit):
        self.used=max(0,total-unused);self.unused=unused;self.limit=max(1,limit)
        self.setAccessibleDescription(f'{size_text(total)} of {size_text(limit)}; {size_text(unused)} unused');self.update()
    def paintEvent(self,event):
        from ui.theme_tokens import palette_for
        colors=palette_for(self.theme);p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect());path=QPainterPath();path.addRoundedRect(rect,3,3);p.setClipPath(path);p.fillRect(rect,QColor(colors['line']))
        used=min(self.width(),self.width()*self.used/self.limit);unused=min(self.width()-used,self.width()*self.unused/self.limit)
        p.fillRect(QRectF(0,0,used,self.height()),QColor(colors['accent']));p.fillRect(QRectF(used,0,unused,self.height()),QColor(colors['muted']));p.end()


class StorageReview(QDialog):
    """Small, nonblocking review; an opened preview never changes disk data."""
    def __init__(self,title,parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.setObjectName('saveCardDialog');self.setWindowModality(Qt.WindowModality.WindowModal);self.resize(460,280)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(20,18,20,18);self.box.setSpacing(12)
        heading=QLabel(title);heading.setObjectName('field');self.box.addWidget(heading)
        self.message=QLabel();self.message.setWordWrap(True);self.message.setTextFormat(Qt.TextFormat.PlainText);self.box.addWidget(self.message)
        self.breakdown=QFrame();self.breakdown.setObjectName('modelRoleCard');self.rows=QVBoxLayout(self.breakdown);self.rows.setContentsMargins(12,8,12,8);self.rows.setSpacing(10);self.breakdown.hide();self.box.addWidget(self.breakdown)
        self.detail=QLabel();self.detail.setObjectName('hint');self.detail.setWordWrap(True);self.detail.setTextFormat(Qt.TextFormat.PlainText);self.box.addWidget(self.detail)
        self.confirm_check=QCheckBox('I understand the saved cards will be deleted.');self.confirm_check.hide();self.box.addWidget(self.confirm_check)
        self.status=QLabel();self.status.setObjectName('hint');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);self.box.addWidget(self.status)
        row=QHBoxLayout();row.addStretch();self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(self.reject);row.addWidget(self.cancel)
        self.confirm=QPushButton();self.confirm.setObjectName('primary');row.addWidget(self.confirm);self.box.addLayout(row)
    def add_row(self,label,value):
        self.breakdown.show();row=QHBoxLayout();caption=QLabel(label);caption.setWordWrap(True);row.addWidget(caption,1)
        state=QLabel(value);state.setObjectName('hint');state.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row.addWidget(state);self.rows.addLayout(row);self.breakdown.setMinimumHeight(16+28*self.rows.count())
    def working(self,text):self.status.setText(text);self.confirm.setEnabled(False);self.cancel.setEnabled(False)


class StorageWidget(QWidget):
    manage_models_requested=Signal()
    def __init__(self,config,events,replays=None,parent=None):
        super().__init__(parent);self.config,self.events,self.replays=config,events,replays;self.phrasebook=Phrasebook()
        self._scanning=False;self._audio_scanning=False;self._models_scanned=False;self._active=False;self._disposed=False;self._audio_stats=None;self._audio_rescan=False;self._mutation=False;self._book_key=None
        self.preview_dialog=None;self.backup_dialog=None;self._backup_busy=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        header=QHBoxLayout();title=QLabel('Storage');title.setObjectName('field');header.addWidget(title,1)
        refresh=icon_button('refresh','Refresh storage usage',self);refresh.clicked.connect(self.refresh_all);header.addWidget(refresh)
        folder=icon_button('folder','Open cards and recordings folder',self);folder.clicked.connect(self._open_folder);header.addWidget(folder);layout.addLayout(header)
        recordings,body=self._card(layout);top=QHBoxLayout();heading=QLabel('Saved recordings');heading.setObjectName('field');top.addWidget(heading,1)
        top.addWidget(QLabel('Limit'));self.audio_limit=QComboBox()
        for amount in (100,250,500):self.audio_limit.addItem(f'{amount} MB',amount)
        self.audio_limit.setCurrentIndex(max(0,self.audio_limit.findData(config.saved_audio_limit_mb)));self.audio_limit.setAccessibleName('Saved audio storage limit');top.addWidget(self.audio_limit)
        info=icon_button('info','About the recording limit',self);info.setToolTip('At the limit, save new cards as text only or increase the limit. Existing card recordings are never automatically deleted.');top.addWidget(info);body.addLayout(top)
        self.saved_audio=self._label(body,'Check storage to see saved recordings.');self.gauge=StorageGauge(config.theme,self);body.addWidget(self.gauge)
        self.audio_breakdown=self._label(body,'');self.audio_warning=self._label(body,'');self.audio_warning.hide()
        actions=QHBoxLayout();note=QLabel('Recordings linked to cards stay protected.');note.setObjectName('hint');note.setWordWrap(True);actions.addWidget(note,1)
        self.clean_audio=QPushButton('Clean up');self.clean_audio.setEnabled(False);self.clean_audio.clicked.connect(self._clean_audio);actions.addWidget(self.clean_audio);body.addLayout(actions)
        deck,body=self._card(layout);row=QHBoxLayout();labels=QVBoxLayout();title=QLabel('Learning deck');title.setObjectName('field');labels.addWidget(title)
        self.phrases=self._label(labels,'');row.addLayout(labels,1);self.backup=QPushButton('Back up');set_button_icon(self.backup,'archive');self.backup.clicked.connect(self._backup_preview);row.addWidget(self.backup);body.addLayout(row)
        models,body=self._card(layout);row=QHBoxLayout();labels=QVBoxLayout();title=QLabel('Models & runtimes');title.setObjectName('field');labels.addWidget(title)
        self.models=self._label(labels,'Not scanned yet');row.addLayout(labels,1);self.manage_models=QPushButton('Manage models');self.manage_models.clicked.connect(self.manage_models_requested.emit);row.addWidget(self.manage_models);body.addLayout(row)
        toggle=QPushButton('Advanced');toggle.setObjectName('secondary');toggle.setCheckable(True);layout.addWidget(toggle)
        self.advanced=QWidget();advanced=QVBoxLayout(self.advanced);advanced.setContentsMargins(0,0,0,0);advanced.setSpacing(10);layout.addWidget(self.advanced);self.advanced.hide();toggle.toggled.connect(self.advanced.setVisible)
        self.ram=QLabel();self.ram.setObjectName('hint');self.ram.setWordWrap(True)
        self.clear_replay=icon_button('trash','Clear temporary replay memory',self);self.clear_replay.setEnabled(replays is not None);self.clear_replay.clicked.connect(events.replay_clear_requested.emit)
        row=QHBoxLayout();row.addWidget(self.ram,1);row.addWidget(self.clear_replay);advanced.addLayout(row)
        self._label(advanced,'RAM only · Expires after 60 seconds, a device change, or Quit.')
        self.benchmarks=QLabel();self.benchmarks.setObjectName('hint');self.benchmarks.setWordWrap(True);clear=icon_button('trash','Clear benchmark summaries',self);clear.clicked.connect(self._clear_benchmarks)
        row=QHBoxLayout();row.addWidget(self.benchmarks,1);row.addWidget(clear);advanced.addLayout(row)
        location=self._label(advanced,'Data location: '+str(data_dir()));location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label(advanced,'Shared clips are stored once. Cards: up to 1,000 entries / 2 MB. Model sizes include recognized files and caches; partial scans are marked.')
        self.delete_cards=QPushButton('Delete all learning cards…');self.delete_cards.setObjectName('dangerLink');self.delete_cards.clicked.connect(self._clear_phrases);advanced.addWidget(self.delete_cards,0,Qt.AlignmentFlag.AlignLeft)
        self.feedback=self._label(layout,'');layout.addStretch()
        self.audio_limit.currentIndexChanged.connect(self._limit_changed)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.refresh)
        events.state_changed.connect(self._state_changed);self.refresh()
    @staticmethod
    def _card(layout):
        frame=QFrame();frame.setObjectName('modelRoleCard');box=QVBoxLayout(frame);box.setContentsMargins(16,14,16,14);box.setSpacing(10);layout.addWidget(frame);return frame,box
    @staticmethod
    def _label(layout,text):
        label=QLabel(text);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText);label.setObjectName('hint');layout.addWidget(label);return label
    def set_theme(self,theme):self.gauge.set_theme(theme)
    def _state_changed(self,state):self.set_theme(self.config.theme)
    def set_active(self,active):
        self._active=active
        if active and not self._disposed:
            self.refresh();self.scan_audio()
            if not self._models_scanned:self.scan_models()
            self.timer.start()
        else:self.timer.stop()
    def dispose(self):
        if self._disposed:return
        self._disposed=True;self.set_active(False)
        for dialog in (self.preview_dialog,self.backup_dialog):
            if dialog:dialog.reject()
        try:self.events.state_changed.disconnect(self._state_changed)
        except (RuntimeError,TypeError):pass
    def refresh(self):
        if self._disposed:return
        stats=self.replays.stats() if self.replays else {'bytes':0,'clips':0}
        self.ram.setText('Temporary replay · '+size_text(stats['bytes'])+f" · {stats['clips']} sentences")
        try:
            stats=self.phrasebook.stats();self.phrases.setText(f"{stats['count']} cards · Notes, explanations & original audio");self.phrases.setToolTip(size_text(stats['bytes'])+' of 2 MB card text')
            file=data_dir()/'phrases.json';key=(file.stat().st_mtime_ns,file.stat().st_size) if file.is_file() else None
            if key!=self._book_key:
                self._book_key=key
                if self._active:self.scan_audio()
            self.backup.setEnabled(not self._backup_busy);self.delete_cards.setEnabled(not self._mutation and stats['count']>0)
        except (ValueError,OSError) as exc:
            self.phrases.setText('Deck unavailable · '+str(exc));self.backup.setEnabled(False);self.delete_cards.setEnabled(False);self.clean_audio.setEnabled(False)
        try:
            file=data_dir()/'benchmarks.json';self.benchmarks.setText('Test summaries · '+size_text(file.stat().st_size if file.is_file() else 0))
        except OSError:self.benchmarks.setText('Test summaries · Unavailable')
    def refresh_all(self):self.refresh();self.scan_audio();self.scan_models()
    def _limit_changed(self):
        if self._audio_stats:self._show_audio(self._audio_stats)
    def _show_audio(self,result):
        limit=(self.audio_limit.currentData() or 250)*1024**2
        self.saved_audio.setText(size_text(result['bytes'])+' of '+str(self.audio_limit.currentData())+f" MB · {result['clips']} recordings")
        self.gauge.set_usage(result['bytes'],result['unused_bytes'],limit)
        self.audio_breakdown.setText('In cards · '+size_text(result['bytes']-result['unused_bytes'])+'     Unused · '+size_text(result['unused_bytes']))
        self.audio_warning.setText('Audio storage is full. Save new cards as text only, increase the limit, or remove unused recordings.');self.audio_warning.setVisible(result['bytes']>=limit)
        self.clean_audio.setText('Clean up'+(' · '+size_text(result['unused_bytes']) if result['unused_bytes'] else ''));self.clean_audio.setEnabled(result['unused_bytes']>0 and not self._mutation and not self._audio_scanning)
    def scan_audio(self,clean=False):
        if clean:self._clean_audio();return
        if self._disposed or self._mutation:return
        if self._audio_scanning:self._audio_rescan=True;return
        from core.storage_data import audio_snapshot
        from audio.tasks import AudioTask
        self._audio_scanning=True;self.clean_audio.setEnabled(False)
        limit=self.audio_limit.currentData() or 250
        self._audio_task=AudioTask(lambda:audio_snapshot(limit));self._audio_task.signals.ready.connect(self._audio_done);QThreadPool.globalInstance().start(self._audio_task)
    @Slot(object,object)
    def _audio_done(self,result,error):
        self._audio_scanning=False
        if self._disposed:return
        if error:self._audio_stats=None;self.saved_audio.setText('Audio storage unavailable · '+error);self.clean_audio.setEnabled(False);return
        self._audio_stats=result;self._show_audio(result)
        if self._audio_rescan:self._audio_rescan=False;self.scan_audio()
    def _clean_audio(self):
        if not self._audio_stats or self._mutation:return
        stats=self._audio_stats;files=[dict(x) for x in stats['unused_files']]
        if not files:return
        dialog=StorageReview('Remove unused recordings?',self);self.preview_dialog=dialog
        dialog.message.setText('These recordings are no longer linked to any card.')
        for label,value in [('Unused recordings',f'{len(files)} files / '+size_text(stats['unused_bytes'])),('Cards & notes','Kept'),('Audio used by cards','Kept'),('Models','Kept')]:dialog.add_row(label,value)
        dialog.detail.setText('Reviewed unused recordings will be permanently removed.');dialog.confirm.setText('Remove '+size_text(stats['unused_bytes']))
        dialog.confirm.clicked.connect(lambda:self._remove_reviewed(dialog,files));dialog.open()
    def _remove_reviewed(self,dialog,files):
        if self._mutation:return
        from core.storage_data import cleanup_recordings
        from audio.tasks import AudioTask
        self._mutation=True;self.clean_audio.setEnabled(False);self.delete_cards.setEnabled(False);dialog.working('Rechecking references and removing reviewed unused recordings…')
        limit=self.audio_limit.currentData() or 250
        self._cleanup_task=AudioTask(lambda:cleanup_recordings(files,limit));self._cleanup_task.signals.ready.connect(lambda result,error:self._cleanup_done(dialog,result,error));QThreadPool.globalInstance().start(self._cleanup_task)
    def _cleanup_done(self,dialog,result,error):
        self._mutation=False
        if self._disposed:return
        if error:
            self.feedback.setText('Cleanup stopped · '+error);dialog.status.setText(error);dialog.cancel.setEnabled(True);self.scan_audio();return
        dialog.accept();self._audio_stats=result['stats'];self._show_audio(result['stats']);self.refresh();self.feedback.setText(size_text(result['removed_bytes'])+f" removed · {result['removed_files']} files. Cards and linked audio kept.")
    def invalidate_models(self):
        self._models_scanned=False
        if self._active:self.scan_models()
    def scan_models(self):
        if self._disposed or self._scanning:return
        self._scanning=True;self.models.setText('Checking recognized model files…');self._task=ModelScan(self.config);self._task.signals.ready.connect(self._model_sizes);QThreadPool.globalInstance().start(self._task)
    @Slot(object)
    def _model_sizes(self,result):
        self._scanning=False
        if self._disposed:return
        if result.get('error'):self.models.setText('Model storage unavailable · '+result['error']);return
        self._models_scanned=True
        text=('At least ' if result['partial'] else '')+size_text(result['bytes'])+' · Shared files counted once'
        if result.get('download_bytes'):text+='\n'+size_text(result['download_bytes'])+' downloaded / partial files retained for resume'
        if result['partial']:text+=' · Partial scan'
        self.models.setText(text)
    def _backup_preview(self):
        if self._backup_busy:return
        try:count=len(self.phrasebook.items(force=True))
        except (ValueError,OSError) as exc:self.feedback.setText('Cannot back up deck · '+str(exc));return
        dialog=StorageReview('Back up your learning',self);self.backup_dialog=dialog
        dialog.message.setText('Save one local backup containing your cards and their original recordings.')
        for label,value in [('Cards, notes & explanations',f'{count} cards'),('Linked original audio','Included'),('Model downloads','Not included')]:dialog.add_row(label,value)
        dialog.detail.setText('Choose where to save a ZIP backup. Settings and unused audio are excluded. Missing recordings are reported.');dialog.confirm.setText('Save backup…');dialog.confirm.clicked.connect(lambda:self._choose_backup(dialog));dialog.open()
    def _choose_backup(self,dialog):
        file,_=QFileDialog.getSaveFileName(self,'Save learning backup',str(Path.home()/('GrammAI-learning-'+datetime.now().strftime('%Y-%m-%d')+'.zip')),'ZIP backup (*.zip)')
        if not file:return
        self.export_backup(file,dialog)
    def export_backup(self,file,dialog=None):
        if self._backup_busy:return
        from core.storage_data import export_deck
        from audio.tasks import AudioTask
        self._backup_busy=True;self.backup.setEnabled(False)
        if dialog:dialog.working('Saving cards and original recordings…')
        self._backup_task=AudioTask(lambda:export_deck(file));self._backup_task.signals.ready.connect(lambda result,error:self._backup_done(dialog,result,error));QThreadPool.globalInstance().start(self._backup_task)
    def _backup_done(self,dialog,result,error):
        self._backup_busy=False
        if self._disposed:return
        self.backup.setEnabled(True)
        if error:
            self.feedback.setText('Backup failed · '+error)
            if dialog:dialog.status.setText(error);dialog.cancel.setEnabled(True);dialog.confirm.setEnabled(True)
            return
        if dialog:dialog.accept()
        self.feedback.setText(f"Backup saved · {result['cards']} cards / {result['recordings']} recordings"+(f" · {result['missing_recordings']} recordings unavailable" if result['missing_recordings'] else ''));self.feedback.setToolTip(result['path'])
    def _clear_phrases(self):
        if self._mutation:return
        dialog=StorageReview('Delete all learning cards?',self);self.preview_dialog=dialog
        dialog.message.setText('Permanently delete all saved cards, notes and explanations?')
        dialog.detail.setText('Make a backup first. Recordings stay on disk and can be reviewed separately with Clean up. Models and preferences stay.')
        dialog.confirm_check.show();dialog.confirm.setObjectName('danger');dialog.confirm.setText('Delete cards');dialog.confirm.setEnabled(False);dialog.confirm_check.toggled.connect(dialog.confirm.setEnabled);dialog.confirm.clicked.connect(lambda:self._delete_confirmed(dialog));dialog.open()
    def _delete_confirmed(self,dialog):
        if not dialog.confirm_check.isChecked() or self._mutation:return
        from audio.tasks import AudioTask
        self._mutation=True;dialog.working('Deleting reviewed learning cards…')
        self._delete_task=AudioTask(lambda:Phrasebook().clear(preserve_audio=True));self._delete_task.signals.ready.connect(lambda result,error:self._delete_done(dialog,error));QThreadPool.globalInstance().start(self._delete_task)
    def _delete_done(self,dialog,error):
        self._mutation=False
        if self._disposed:return
        if error:dialog.status.setText(error);dialog.cancel.setEnabled(True);self.feedback.setText('Could not delete cards · '+error);return
        dialog.accept();self.refresh();self.scan_audio();self.feedback.setText('Learning cards deleted. Recordings and models kept.')
    def _clear_benchmarks(self):
        try:write_json('benchmarks.json',[]);self.refresh();self.feedback.setText('Test summaries cleared.')
        except OSError as exc:self.feedback.setText('Could not clear summaries · '+str(exc))
    def _open_folder(self):
        data_dir().mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))
