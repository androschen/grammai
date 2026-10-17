"""Task-focused main window: choose audio/languages, start, read subtitles."""
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QFrame,QHBoxLayout,
    QLabel,QMenu,QPushButton,QScrollArea,QSplitter,QSystemTrayIcon,QVBoxLayout,QWidget)
from audio.capture import list_audio_sources
from core.config import LANGUAGE_LABELS,SOURCE_LANGUAGE_LABELS,TargetLanguage
from core.history import SessionHistory
from ui.components import AudioMeterWidget
from ui.history import HistoryPanel,HistoryCard
from ui.performance import LivePerformance
from ui.settings import SettingsDialog
from ui.theme import style_for
from ui.controls import ToggleSwitch


def _tray_icon():
    pixmap=QPixmap(32,32)
    pixmap.fill(QColor('#b3f2ce'))
    painter=QPainter(pixmap)
    painter.setPen(QColor('#142b20'))
    painter.drawText(pixmap.rect(),Qt.AlignmentFlag.AlignCenter,'G')
    painter.end()
    return QIcon(pixmap)


class ControlPanel(QWidget):
    def __init__(self,config,events,replays=None):
        super().__init__()
        self._config,self._events=config,events
        self._replays=replays
        self._quitting=False
        self._history=SessionHistory()
        self._latest_id=None
        self.setObjectName('mainPanel')
        self.setWindowTitle('GrammAI - Live translation')
        self._applied_theme = config.theme
        self.setStyleSheet(style_for(config.theme))
        self.setMinimumSize(660,580)
        screen=QApplication.primaryScreen()
        available=screen.availableGeometry() if screen else None
        self.resize(min(1040,available.width()-48) if available else 1040, min(800,available.height()-48) if available else 800)
        self._build_ui()
        self._tray=self._build_tray()
        self.set_subtitles_on(False)
        events.status_changed.connect(self.set_status)
        events.pipeline_error.connect(self.set_status)
        events.audio_level_changed.connect(self._on_audio_level)
        events.state_changed.connect(self._on_app_state)
        events.subtitle_ready.connect(self._on_subtitle)
        events.subtitle_corrected.connect(self._on_corrected)
        events.benchmark_busy.connect(self._benchmark_busy)

    def _build_ui(self):
        layout=QVBoxLayout(self)
        layout.setContentsMargins(28,24,28,24)
        layout.setSpacing(18)
        header=QHBoxLayout()
        title=QLabel('GrammAI')
        title.setObjectName('title')
        brand=QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(title)
        tagline=QLabel('Live translation, on your desktop.')
        tagline.setObjectName('hint')
        brand.addWidget(tagline)
        header.addLayout(brand)
        header.addStretch()
        self._badge=QLabel('READY')
        self._badge.setObjectName('badge')
        self._badge.setFixedHeight(26)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._badge,0,Qt.AlignmentFlag.AlignVCenter)
        header.addSpacing(12)
        self._theme_picker=QComboBox()
        self._theme_picker.setAccessibleName('Color theme')
        self._theme_picker.addItem('Dark','dark')
        self._theme_picker.addItem('Light','light')
        self._theme_picker.setCurrentIndex(self._theme_picker.findData(self._config.theme))
        self._theme_picker.currentIndexChanged.connect(self._change_theme)
        header.addWidget(self._theme_picker)
        saved=QPushButton('Saved phrases')
        saved.clicked.connect(self._open_phrasebook)
        header.addWidget(saved)
        settings=QPushButton('Settings')
        settings.clicked.connect(lambda:self._open_settings(0))
        header.addWidget(settings)
        layout.addLayout(header)
        self._status=QLabel('Ready. Choose audio and languages, then start translation.')
        self._status.setObjectName('status')
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        splitter=QSplitter(Qt.Orientation.Horizontal)
        self._workspace=splitter
        controls=QFrame()
        controls.setObjectName('card')
        controls.setMinimumWidth(240)
        controls.setMaximumWidth(320)
        left=QVBoxLayout(controls)
        left.setContentsMargins(20,14,20,20)
        left.setSpacing(10)
        def field(text):
            label=QLabel(text)
            label.setObjectName('section')
            left.addWidget(label)
        field('AUDIO SOURCE')
        self._device=QComboBox()
        self._device.setAccessibleName('Audio source')
        self._device.addItem('Desktop audio (default)','')
        self._sources=[]
        try:
            self._sources=list_audio_sources()
        except Exception:
            pass
        for source in self._sources:
            self._device.addItem(('Desktop: ' if source.kind=='loopback' else 'Mic: ')+source.name,source.device_id)
        self._device.setCurrentIndex(max(0,self._device.findData(self._config.audio_device_id)))
        self._device.currentIndexChanged.connect(self._on_device_changed)
        left.addWidget(self._device)
        self._meter=AudioMeterWidget(self)
        self._meter.setToolTip('Live input level. Click to adjust noise filtering in Audio settings.')
        self._meter.clicked.connect(lambda:self._open_settings(0))
        left.addWidget(self._meter)
        audio=QPushButton('Adjust noise filtering')
        audio.clicked.connect(lambda:self._open_settings(0))
        left.addWidget(audio)
        field('LANGUAGE ROUTE')
        self._source=QComboBox()
        self._source.setAccessibleName('Spoken language')
        for code,name in SOURCE_LANGUAGE_LABELS.items():
            self._source.addItem(name,code)
        self._source.setCurrentIndex(max(0,self._source.findData(self._config.source_language)))
        self._source.currentIndexChanged.connect(self._on_language_changed)
        left.addWidget(self._source)
        direction=QLabel('into')
        direction.setObjectName('hint')
        left.addWidget(direction)
        self._language=QComboBox()
        self._language.setAccessibleName('Target language')
        for code,name in LANGUAGE_LABELS.items():
            self._language.addItem(name,code.value)
        self._language.setCurrentIndex(max(0,self._language.findData(self._config.target_language.value)))
        self._language.currentIndexChanged.connect(self._on_language_changed)
        left.addWidget(self._language)
        field('SESSION')
        self._toggle=QPushButton('Start translation')
        self._toggle.setObjectName('toggle')
        self._toggle.setCheckable(True)
        self._toggle.clicked.connect(self._on_toggle_clicked)
        left.addWidget(self._toggle)
        self._translation_toggle=ToggleSwitch('Translate speech')
        self._translation_toggle.setChecked(self._config.translation_enabled)
        self._translation_toggle.toggled.connect(self._set_translation_mode)
        self._language.setEnabled(self._config.translation_enabled)
        left.addWidget(self._translation_toggle)
        self._overlay_toggle=ToggleSwitch('Floating subtitles')
        self._overlay_toggle.setChecked(self._config.show_overlay)
        self._overlay_toggle.toggled.connect(self._events.overlay_toggled.emit)
        left.addWidget(self._overlay_toggle)
        hint=QLabel('History continues when floating subtitles are hidden.')
        hint.setWordWrap(True)
        hint.setObjectName('hint')
        left.addWidget(hint)
        left.addStretch()
        left.addWidget(LivePerformance(self._events,compact=True))
        performance=QPushButton('Performance && models')
        performance.clicked.connect(lambda:self._open_settings(3))
        left.addWidget(performance)
        sidebar=QScrollArea()
        sidebar.setWidgetResizable(True)
        sidebar.setFrameShape(QFrame.Shape.NoFrame)
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(340)
        controls.setMaximumWidth(16777215)
        sidebar.setWidget(controls)
        splitter.addWidget(sidebar)
        reading=QWidget()
        right=QVBoxLayout(reading)
        right.setContentsMargins(14,0,0,0)
        label=QLabel('Latest subtitle')
        label.setObjectName('field')
        right.addWidget(label)
        self._latest=QVBoxLayout()
        empty=QFrame()
        empty.setObjectName('latestEmpty')
        empty.setMinimumHeight(170)
        empty_layout=QVBoxLayout(empty)
        empty_layout.setContentsMargins(24,22,24,22)
        empty_layout.addStretch()
        self._empty_latest=QLabel('Ready when you are')
        self._empty_latest.setObjectName('field')
        font=self._empty_latest.font()
        font.setPointSize(16)
        self._empty_latest.setFont(font)
        empty_layout.addWidget(self._empty_latest)
        guidance=QLabel('Start translation to see words and pronunciation here.')
        guidance.setObjectName('hint')
        guidance.setWordWrap(True)
        empty_layout.addWidget(guidance)
        empty_layout.addStretch()
        self._latest.addWidget(empty)
        right.addLayout(self._latest)
        self._history_panel=HistoryPanel(self)
        self._history_panel.cleared.connect(self.clear_history)
        self._history_panel.study_requested.connect(self._events.learning_requested.emit)
        right.addWidget(self._history_panel,1)
        splitter.addWidget(reading)
        self._details_host=QWidget()
        self._details_layout=QVBoxLayout(self._details_host)
        self._details_layout.setContentsMargins(0,0,0,0)
        splitter.addWidget(self._details_host)
        self._details_host.hide()
        self._details_view=None
        splitter.setSizes([290,620])
        splitter.setStretchFactor(1,1)
        layout.addWidget(splitter,1)

    def open_sentence_details(self,dialog):
        if self._details_view is not None:
            self._details_view.reject()
        self._details_view=dialog
        dialog.setParent(self._details_host,Qt.WindowType.Widget)
        self._details_layout.addWidget(dialog)
        dialog.finished.connect(lambda result:self._close_details(dialog))
        self._details_host.show()
        dialog.show()
        screen=self.screen().availableGeometry()
        if screen.width()<1280:
            self._workspace.widget(0).hide()
        self.resize(min(1480,screen.width()-48),self.height())
        self._workspace.setSizes([260,520,480])

    def _close_details(self,dialog):
        self._details_layout.removeWidget(dialog)
        dialog.deleteLater()
        if self._details_view is dialog:
            self._details_view=None
            self._details_host.hide()
            self._workspace.widget(0).show()

    def _build_tray(self):
        tray=QSystemTrayIcon(_tray_icon(),self)
        menu=QMenu(self)
        reveal=menu.addAction('Open GrammAI')
        reveal.triggered.connect(self.reveal)
        self._tray_toggle=menu.addAction('Start translation')
        self._tray_toggle.triggered.connect(self._toggle.click)
        quit_action=menu.addAction('Quit GrammAI')
        quit_action.triggered.connect(self._events.quit_requested.emit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason:self.reveal() if reason==QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray.show()
        return tray

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _change_theme(self):
        self._config.theme=self._theme_picker.currentData()
        self._events.state_changed.emit(self._config.snapshot())

    def _on_toggle_clicked(self):
        self.set_subtitles_on(self._toggle.isChecked())
        self._events.subtitles_toggled.emit(self._toggle.isChecked())

    def _on_device_changed(self):
        device=self._device.currentData() or ''
        self._config.audio_device_id=device
        source=next((s for s in self._sources if s.device_id==device),None)
        self._config.audio_device_name=source.name if source else 'Desktop audio (default)'
        self._config.audio_device_kind=source.kind if source else 'loopback'
        self._events.state_changed.emit(self._config.snapshot())

    def _set_translation_mode(self,enabled):
        self._config.translation_enabled=enabled
        self._events.state_changed.emit(self._config.snapshot())

    def _on_language_changed(self):
        self._config.source_language=self._source.currentData()
        self._config.target_language=TargetLanguage(self._language.currentData())
        self._events.state_changed.emit(self._config.snapshot())

    def _open_settings(self,page=0):
        dialog=SettingsDialog(self._config,self._events,self,page=page,replays=self._replays)
        dialog.exec()
        dialog.deleteLater()

    @Slot(float)
    def _on_audio_level(self,level):
        self._meter.update_volume(round(max(0,min(1,level))*100))

    @Slot(object)
    def _on_app_state(self,state):
        if self._applied_theme != self._config.theme:
            self._applied_theme=self._config.theme
            self.setStyleSheet(style_for(self._config.theme))
            if self._details_view is not None:
                self._details_view.setStyleSheet(style_for(self._config.theme))
        self._theme_picker.blockSignals(True)
        self._theme_picker.setCurrentIndex(self._theme_picker.findData(self._config.theme))
        self._theme_picker.blockSignals(False)
        self._translation_toggle.blockSignals(True)
        self._translation_toggle.setChecked(self._config.translation_enabled)
        self._translation_toggle.blockSignals(False)
        self._language.setEnabled(self._config.translation_enabled)
        self.set_subtitles_on(self._toggle.isChecked())
        self._meter.set_threshold(round(state.noise_threshold*100))
        for combo,value in ((self._device,state.device_id),(self._source,state.source_language),(self._language,state.target_language)):
            combo.blockSignals(True)
            index=combo.findData(value)
            if index>=0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)
        self._overlay_toggle.blockSignals(True)
        self._overlay_toggle.setChecked(self._config.show_overlay)
        self._overlay_toggle.blockSignals(False)

    @Slot(object)
    def _on_subtitle(self,update):
        if self._history.append(update):
            self._history_panel.append(update)
        self._show_latest(update)

    def _show_latest(self,update):
        self._latest_id=update.uid
        while self._latest.count():
            widget=self._latest.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        card=HistoryCard(update,featured=True)
        card.study_requested.connect(self._events.learning_requested.emit)
        card.setMaximumHeight(230)
        self._latest.addWidget(card)

    @Slot(object)
    def _on_corrected(self,update):
        if self._history.replace(update):
            self._history_panel.replace_update(update)
        if self._latest_id==update.uid:
            self._show_latest(update)

    def _open_phrasebook(self):
        from core.phrasebook import Phrasebook
        from ui.learning import PhrasebookDialog
        dialog=PhrasebookDialog(self._config,Phrasebook(),self)
        dialog.exec()
        dialog.deleteLater()

    def clear_history(self):
        if self._details_view is not None:
            self._details_view.reject()
        self._history.clear()
        self._history_panel.clear()

    def set_subtitles_on(self,enabled):
        self._badge.setText('LIVE' if enabled else 'READY')
        self._toggle.setChecked(enabled)
        action='translation' if self._config.translation_enabled else 'transcription'
        self._toggle.setText(('Stop ' if enabled else 'Start ')+action)
        self._toggle.setProperty('active','true' if enabled else 'false')
        self._toggle.style().unpolish(self._toggle)
        self._toggle.style().polish(self._toggle)
        self._tray_toggle.setText(('Stop ' if enabled else 'Start ')+action)
        self._tray.setToolTip('GrammAI - translating' if enabled else 'GrammAI - stopped')

    @Slot(bool)
    def _benchmark_busy(self,busy):
        if busy:
            self.set_status('Benchmark running. Live translation will resume when the test finishes.')

    @Slot(str)
    def set_status(self,message):
        self._status.setText(message)
        lower=message.lower()
        if 'benchmark' in lower and 'running' in lower:
            self._badge.setText('BENCHMARK')
        elif self._toggle.isChecked():
            label='LIVE'
            if any(word in lower for word in ('failed','unavailable','error')):
                label='ATTENTION'
            elif any(word in lower for word in ('loading','downloading')):
                label='LOADING'
            elif 'transcribing' in lower:
                label='WORKING'
            self._badge.setText(label)
        else:
            self._badge.setText('READY')

    def mark_quitting(self):
        self._quitting=True
        if self._details_view is not None:
            self._details_view.reject()
        self.clear_history()
        self._tray.hide()

    def closeEvent(self,event:QCloseEvent):
        if self._quitting:
            event.accept()
        elif self._tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self._events.quit_requested.emit()


def quit_application():
    app=QApplication.instance()
    if app:
        app.quit()
