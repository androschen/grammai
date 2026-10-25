"""Language matching, replay ownership and recall-safe pronunciation controls."""
import os, tempfile, unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, QLocale
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtTextToSpeech import QTextToSpeech
from core.events import EventBus, SubtitleUpdate
from audio.pronunciation import PronunciationService
from audio.playback import AudioReplay
from audio.replay import ReplayStore
from ui.pronunciation import ListenWidget
APP = QApplication.instance() or QApplication([])


def settle(predicate):
    for _ in range(150):
        if predicate(): return
        QTest.qWait(10)
    raise AssertionError('Pronunciation completion signal did not arrive')


class Voice:
    def __init__(self, locale): self.code = locale
    def locale(self): return QLocale(self.code)
    def name(self): return 'Test ' + self.code


class Engine(QObject):
    stateChanged = Signal(object)
    def __init__(self, locales=('en_US', 'zh_CN', 'th_TH', 'id_ID')):
        super().__init__(); self.voices = [Voice(x) for x in locales]; self.spoken = []; self.selected = None; self.rate = 0.; self.stops = 0
    def availableVoices(self): return self.voices
    def state(self): return QTextToSpeech.State.Ready
    def setVoice(self, value): self.selected = value
    def setRate(self, value): self.rate = value
    def setVolume(self, value): pass
    def say(self, text): self.spoken.append(text); self.stateChanged.emit(QTextToSpeech.State.Speaking)
    def stop(self): self.stops += 1; self.stateChanged.emit(QTextToSpeech.State.Ready)
    def errorString(self): return 'Output disconnected'


class PronunciationTests(unittest.TestCase):
    def setUp(self):
        self.events = EventBus(); self.engine = Engine()
        self.speech = PronunciationService(self.events, engine_factory=lambda name:self.engine, engines=['winrt'])
        self.events.pronunciation_service = self.speech
    def tearDown(self):
        self.speech.stop(); QTest.qWait(210)
    def test_discovery_is_lazy_and_never_uses_mock_or_wrong_language(self):
        self.assertFalse(self.speech._loaded)
        self.assertEqual(set(self.speech.inventory()), {'en','zh','th','id'})
        self.engine.voices = [Voice('en_US'), Voice('zh_HK')]; self.speech.refresh()
        self.assertIsNone(self.speech.voice('zh')); self.assertFalse(self.speech.play('tts:no', '你好', 'zh'))
        self.assertEqual(self.engine.spoken, [])
        empty = PronunciationService(self.events, engine_factory=lambda name:self.fail('Must not create mock engine'), engines=['mock'])
        self.assertEqual(empty.inventory(), {})
    def test_language_voice_text_and_speed_match_without_model_or_disk(self):
        self.assertTrue(self.speech.play('tts:one', '你好！', 'zh-CN', .8))
        self.assertEqual(self.engine.selected.locale().name(), 'zh_CN'); self.assertEqual(self.engine.spoken, ['你好！'])
        self.assertEqual(self.engine.rate, -.2); self.assertTrue(self.events.property('pronunciation_active'))
        self.assertFalse(self.speech.play('tts:long', 'x'*2001, 'en'))
    def test_stop_ready_error_and_duplicate_stop_release_capture(self):
        active=[]; failures=[]; self.events.playback_active.connect(active.append);self.speech.failed.connect(lambda k,m:failures.append(m))
        self.speech.play('tts:a', 'Hello', 'en'); self.speech.stop(); self.speech.stop(); settle(lambda: active == [True,False])
        self.assertEqual(active, [True,False])
        self.speech.play('tts:b', 'Hello', 'en'); self.engine.stateChanged.emit(QTextToSpeech.State.Ready); QTest.qWait(220)
        self.assertFalse(active[-1])
        self.speech.play('tts:c', 'Hello', 'en'); self.engine.stateChanged.emit(QTextToSpeech.State.Error);QTest.qWait(220)
        self.assertIn('Output disconnected', failures[-1]);self.assertFalse(active[-1])
    def test_recording_and_speech_handoff_never_resume_capture_during_playback(self):
        player=AudioReplay(self.events, ReplayStore()); active=[]; self.events.playback_active.connect(active.append)
        self.speech.play('tts:a','Hello','en')
        player._stop_pronunciation(); self.events.setProperty('replay_active',True);QTest.qWait(220)
        self.assertNotIn(False,active)
        self.events.setProperty('replay_active',False)
        self.speech.play('tts:b','Hello','en'); player._resume_capture()
        self.assertTrue(active[-1]);self.assertNotIn(False,active)
        self.speech.stop();QTest.qWait(220);self.assertFalse(active[-1])
    def test_silent_backend_timeout_and_late_saved_audio_load_are_cancelled(self):
        player=AudioReplay(self.events,ReplayStore());old=player._generation
        self.engine.say=lambda text:None
        failures=[];self.speech.failed.connect(lambda key,message:failures.append(message))
        self.speech.play('tts:waiting','Hello','en');generation=self.speech._generation
        with patch.object(player,'_start') as start:
            player._loaded(old,'saved:late.ogg',1.,[0.],None);start.assert_not_called()
        self.speech._check_started(generation);self.assertEqual(self.speech._key,'');self.assertIn('did not start',failures[0])

    def test_new_request_replaces_old_and_old_timeout_cannot_stop_it(self):
        self.speech.play('tts:a','One','en'); old=self.speech._generation
        self.speech.play('tts:b','Two','en'); self.speech._check_started(old)
        self.assertEqual(self.speech._key,'tts:b');self.assertEqual(self.engine.spoken,['One','Two'])
    def test_two_widgets_have_single_play_stop_and_hide_cancels(self):
        a=ListenWidget(self.events);b=ListenWidget(self.events)
        a.bind('Hello','en');b.bind('你好','zh');a.show();b.show()
        a.play.click();self.assertEqual(a.play.text(),'Stop');self.assertTrue(a.playing)
        b.play.click();self.assertFalse(a.playing);self.assertTrue(b.playing)
        b.speed.setCurrentIndex(1);self.assertFalse(b.playing)
        b.play.click();b.hide();self.assertEqual(self.speech._key,'')
        a.dispose();b.dispose();a.close();b.close()
    def test_locked_missing_and_refresh_controls_do_not_speak(self):
        self.engine.voices=[Voice('en_US')];w=ListenWidget(self.events)
        w.bind('你好','zh',locked=True);self.assertFalse(w.play.isEnabled());self.assertEqual(w.hint.text(),'Reveal to listen');self.assertTrue(w.recheck.isHidden())
        w.bind('你好','zh');self.assertFalse(w.play.isEnabled());self.assertIn('Chinese voice not installed',w.hint.text());self.assertFalse(w.recheck.isHidden())
        self.engine.voices.append(Voice('zh_CN'));w.recheck.click();self.assertTrue(w.play.isEnabled());self.assertEqual(self.engine.spoken,[])
        w.dispose()
    def test_practice_recall_reveal_and_switch_card_safely(self):
        from core.config import AppConfig
        from core.phrasebook import Phrasebook
        from ui.deck import LearningDeckDialog
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GRAMMAI_DATA_DIR=folder):
            book=Phrasebook();book.save(SubtitleUpdate('','Hello','你好',source_language='zh'),reviewed=True)
            d=LearningDeckDialog(AppConfig(),book,events=self.events);d.show();d.tabs.setCurrentIndex(1)
            d.mode.setCurrentIndex(d.mode.findData('recall'));d.start_review()
            self.assertFalse(d.practice_listen.play.isEnabled());self.assertEqual(d.practice_listen.text,'你好')
            d.reveal_answer();self.assertTrue(d.practice_listen.play.isEnabled());d.practice_listen.play.click();self.assertTrue(d.practice_listen.playing)
            d.skip_card();self.assertFalse(d.practice_listen.playing);d.reject()
    def test_reply_ui_uses_reply_language_not_meaning_and_cleans_up(self):
        from core.config import AppConfig
        from core.analysis import AnalysisService
        from core.phrasebook import Phrasebook
        from ui.learning import StudyDialog
        from tests.test_reply_suggestions import PAYLOAD, VALUE
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GRAMMAI_DATA_DIR=folder):
            service=AnalysisService(events=self.events)
            d=StudyDialog(SubtitleUpdate('','Wrong',PAYLOAD['text'],source_language='zh'),AppConfig(analysis_explanation_language='id'),self.events,ReplayStore(),Phrasebook(),analysis=service)
            with patch.object(service,'suggest_replies',return_value=True):
                d.show();d.reply_button.click();w=d.reply_suggestions;w.completed(w.token,VALUE)
                self.assertEqual(len(w.listeners),2);listen=w.listeners[0];listen.play.click()
                self.assertEqual(self.engine.spoken[-1],VALUE['replies'][0]['text']);self.assertEqual(self.engine.selected.locale().name(),'zh_CN')
                d.reply_button.click();self.assertFalse(listen.playing);d.reject()
            service.shutdown();service.timer.stop()

if __name__=='__main__':unittest.main()
