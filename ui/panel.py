"""Task-focused main window: choose audio/languages, start, read subtitles."""
from PySide6.QtCore import Qt, Slot, QEvent
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
        QApplication.instance().setProperty('grammai_theme',config.theme)
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
        from ui.icons import icon_button, set_button_icon
        from PySide6.QtWidgets import QWidgetAction
        outer=QHBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        rail=QFrame();rail.setObjectName('navigationRail');rail.setFixedWidth(64)
        nav=QVBoxLayout(rail);nav.setContentsMargins(10,16,10,16);nav.setSpacing(12)
        logo=QLabel('G');logo.setObjectName('railBrand');logo.setAlignment(Qt.AlignmentFlag.AlignCenter);nav.addWidget(logo)
        conversation=icon_button('conversation','Conversation',self);conversation.clicked.connect(lambda:self._close_current_details());nav.addWidget(conversation)
        saved=icon_button('bookmark','Saved phrases',self);saved.clicked.connect(self._open_phrasebook);nav.addWidget(saved)
        nav.addStretch()
        performance=icon_button('chart','Performance and models',self);performance.clicked.connect(lambda:self._open_settings(3));nav.addWidget(performance)
        settings=icon_button('settings','Settings',self);settings.clicked.connect(lambda:self._open_settings(0));nav.addWidget(settings)
        outer.addWidget(rail)
        content=QWidget();body=QVBoxLayout(content);body.setContentsMargins(18,12,18,12);body.setSpacing(10);outer.addWidget(content,1)
        header=QHBoxLayout();title=QLabel('Conversation');title.setObjectName('field');header.addWidget(title);header.addStretch()
        self._badge=QLabel('Ready');self._badge.setObjectName('hint');header.addWidget(self._badge)
        self._overlay_toggle=icon_button('cc','Floating subtitles',self);self._overlay_toggle.setCheckable(True);self._overlay_toggle.setChecked(self._config.show_overlay)
        self._overlay_toggle.toggled.connect(self._overlay_visibility_changed);header.addWidget(self._overlay_toggle)
        self._theme_button=icon_button('sun','Switch to light mode',self);self._theme_button.clicked.connect(self._toggle_theme);header.addWidget(self._theme_button);body.addLayout(header)
        session=QHBoxLayout();session.setSpacing(8)
        self._toggle=icon_button('play','Start translation',self);self._toggle.setCheckable(True);self._toggle.clicked.connect(self._on_toggle_clicked);session.addWidget(self._toggle)
        self._device=QComboBox();self._device.setAccessibleName('Audio source');self._device.addItem('Desktop audio (default)','');self._sources=[]
        try:self._sources=list_audio_sources()
        except Exception:pass
        for source in self._sources:self._device.addItem(('Desktop: ' if source.kind=='loopback' else 'Mic: ')+source.name,source.device_id)
        self._device.setCurrentIndex(max(0,self._device.findData(self._config.audio_device_id)));self._device.currentIndexChanged.connect(self._on_device_changed)
        self._source=QComboBox();self._source.setAccessibleName('Spoken language')
        for code,name in SOURCE_LANGUAGE_LABELS.items():self._source.addItem(name,code)
        self._source.setCurrentIndex(max(0,self._source.findData(self._config.source_language)));self._source.currentIndexChanged.connect(self._on_language_changed)
        self._language=QComboBox();self._language.setAccessibleName('Translation language')
        for code,name in LANGUAGE_LABELS.items():self._language.addItem(name,code.value)
        self._language.setCurrentIndex(max(0,self._language.findData(self._config.target_language.value)));self._language.currentIndexChanged.connect(self._on_language_changed)
        self._translation_toggle=ToggleSwitch('Translate speech');self._translation_toggle.setChecked(self._config.translation_enabled);self._translation_toggle.toggled.connect(self._set_translation_mode)
        def menu_button(icon,label,widgets):
            button=icon_button(icon,label,self);menu=QMenu(button);host=QWidget();box=QVBoxLayout(host);box.setContentsMargins(14,12,14,12)
            for caption,widget in widgets:
                if caption:box.addWidget(QLabel(caption))
                box.addWidget(widget)
            action=QWidgetAction(menu);action.setDefaultWidget(host);menu.addAction(action);button.clicked.connect(lambda:menu.exec(button.mapToGlobal(button.rect().bottomLeft())))
            return button
        self._device.setMinimumWidth(160);self._device.setMaximumWidth(300)
        self._device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self._device.setMinimumContentsLength(14)
        session.addWidget(self._device,1)
        self._meter=AudioMeterWidget(self);self._meter.setMinimumWidth(70);self._meter.setMaximumWidth(100);self._meter.set_threshold(round(self._config.noise_threshold*100));self._meter.setToolTip('Input level and noise threshold. Click to adjust.');self._meter.clicked.connect(lambda:self._open_settings(0));session.addWidget(self._meter)
        self._threshold_button=icon_button('sliders','Noise threshold',self);self._threshold_button.clicked.connect(lambda:self._open_settings(0));session.addWidget(self._threshold_button)
        self._route=menu_button('route','Spoken and translation languages',[('Speech',self._source),('Meaning',self._language),('',self._translation_toggle)])
        self._route.setMinimumSize(120,36);self._route.setMaximumSize(220,36);session.addWidget(self._route);session.addStretch()
        body.addLayout(session)
        self._workspace=QSplitter(Qt.Orientation.Horizontal);self._workspace.setChildrenCollapsible(False)
        self._history_panel=HistoryPanel(self);self._history_panel.cleared.connect(self.clear_history);self._history_panel.study_requested.connect(self._events.learning_requested.emit);self._history_panel.explain_requested.connect(self._events.phrase_explain_requested.emit)
        self._workspace.addWidget(self._history_panel)
        self._details_host=QWidget();self._details_layout=QVBoxLayout(self._details_host);self._details_layout.setContentsMargins(0,0,0,0);self._workspace.addWidget(self._details_host);self._details_host.hide();self._details_view=None
        self._workspace.setStretchFactor(0,1);body.addWidget(self._workspace,1)
        self._status=QLabel('Ready. Start translation to begin.');self._status.setObjectName('hint');self._status.setTextFormat(Qt.TextFormat.PlainText);self._status.setWordWrap(True);body.addWidget(self._status)
        self._refresh_route()
        self._refresh_overlay_control()
        self._refresh_theme_control()
        self._refresh_audio_control()

    def _refresh_audio_control(self):
        kind='Mic' if self._config.audio_device_kind=='mic' else 'Desktop'
        full=kind+' · '+(self._config.audio_device_name or 'Default speakers')
        self._device.setToolTip(full+' · Select audio device')
        self._device.setAccessibleName(full+'. Select audio device')
        threshold=round(self._config.noise_threshold*100)
        self._threshold_button.setToolTip(f'Noise threshold · {threshold}%')
        self._threshold_button.setAccessibleName(f'Adjust noise threshold, {threshold} percent')

    def _toggle_theme(self):
        self._config.theme="light" if self._config.theme=="dark" else "dark"
        self._events.state_changed.emit(self._config.snapshot())

    def _refresh_theme_control(self):
        from ui.icons import set_button_icon
        dark=self._config.theme=="dark"
        set_button_icon(self._theme_button,"sun" if dark else "moon")
        label="Switch to light mode" if dark else "Switch to dark mode"
        self._theme_button.setAccessibleName(label);self._theme_button.setToolTip(label)

    def _refresh_overlay_control(self):
        on=self._overlay_toggle.isChecked()
        label="Hide subtitles" if on else "Show subtitles"
        from ui.icons import set_button_icon
        self._overlay_toggle.setText('')
        set_button_icon(self._overlay_toggle,'cc-on' if on else 'cc')
        self._overlay_toggle.setAccessibleName(label)
        self._overlay_toggle.setToolTip(label+" · Floating desktop overlay; translation continues when hidden")
        self._overlay_toggle.setFixedSize(36,36)

    def _overlay_visibility_changed(self,enabled):
        self._refresh_overlay_control()
        self._events.overlay_toggled.emit(enabled)

    def _refresh_route(self):
        source=self._config.source_language
        source='Auto' if source=='auto' else source.upper()
        self._route.setText(source+' → '+self._config.target_language.value.upper())
        self._route.setToolTip(self._source.currentText()+' → '+self._language.currentText())

    def _close_current_details(self):
        if self._details_view is not None:self._details_view.reject()

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
        self._workspace.setSizes([max(320,self.width()-460),420])

    def _close_details(self,dialog):
        self._details_layout.removeWidget(dialog)
        dialog.deleteLater()
        if self._details_view is dialog:
            self._details_view=None
            self._details_host.hide()


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

    def _on_toggle_clicked(self):
        self.set_subtitles_on(self._toggle.isChecked())
        self._events.subtitles_toggled.emit(self._toggle.isChecked())

    def _on_device_changed(self):
        device=self._device.currentData() or ''
        self._config.audio_device_id=device
        source=next((s for s in self._sources if s.device_id==device),None)
        self._config.audio_device_name=source.name if source else 'Desktop audio (default)'
        self._config.audio_device_kind=source.kind if source else 'loopback'
        self._refresh_audio_control()
        self._events.state_changed.emit(self._config.snapshot())

    def _set_translation_mode(self,enabled):
        self._config.translation_enabled=enabled
        self._events.state_changed.emit(self._config.snapshot())

    def _on_language_changed(self):
        self._config.source_language=self._source.currentData()
        self._config.target_language=TargetLanguage(self._language.currentData())
        self._refresh_route()
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
            QApplication.instance().setProperty('grammai_theme',self._config.theme)
            self._applied_theme=self._config.theme
            self.setStyleSheet(style_for(self._config.theme))
            if self._details_view is not None:
                self._details_view.setStyleSheet(style_for(self._config.theme))
        self._refresh_theme_control()
        self._refresh_audio_control()
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
        self._refresh_overlay_control()
        self._refresh_route()

    @Slot(object)
    def _on_subtitle(self,update):
        if self._history.append(update):
            self._history_panel.append(update)
        self._show_latest(update)

    def _show_latest(self,update):
        # A single conversation list avoids duplicating the newest sentence.
        self._latest_id=update.uid

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
        from ui.icons import set_button_icon
        set_button_icon(self._toggle,'pause' if enabled else 'play')
        self._toggle.setText('')
        self._toggle.setToolTip(('Pause ' if enabled else 'Start ')+action)
        self._toggle.setAccessibleName(self._toggle.toolTip())
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
