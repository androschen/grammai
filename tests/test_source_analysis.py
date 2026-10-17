"""Original source evidence, not prior translations, drives history analysis."""
import json
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.analysis import AnalysisService
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.history import SessionHistory
from ml.context_analysis import build_body,parse_response
from ui.learning import StudyDialog

APP=QApplication.instance() or QApplication([])
PAYLOAD={'selected_sentence':'You call the shots.','source_language':'en','target_language':'id',
    'preceding_sentences':[{'text':'You choose the restaurant.','language':'en'}]}
RESULT={'source_meaning':'The listener has the final decision.','translation':'Kamu yang memutuskan.',
    'explanation':'An idiom about authority.','ambiguity':''}


class SourceAnalysisTests(unittest.TestCase):
    def test_previous_translation_never_changes_model_request(self):
        for provider in ('local','online'):
            with self.subTest(provider=provider):
                config=AppConfig(analysis_provider=provider)
                first=build_body(config,dict(PAYLOAD,original_translation='WRONG_FIRST'))
                second=build_body(config,dict(PAYLOAD,original_translation='WRONG_SECOND',target_text='UNEXPECTED_TRANSLATION'))
                self.assertEqual(first,second)
                encoded=json.dumps(second)
                self.assertNotIn('WRONG_',encoded)
                self.assertNotIn('UNEXPECTED_TRANSLATION',encoded)
                data=json.loads(second['messages'][1]['content'])
                self.assertEqual(data['selected_sentence'],PAYLOAD['selected_sentence'])
                self.assertEqual(data['preceding_sentences'],PAYLOAD['preceding_sentences'])

    def test_cache_and_worker_ignore_previous_translation(self):
        service=AnalysisService()
        def wait():
            for _ in range(100):
                QTest.qWait(10)
                if not service.busy:
                    return
            self.fail('worker did not finish')
        with patch('core.analysis.analyze',return_value=RESULT) as model:
            service.request('a',AppConfig(),dict(PAYLOAD,original_translation='first'))
            wait()
            self.assertNotIn('original_translation',model.call_args.args[1])
            service.request('b',AppConfig(),dict(PAYLOAD,original_translation='second'))
            QTest.qWait(10)
            self.assertEqual(model.call_count,1)
        service.shutdown()

    def test_original_preview_edits_sync_and_translated_context_is_excluded(self):
        history=SessionHistory()
        history.append(SubtitleUpdate('','WRONG_PREVIOUS_TRANSLATION','You choose the restaurant.',source_language='en',target_language='id'))
        update=SubtitleUpdate('','WRONG_SELECTED_TRANSLATION','You call the shots.',source_language='en',target_language='id')
        history.append(update)
        events=EventBus()
        service=AnalysisService()
        service.request=Mock(return_value=True)
        dialog=StudyDialog(update,AppConfig(analysis_enabled=True),events,Mock(),Mock(),analysis=service,history=history)
        widget=dialog.analysis_widget
        self.assertEqual(widget.source_text.toPlainText(),update.native_text)
        self.assertIn('English',widget.source_label.text())
        self.assertNotIn('WRONG',widget.context.toPlainText())
        widget.source_text.setPlainText('You make the decision.')
        self.assertEqual(dialog.text.toPlainText(),'You make the decision.')
        dialog.text.setPlainText('You decide.')
        self.assertEqual(widget.source_text.toPlainText(),'You decide.')
        widget._run()
        sent=service.request.call_args.args[2]
        self.assertEqual(sent['selected_sentence'],'You decide.')
        self.assertNotIn('WRONG',json.dumps(sent))
        self.assertNotIn('original_translation',sent)
        widget._finished(widget.token,RESULT)
        text=widget.output.toPlainText()
        self.assertLess(text.index('Source meaning'),text.index('Fresh translation'))
        self.assertIn('comparison only',text)
        self.assertIn('WRONG_SELECTED_TRANSLATION',text)
        dialog.reject()
        service.shutdown()

    def test_edited_transcript_rejects_inflight_analysis(self):
        service=AnalysisService()
        service.request=Mock(return_value=True)
        update=SubtitleUpdate('','old','original',source_language='en',target_language='id')
        dialog=StudyDialog(update,AppConfig(analysis_enabled=True),EventBus(),Mock(),Mock(),analysis=service,history=SessionHistory())
        widget=dialog.analysis_widget
        widget._run()
        token=widget.token
        dialog.text.setPlainText('corrected')
        widget._finished(token,RESULT)
        self.assertFalse(widget.apply.isEnabled())
        self.assertIsNone(widget.candidate)
        self.assertIn('changed',widget.feedback.text())
        dialog.reject()
        service.shutdown()

    def test_response_requires_source_interpretation(self):
        response=lambda value:json.dumps({'choices':[{'message':{'content':json.dumps(value)}}]}).encode()
        self.assertEqual(parse_response(response(RESULT)),RESULT)
        missing=dict(RESULT)
        del missing['source_meaning']
        with self.assertRaises(ValueError):
            parse_response(response(missing))
