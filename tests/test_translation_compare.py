"""Translation-only prompts, fair local comparisons, task locking and UI ratings."""
import io
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock,patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core.config import AppConfig
from core.events import EventBus
from core.analysis import AnalysisService
from core.pipeline import TranslationPipeline
from core.translation_compare import compare_translations,OfflineNllbTranslator
from ml.qwen_translator import QwenTranslator,translation_body,TRANSLATION_SCHEMA
from ml.local_analysis import LocalAnalysisRuntime
from ui.translation_compare import TranslationComparisonDialog

APP=QApplication.instance() or QApplication([])
PAYLOAD={'text':'gua beli nasi dulu','source':'id','target':'en'}


class TranslationAdapterTests(unittest.TestCase):
    def test_prompt_contains_only_source_and_languages_not_prior_answers(self):
        body=translation_body(**dict(text=PAYLOAD['text'],source='id',target='en'))
        self.assertEqual(json.loads(body['messages'][1]['content'])['text'],PAYLOAD['text'])
        self.assertFalse(body['chat_template_kwargs']['enable_thinking'])
        self.assertNotRegex(body['messages'][0]['content'],r'\bgua\b')
        self.assertNotIn('source_meaning',json.dumps(body))
        runtime=Mock();runtime.complete_json.return_value={'translation':"I'll buy rice first."}
        value=QwenTranslator(AppConfig(),runtime).translate(**PAYLOAD)
        self.assertEqual(value,"I'll buy rice first.")
        self.assertEqual(runtime.complete_json.call_args.args[1],TRANSLATION_SCHEMA)

    def test_invalid_output_and_input_are_not_accepted_as_translations(self):
        runtime=Mock()
        adapter=QwenTranslator(AppConfig(),runtime)
        for value in ({},{'translation':''},{'translation':123}):
            runtime.complete_json.return_value=value
            with self.assertRaises(ValueError):adapter.translate(**PAYLOAD)
        with self.assertRaises(ValueError):translation_body('a'*1001,'id','en')
        with self.assertRaises(ValueError):translation_body('hello','auto','en')
        with self.assertRaises(InterruptedError):adapter.translate(**PAYLOAD,cancelled=lambda:True)

    def test_runtime_uses_translation_schema_and_zero_temperature(self):
        runtime=LocalAnalysisRuntime();runtime.process=Mock();runtime.process.poll.return_value=None
        runtime.signature=('test',);runtime.url='http://127.0.0.1:12345';runtime.key='test'
        runtime.http=Mock()
        runtime.http.open.return_value=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"translation":"I"}'},'finish_reason':'stop'}]}).encode())
        self.assertEqual(runtime.complete_json(translation_body('gua','id','en'),TRANSLATION_SCHEMA),{'translation':'I'})
        request=runtime.http.open.call_args.args[0]
        body=json.loads(request.data)
        self.assertEqual(body['temperature'],0)
        self.assertEqual(body['response_format']['schema'],TRANSLATION_SCHEMA)
        self.assertNotIn('source_meaning',str(body))

    def test_offline_nllb_never_downloads_missing_weights(self):
        translator=OfflineNllbTranslator(AppConfig())
        with patch('core.translation_compare._looks_like_ct2',return_value=False),patch.object(translator,'_download_preconverted') as download:
            with self.assertRaises(ValueError):translator._resolve_model_dir()
            download.assert_not_called()

    def test_compare_same_source_text_reports_independent_errors_and_timings(self):
        runtime=Mock();runtime.paths.return_value=(Mock(),Mock(name='model'))
        runtime.paths.return_value[1].name='Qwen.gguf'
        with patch('core.translation_compare.OfflineNllbTranslator') as nllb,patch('core.translation_compare.QwenTranslator') as qwen:
            nllb.return_value.translate.return_value='baseline'
            qwen.return_value.translate.return_value='candidate'
            result=compare_translations(AppConfig(analysis_provider='online'),PAYLOAD,runtime)
            self.assertEqual(nllb.return_value.translate.call_args.args,tuple(PAYLOAD.values()))
            self.assertEqual(qwen.return_value.translate.call_args.args[:3],tuple(PAYLOAD.values()))
            self.assertEqual(qwen.call_args.args[0].analysis_provider,'local')
            self.assertFalse(result['context_used'])
            self.assertTrue(all('loading_ms' in r and 'translation_ms' in r for r in result['results']))
            nllb.return_value.close.assert_called_once()
            nllb.return_value.ensure_loaded.side_effect=RuntimeError('missing')
            partial=compare_translations(AppConfig(),PAYLOAD,runtime)
            self.assertIn('error',partial['results'][0])
            self.assertEqual(partial['results'][1]['text'],'candidate')


class ComparisonLifecycleTests(unittest.TestCase):
    def test_service_blocks_during_live_and_pipeline_blocks_during_comparison(self):
        events=EventBus();service=AnalysisService(events=events)
        events.comparison_allowed=lambda:False
        with self.assertRaises(ValueError):service.compare('token',AppConfig(),PAYLOAD)
        self.assertFalse(service.busy)
        pipeline=TranslationPipeline(AppConfig(),events,Mock())
        events.setProperty('comparison_busy',True)
        failed=[];pipeline.inference_failed.connect(lambda:failed.append(True))
        pipeline.start_inference()
        self.assertFalse(pipeline.inference_requested)
        self.assertTrue(failed)
        pipeline._timer.stop();service.shutdown()

    def test_service_clears_busy_on_result_and_closing_dialog_drops_late_results(self):
        events=EventBus();service=AnalysisService(events=events);events.analysis_service=service
        results=[];service.comparison_completed.connect(lambda token,result:results.append(result))
        result=dict(PAYLOAD,results=[{'engine':'nllb','text':'baseline'},{'engine':'qwen','text':'candidate'}])
        with patch('core.translation_compare.compare_translations',return_value=result):
            self.assertTrue(service.compare('token',AppConfig(),PAYLOAD))
            self.assertTrue(events.property('comparison_busy'))
            for _ in range(100):
                QTest.qWait(10)
                if not service.busy:break
            self.assertTrue(results)
            self.assertFalse(events.property('comparison_busy'))
        dialog=TranslationComparisonDialog(AppConfig(),events)
        dialog.token='ui-token'
        dialog._finished('old-token',result)
        self.assertEqual(dialog.entries,[])
        dialog._finished('ui-token',result)
        self.assertEqual(len(dialog.entries),1)
        dialog.cards['qwen'][2].setCurrentIndex(1)
        self.assertEqual(dialog.entries[0]['ratings']['qwen'],1)
        dialog.reject()
        self.assertEqual(dialog.entries,[])
        service.shutdown()


if __name__=='__main__':unittest.main()
