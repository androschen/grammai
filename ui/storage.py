"""Storage information and explicit cleanup for app-owned learning data."""
from pathlib import Path
from PySide6.QtCore import QObject,QRunnable,QThreadPool,Signal,Slot,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QLabel,QPushButton,QMessageBox
from core.preferences import data_dir,write_json
from core.phrasebook import Phrasebook


class ScanSignals(QObject):
    ready=Signal(object)


class ModelScan(QRunnable):
    def __init__(self,config):
        super().__init__()
        self.signals=ScanSignals()
        self.config=config

    def run(self):
        total=0
        from core.paths import model_candidates
        roots=[Path.home()/'.grammai'/'models',*model_candidates('local-ai'),*model_candidates('speech')]
        hub=Path.home()/'.cache'/'huggingface'/'hub'
        if hub.is_dir():
            roots.extend(hub.glob('models--Systran--faster-whisper-*'))
        count=0
        for root in roots:
            try:
                for path in root.rglob('*'):
                    count+=1
                    if count>50000:
                        self.signals.ready.emit({'bytes':total,'partial':True})
                        return
                    if path.is_file() and not path.is_symlink():
                        total+=path.stat().st_size
            except OSError:
                continue
        external=Path(self.config.vulkan_model)
        try:
            if external.is_file() and not any(external.resolve().is_relative_to(r.resolve()) for r in roots):
                total+=external.stat().st_size
        except OSError:
            pass
        external=Path(self.config.analysis_gguf) if self.config.analysis_gguf else None
        try:
            if external is not None and external.is_file() and not any(external.resolve().is_relative_to(r.resolve()) for r in roots):
                total+=external.stat().st_size
        except OSError:
            pass
        self.signals.ready.emit({'bytes':total,'partial':False})


class StorageWidget(QWidget):
    def __init__(self,config,events,replays=None,parent=None):
        super().__init__(parent)
        self.config,self.events,self.replays=config,events,replays
        self.phrasebook=Phrasebook()
        self._scanning=False
        layout=QVBoxLayout(self)
        form=QFormLayout()
        self.ram,self.phrases,self.models,self.benchmarks=QLabel(),QLabel(),QLabel('Not scanned'),QLabel()
        for label in (self.ram,self.phrases,self.models,self.benchmarks):
            label.setWordWrap(True)
        form.addRow('Replay audio (RAM only)',self.ram)
        form.addRow('Learning deck (text only)',self.phrases)
        form.addRow('Benchmark summaries',self.benchmarks)
        form.addRow('Local models',self.models)
        layout.addLayout(form)
        hint=QLabel('Replay expires after 60 seconds and on device changes or Quit. No audio archive is created. Only phrases you explicitly save persist; the phrasebook is limited to 1,000 entries and 2 MB.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        layout.addWidget(hint)
        clear=QPushButton('Clear replay RAM')
        clear.setEnabled(replays is not None)
        clear.clicked.connect(events.replay_clear_requested.emit)
        layout.addWidget(clear)
        phrases=QPushButton('Delete all learning cards...')
        phrases.clicked.connect(self._clear_phrases)
        layout.addWidget(phrases)
        benchmarks=QPushButton('Clear benchmark summaries')
        benchmarks.clicked.connect(self._clear_benchmarks)
        layout.addWidget(benchmarks)
        refresh=QPushButton('Refresh model sizes')
        refresh.clicked.connect(self.scan_models)
        layout.addWidget(refresh)
        open_folder=QPushButton('Open app data folder')
        open_folder.clicked.connect(self._open_folder)
        layout.addWidget(open_folder)
        model_hint=QLabel('Model files are counted separately and never removed automatically. Shared Hugging Face caches can be used by other apps. Configured external Vulkan weights are included in the total.')
        model_hint.setWordWrap(True)
        model_hint.setObjectName('hint')
        layout.addWidget(model_hint)
        layout.addStretch()
        self.timer=QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    def set_active(self,active):
        if active:
            self.refresh()
            self.timer.start()
        else:
            self.timer.stop()

    def refresh(self):
        stats=self.replays.stats() if self.replays else {'bytes':0,'limit_bytes':3840000,'clips':0}
        self.ram.setText(f"{stats['bytes']/1024**2:.2f} / {stats['limit_bytes']/1024**2:.2f} MB; {stats['clips']} replayable sentences")
        stats=self.phrasebook.stats()
        self.phrases.setText(f"{stats['count']} / 1,000 phrases; {stats['bytes']/1024:.1f} / 2,048 KB")
        file=data_dir()/'benchmarks.json'
        summary_bytes=file.stat().st_size if file.is_file() else 0
        fixture=data_dir()/'benchmark.wav'
        fixture_bytes=fixture.stat().st_size if fixture.is_file() else 0
        self.benchmarks.setText(f'{summary_bytes/1024:.1f} KB summaries + {fixture_bytes/1024:.1f} KB fixed test audio (not a recording)')

    def scan_models(self):
        if self._scanning:
            return
        self._scanning=True
        self.models.setText('Checking model files in the background...')
        self._task=ModelScan(self.config)
        self._task.signals.ready.connect(self._model_sizes)
        QThreadPool.globalInstance().start(self._task)

    @Slot(object)
    def _model_sizes(self,result):
        self._scanning=False
        self.models.setText(f"{result['bytes']/1024**2:.1f} MB"+(' (partial scan)' if result['partial'] else ''))

    def _clear_phrases(self):
        if QMessageBox.question(self,'Delete saved phrases?','Permanently delete all saved phrases and notes?')==QMessageBox.StandardButton.Yes:
            try:
                self.phrasebook.clear()
                self.refresh()
            except OSError as exc:
                QMessageBox.warning(self,'Could not clear phrases',str(exc))

    def _clear_benchmarks(self):
        try:
            write_json('benchmarks.json',[])
            self.refresh()
        except OSError as exc:
            QMessageBox.warning(self,'Could not clear summaries',str(exc))

    def _open_folder(self):
        data_dir().mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))
