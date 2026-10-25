"""Compact Listen/Stop control; synthesized speech stays distinct from recordings."""
from uuid import uuid4
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel
from ui.icons import icon_button, set_button_icon
from audio.pronunciation import pronunciation_service, language_code, LANGUAGES


class ListenWidget(QWidget):
    def __init__(self, events, parent=None, service=None):
        super().__init__(parent)
        self.events = events
        self.service = service or pronunciation_service(events)
        self.key = 'tts:' + uuid4().hex
        self.text = ''
        self.language = ''
        self.locked = False
        self.playing = False
        self._disposed = False
        self._binding = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 4, 0, 4)
        box.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.play = QPushButton('Listen')
        self.play.setAccessibleName('Listen to generated pronunciation')
        set_button_icon(self.play, 'speaker')
        self.play.clicked.connect(self.toggle)
        row.addWidget(self.play)
        self.speed = QComboBox()
        self.speed.addItem('1×', 1.)
        self.speed.addItem('Slower', .8)
        self.speed.setFixedWidth(90)
        self.speed.setAccessibleName('Pronunciation speed')
        self.speed.setToolTip('Windows normal or slower speech rate')
        self.speed.currentIndexChanged.connect(self.stop)
        row.addWidget(self.speed)
        self.recheck = icon_button('refresh', 'Check installed Windows voices again', self)
        self.recheck.clicked.connect(self._refresh)
        row.addWidget(self.recheck)
        row.addStretch()
        box.addLayout(row)
        self.hint = QLabel()
        self.hint.setObjectName('hint')
        self.hint.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)) if url == 'ms-settings:speech' else None)
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        if self.service:
            self.service.voices_changed.connect(self._availability)
            self.service.failed.connect(self._failed)
        if events is not None:
            events.playback_started.connect(self._started)
        self.bind('', '')

    def bind(self, text, language, locked=False):
        self.stop()
        self.text = str(text or '').strip()
        self.language = language_code(language)
        self.locked = bool(locked)
        self._availability()
        self.setVisible(bool(self.text))

    def _availability(self):
        if self._binding or self._disposed:
            return
        self._binding = True
        try:
            voice = self.service.voice(self.language) if self.service and self.text and not self.locked else None
            valid = bool(self.text and len(self.text) <= 2000 and voice and not self.locked)
            self.play.setEnabled(valid)
            self.speed.setEnabled(valid)
            self.recheck.setVisible(bool(self.text and not voice and not self.locked and self.service))
            self.play.setToolTip('Reveal the expression first' if self.locked else 'Generated pronunciation · not the original speaker')
            if self.locked:
                self.hint.setText('Reveal to listen')
            elif len(self.text) > 2000:
                self.hint.setText('Listen supports text up to 2,000 characters.')
            elif voice:
                self.hint.setText('Windows voice · generated pronunciation')
                self.hint.setToolTip(voice[1].name() + ' · ' + voice[1].locale().name())
            else:
                name = LANGUAGES.get(self.language, 'Matching language')
                self.hint.setText(name + ' voice not installed · <a href="ms-settings:speech">Add voice</a>' if self.service else 'Windows pronunciation unavailable')
                self.hint.setToolTip('Windows Settings → Time & language → Speech → Manage voices → Add voices. Then check voices again.')
        finally:
            self._binding = False

    def _refresh(self):
        if self.service:
            self.service.refresh()
            self._availability()

    def toggle(self):
        if self.playing:
            self.stop()
        elif self.service and self.play.isEnabled():
            self.service.play(self.key, self.text, self.language, float(self.speed.currentData()))

    def _started(self, key):
        self.playing = key == self.key
        self.play.setText('Stop' if self.playing else 'Listen')
        set_button_icon(self.play, 'stop' if self.playing else 'speaker')
        self.play.setAccessibleName('Stop pronunciation' if self.playing else 'Listen to generated pronunciation')

    def _failed(self, key, message):
        if key == self.key:
            self.hint.setText(message)
            self.recheck.show()

    def stop(self, *args):
        if self.playing and self.service:
            self.service.stop()
        self._started('')

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def dispose(self):
        if self._disposed:
            return
        self.stop()
        self._disposed = True
        if self.service:
            for signal, slot in ((self.service.voices_changed, self._availability), (self.service.failed, self._failed)):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if self.events is not None:
            try:
                self.events.playback_started.disconnect(self._started)
            except (RuntimeError, TypeError):
                pass
