"""No-capture, offline diagnostics for a freshly frozen application."""
import json
from pathlib import Path


def smoke_check(report,verify_models=False):
    results={}
    try:
        import numpy as np
        import ctranslate2,soundcard,sentencepiece,tokenizers,av,psutil
        from transformers import AutoTokenizer
        from faster_whisper import WhisperModel
        from audio.segmentation import StreamingSpeechDetector
        from ml.phonetics import phonetics_auto
        from core.events import EventBus,SubtitleUpdate
        from core.config import AppConfig
        from audio.replay import ReplayStore
        from ui.learning import StudyDialog
        from ui.overlay import SubtitleOverlay
        from core.local_assets import managed_paths
        from core.speech_assets import installed_paths
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        results['imports']='ok'
        results['chinese_pronunciation']=bool(phonetics_auto('\u4f60\u597d'))
        results['thai_pronunciation']=bool(phonetics_auto('\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35'))
        results['vad_silence']=StreamingSpeechDetector()(np.zeros(640,dtype=np.float32))<.5
        from audio.pronunciation import PronunciationService
        from ui.pronunciation import ListenWidget
        from PySide6.QtTextToSpeech import QTextToSpeech
        events=EventBus()
        speech=PronunciationService(events);events.pronunciation_service=speech
        results['windows_speech']={'engines':QTextToSpeech.availableEngines(),'voices':speech.inventory()}
        import sys
        if sys.platform=='win32':
            assert any(x in results['windows_speech']['engines'] for x in ('winrt','sapi')), 'Native Windows speech plugins missing'
        listen=ListenWidget(events);listen.bind('Hello','en')
        assert listen.play.isEnabled()==bool(speech.voice('en'))
        listen.bind('你好','zh',locked=True);assert not listen.play.isEnabled()
        listen.dispose();listen.deleteLater();results['listen_ui']='ok'

        dialog=StudyDialog(SubtitleUpdate('','Hello','Hello',source_language='en'),AppConfig(),events,ReplayStore(),None)
        dialog.show();QApplication.processEvents()
        results['details']='ok';dialog.reject();dialog.deleteLater()
        overlay=SubtitleOverlay(events,AppConfig());overlay.close();results['overlay']='ok'
        from ui.translation_compare import TranslationComparisonDialog
        comparison=TranslationComparisonDialog(AppConfig(),events)
        comparison.reject();comparison.deleteLater();results['comparison_ui']='ok'
        from ui.settings import SettingsDialog
        settings=SettingsDialog(AppConfig(),events)
        assert settings._translation_mode.count()==3
        settings.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
        settings.tabs.setCurrentIndex(3);settings.resize(1000,850);settings.show();QApplication.processEvents()
        for control in (settings._processing,settings._speech_choice,settings._translation_mode,settings._learning_choice,settings.manage_components,settings.test_setup,settings.setup_assistant):
            assert settings._models_normal.isAncestorOf(control), 'Models control has the wrong parent'
            assert control.isVisible(), 'Models control is hidden'
            point=control.mapTo(settings,control.rect().center())
            assert settings.childAt(point) is control, 'Another widget blocks Models input'
        settings._show_components(True);QApplication.processEvents()
        assert not settings._processing.isVisible() and settings.component_manager.isVisible()
        assert len(settings.component_manager.cards)==7
        settings._show_components(False);QApplication.processEvents()
        assert settings._processing.isVisible()
        results['models_input_routing']='ok'
        settings.reject();settings.deleteLater();results['translation_settings']='ok'
        from core.components import catalog
        assert {'speech-cpu','speech-turbo','qwen','ai-cpu','ai-vulkan','translation-fast'}<=set(catalog())
        results['component_catalog']='ok'
        from ui.model_setup import SetupDialog,active_jobs
        from PySide6.QtTest import QTest
        setup=SetupDialog(AppConfig());setup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
        for _ in range(1500):
            if not active_jobs():break
            QTest.qWait(10)
        assert not active_jobs(),'Setup hardware check did not finish'
        assert not setup.finish.isEnabled() and setup.pages.count()==3
        setup.reject();setup.deleteLater();results['setup_wizard']='ok'

        from ui.deck import LearningDeckDialog
        from core.phrasebook import Phrasebook
        from core.preferences import data_dir
        deck_path=data_dir()/'phrases.json'
        results['deck_storage']={'path':str(deck_path),'exists':deck_path.is_file()}
        try:
            raw=json.loads(deck_path.read_text(encoding='utf-8-sig')) if deck_path.is_file() else []
            results['deck_storage']['raw_count']=len(raw) if isinstance(raw,list) else -1
            results['deck_storage']['reader_count']=len(Phrasebook().items())
        except Exception as exc:
            results['deck_storage']['error']=type(exc).__name__
        deck=LearningDeckDialog(AppConfig(),Phrasebook())
        if 'error' not in results['deck_storage']:
            results['deck_storage']['displayed_count']=deck.list.count()
            assert deck.list.count()==results['deck_storage']['reader_count']==results['deck_storage']['raw_count']
        assert deck.mode.count()==2
        assert deck.editor.edit_fields.isHidden() and deck.editor.checked.isHidden()
        assert deck.editor.save.text()=='Save notes'
        results['reading_card_ui']='ok'
        from core.card_time import saved_time
        assert saved_time('2026-10-24T07:32:00+00:00')[0]!='Date unavailable'
        if deck.items:
            assert deck.editor.saved_at.text().startswith('Saved ')
            doc=deck.list.itemDelegate().document(deck.list.model().index(0,0),300,deck.palette())
            assert saved_time(deck.items[0].get('saved_at'))[0] in doc.toPlainText()
        results['card_saved_time_ui']='ok'
        from PySide6.QtCore import Qt
        assert deck.editor.windowModality()==Qt.WindowModality.WindowModal
        from core.learning_cards import practice_prompt
        assert practice_prompt({'card_type':'vocabulary','native_text':'gua','example_sentence':'gua beli nasi dulu'},'recall')[0]=='____ beli nasi dulu'
        from ui.card_explanation import CardExplanationWidget
        explanation=CardExplanationWidget()
        explanation.set_data({'sentence_meaning':'Saya makan dulu.','why':'Urutan tindakan.',
            'words':[{'text':'gua','pronunciation':'','meaning':'saya','reason':'Kata ganti.'}]},None)
        assert explanation.reading_layout.count()==3
        explanation.dispose();explanation.deleteLater()
        assert deck.practice_explanation.value is None
        results['saved_explanation_ui']='ok'
        results['contextual_vocabulary_ui']='ok'
        deck.reject();deck.deleteLater();results['learning_deck_ui']='ok'
        from ui.deck import LearningDeckPage
        from PySide6.QtWidgets import QWidget,QVBoxLayout
        host=QWidget();host.resize(940,700);host_box=QVBoxLayout(host)
        page=LearningDeckPage(AppConfig(),Phrasebook(),host);host_box.addWidget(page)
        assert not page.isWindow() and not page.editor.isWindow()
        assert page.editor.window() is host
        assert page.list.count()==results['deck_storage'].get('reader_count',page.list.count())
        results['single_window_deck']='ok';page.dispose()
        from ui.settings import SettingsPage
        from ui.performance import ResourcesPage
        preferences=SettingsPage(AppConfig(),events,host);assert not preferences.isWindow();preferences.activate();preferences.suspend();preferences.dispose();preferences.deleteLater()
        resources=ResourcesPage(events,host);assert not resources.isWindow();resources.deleteLater()
        results['unified_workspace']='ok';host.deleteLater()
        from ui.phrase_explain import PhraseExplanationDialog
        from core.analysis import AnalysisService
        phrase_service=AnalysisService(events=events,config=AppConfig())
        phrase=PhraseExplanationDialog(AppConfig(),events,phrase_service,
            {'phrase':'gua','sentence':'gua beli nasi dulu','language':'id','original_text':'gua beli nasi dulu','original_language':'id'},Phrasebook())
        # Do not process the queued automatic explanation during a UI-only smoke.
        phrase.reject();phrase.deleteLater();phrase_service.shutdown()
        from ui.save_card import SaveCardFields
        assert isinstance(phrase.form,SaveCardFields)
        results['compact_save_ui']='ok'
        results['phrase_explanation_ui']='ok'
        import tempfile,os
        from audio.library import AudioLibrary
        original_data_dir=os.environ.get('GRAMMAI_DATA_DIR')
        with tempfile.TemporaryDirectory() as audio_test_dir:
            try:
                os.environ['GRAMMAI_DATA_DIR']=audio_test_dir
                library=AudioLibrary();audio=np.sin(np.arange(16000,dtype=np.float32)*.03)*.1
                recording=library.save(audio)
                decoded=library.load(recording['file'])
                assert len(decoded)==len(audio) and np.mean((decoded-audio)**2)<.01
                book=Phrasebook();item=book.save(SubtitleUpdate('','Hello','Hello'),audio=recording)
                assert Phrasebook().items()[0]['audio']['file']==recording['file']
                from ui.card_audio import AudioTransport
                transport=AudioTransport(events);transport.bind(item,locked=True);assert not transport.play.isEnabled()
                transport.bind(item);assert transport.play.isEnabled();transport.dispose();transport.deleteLater()
                results['saved_audio_roundtrip']='ok'
                from ui.learning import StudyDialog
                reply_study=StudyDialog(SubtitleUpdate('','Sudah makan?','你吃饭了吗？',source_language='zh',target_language='id'),AppConfig(),events,ReplayStore(),book)
                widget=reply_study.reply_suggestions;widget.token='packaged-reply'
                widget.completed('packaged-reply',dict(status='ready',reason='',replies=[dict(text='还没，你呢？',meaning='Belum, kamu?',label='Kalau belum makan'),dict(text='吃了，谢谢。',meaning='Sudah makan, terima kasih.',label='Kalau sudah makan')]))
                assert widget.rows.count()==2
                widget.save_reply(widget.value['replies'][0]);popup=widget.popup
                assert popup.form.audio.isHidden() and not popup.save.isEnabled()
                popup.checked.setChecked(True);popup.commit()
                generated=next(x for x in book.items() if x.get('card_type')=='reply')
                assert generated['reply_question']=='你吃饭了吗？' and 'audio' not in generated
                assert not popup.isVisible();reply_study.reject();reply_study.deleteLater()
                results['reply_suggestions_ui']='ok'
            finally:
                if original_data_dir is None:os.environ.pop('GRAMMAI_DATA_DIR',None)
                else:os.environ['GRAMMAI_DATA_DIR']=original_data_dir
        results['existing_speech_model']=installed_paths()[1].is_file()
        results['existing_context_model']=managed_paths()[1].is_file()
        if verify_models:
            import os
            os.environ['HF_HUB_OFFLINE']='1'
            from ml.whisper_engine import WhisperEngine
            from ml.translator import NllbTranslator,_looks_like_ct2
            from ml.local_analysis import LocalAnalysisRuntime
            from core.config import TargetLanguage
            from dataclasses import replace
            exe,model=installed_paths()
            config=replace(AppConfig(),backend='vulkan',vulkan_executable=str(exe),vulkan_model=str(model))
            engine=WhisperEngine(config)
            translator=NllbTranslator(config)
            runtime=LocalAnalysisRuntime()
            try:
                engine.ensure_loaded()
                engine._transcribe(np.zeros(16000,dtype=np.float32),'transcribe')
                results['gpu_speech']=engine.active_backend
                if not _looks_like_ct2(Path.home()/'.grammai/models/nllb-200-distilled-600M-int8'):
                    raise RuntimeError('Offline verification requires existing NLLB weights')
                results['translation']=translator.translate('Hello','en','id')
                runtime.ensure_loaded(config,lambda message:None,lambda:False)
                results['gpu_context']=runtime.status
                from core.translation_compare import compare_translations
                results['translation_comparison']=compare_translations(config,
                    {'text':'gua beli nasi dulu','source':'id','target':'en'},runtime)['results']
                if any('error' in record for record in results['translation_comparison']):
                    raise RuntimeError('Packaged translator comparison failed')
                from ml.live_translator import LiveTranslator
                from core.analysis import AnalysisWorker
                live=LiveTranslator(replace(config,translation_mode='context'),translator,runtime,events)
                live.ensure_loaded()
                results['context_translation']=live.translate('gua beli nasi dulu','id','en')
                live.remember('We are buying lunch.','en')
                results['context_translation_with_dialogue']=live.translate('gua beli nasi dulu','id','en')
                reviewed=[]
                worker=AnalysisWorker(config,{'text':'gua beli nasi dulu','source':'id','target':'en',
                    'context':[]},runtime,'refine')
                worker.result.connect(reviewed.append);worker.run()
                if not reviewed or 'error' in reviewed[0]:
                    raise RuntimeError('Packaged automatic review failed')
                results['review_translation']=reviewed[0]['translation']
                from ml.phrase_explanation import explain
                results['phrase_explanation']=explain(config,
                    {'phrase':'gua','sentence':'gua beli nasi dulu','language':'id',
                     'original_text':'gua beli nasi dulu','original_language':'id'},runtime)
                if results['phrase_explanation']['meaning'].strip().casefold()=='gua':
                    raise RuntimeError('Packaged explanation repeated the phrase without defining it')
                live.close()
            finally:
                engine.close();translator.close();runtime.close()
        results['ok']=all(results[key] for key in ('chinese_pronunciation','thai_pronunciation','vad_silence'))
    except Exception:
        import traceback
        results['ok']=False;results['error']=traceback.format_exc()
    if report:
        Path(report).write_text(json.dumps(results,indent=2),encoding='utf8')
    return 0 if results.get('ok') else 1
