"""On-demand, offline Windows pronunciation with language-matched native voices."""
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtTextToSpeech import QTextToSpeech

LANGUAGES = {'en': 'English', 'zh': 'Chinese', 'th': 'Thai', 'id': 'Indonesian'}


def language_code(value):
    return str(value or '').replace('_', '-').split('-')[0].lower()


class PronunciationService(QObject):
    voices_changed = Signal()
    failed = Signal(str, str)

    def __init__(self, events, parent=None, engine_factory=None, engines=None):
        super().__init__(parent or events)
        self.events = events
        self._factory = engine_factory or (lambda name: QTextToSpeech(name, self))
        self._names = engines
        self._loaded = False
        self._engines = []
        self._voices = {}
        self._key = ''
        self._current = None
        self._generation = 0
        self._started = False
        events.replay_clear_requested.connect(self.stop)

    def refresh(self):
        self.stop()
        for engine in self._engines:
            engine.deleteLater()
        self._engines = []
        self._voices = {}
        # Never select Qt's mock engine or a network speech provider.
        names = self._names if self._names is not None else QTextToSpeech.availableEngines()
        for name in ('winrt', 'sapi'):
            if name not in names:
                continue
            try:
                engine = self._factory(name)
                self._engines.append(engine)
                engine.stateChanged.connect(lambda state, e=engine: self._state(e, state))
                if engine.state() == QTextToSpeech.State.Error:
                    continue
                for voice in engine.availableVoices():
                    locale = voice.locale().name().replace('_', '-')
                    code = language_code(locale)
                    if code not in LANGUAGES or (code == 'zh' and locale in ('zh-HK', 'zh-MO')):
                        continue
                    self._voices.setdefault(code, (engine, voice))
            except (RuntimeError, OSError):
                continue
        self._loaded = True
        self.voices_changed.emit()

    def voice(self, language):
        if not self._loaded:
            self.refresh()
        return self._voices.get(language_code(language))

    def inventory(self):
        if not self._loaded:
            self.refresh()
        return {code: {'name': voice.name(), 'locale': voice.locale().name()}
                for code, (_, voice) in self._voices.items()}

    def play(self, key, text, language, speed=1.):
        # Reject rather than truncate: pronunciation must match the displayed expression.
        text = str(text or '').strip()
        selected = self.voice(language)
        if not selected or not text or len(text) > 2000:
            self.failed.emit(key, 'Matching Windows voice unavailable.' if not selected else 'Listen supports text up to 2,000 characters.')
            return False
        self.stop()
        self.events.replay_requested.emit('', 1.)
        engine, voice = selected
        try:
            engine.setVoice(voice)
            engine.setRate(-.2 if speed < 1. else 0.)
            engine.setVolume(1.)
            self._current = engine
            self._key = key
            self._started = False
            generation = self._generation
            self.events.setProperty('pronunciation_active', True)
            self.events.playback_started.emit(key)
            # Suppress loopback/microphone capture before the first spoken sample.
            self.events.playback_active.emit(True)
            engine.say(text)
            QTimer.singleShot(8000, self, lambda: self._check_started(generation))
            return True
        except (RuntimeError, OSError) as exc:
            self.stop()
            self.failed.emit(key, 'Windows pronunciation failed: ' + str(exc))
            return False

    def _check_started(self, generation):
        if generation == self._generation and self._key and not self._started:
            key = self._key
            self.stop()
            self.failed.emit(key, 'Windows voice did not start. Check your audio output or recheck voices.')

    def _state(self, engine, state):
        if engine is not self._current or not self._key:
            return
        if state == QTextToSpeech.State.Speaking:
            self._started = True
        elif state == QTextToSpeech.State.Ready and self._started:
            self.stop()
        elif state == QTextToSpeech.State.Error:
            key = self._key
            message = engine.errorString() or 'Check your Windows speech voice and audio output.'
            self.stop()
            self.failed.emit(key, 'Windows pronunciation failed: ' + message)

    def stop(self):
        if self._current is None and not self._key:
            return
        self._generation += 1
        engine, key = self._current, self._key
        self._current = None
        self._key = ''
        self._started = False
        self.events.setProperty('pronunciation_active', False)
        if engine is not None:
            engine.stop()
        if key:
            self.events.playback_started.emit('')
            generation = self._generation
            QTimer.singleShot(200, self, lambda: self._release_capture(generation))

    def _release_capture(self, generation):
        if generation == self._generation and not self._key and not self.events.property('replay_active'):
            self.events.playback_active.emit(False)


def pronunciation_service(events):
    if events is None:
        return None
    service = getattr(events, 'pronunciation_service', None)
    if service is None:
        service = PronunciationService(events)
        events.pronunciation_service = service
    return service
