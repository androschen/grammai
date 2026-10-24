"""Render native learning UI using only synthetic examples and no model calls."""
import os,tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus
from core.analysis import AnalysisService
from core.phrasebook import Phrasebook
from ui.deck import LearningDeckDialog
from ui.phrase_explain import PhraseExplanationDialog

PAYLOAD=dict(phrase='摸鱼',sentence='别摸鱼了，先把这个做完。',language='zh',
    original_text='别摸鱼了，先把这个做完。',original_language='zh',text_role='original',
    example_translation='Jangan bermalas-malasan, selesaikan ini dulu.',
    context=[dict(text='你怎么还在刷手机？',language='zh')])
VALUE=dict(meaning='Bermalas-malasan saat seharusnya bekerja.',usage='Informal',
    usage_note='Ungkapan santai tentang menghindari pekerjaan.',uncertainty='')


def main():
    app=QApplication.instance() or QApplication([])
    for file in ('segoeui.ttf','msyh.ttc','tahoma.ttf'):
        path=Path('C:/Windows/Fonts')/file
        if path.is_file():QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI',10));out=Path('build/learning-preview');out.mkdir(parents=True,exist_ok=True)
    def grab(widget,name):
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);widget.show();QTest.qWait(80)
        assert widget.grab().save(str(out/name))
    with tempfile.TemporaryDirectory(dir=out) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
        book=Phrasebook();book.save_vocabulary(PAYLOAD,VALUE,VALUE['meaning'],'Ungkapan santai tentang pekerjaan.',reviewed=True)
        for language,phrase,sentence,meaning,notes in [
            ('th','ไม่เป็นไร','ไม่เป็นไร ไว้คราวหน้า','Tidak apa-apa.','Untuk menenangkan orang.'),
            ('en','grab a bite',"Let's grab a bite before the meeting.",'Makan sebentar / cari makan.','Ungkapan santai, bukan menggigit.')]:
            p=dict(PAYLOAD,phrase=phrase,sentence=sentence,language=language,original_text=sentence,original_language=language,example_translation='',context=[])
            book.save_vocabulary(p,dict(usage='Informal',usage_note='',uncertainty=''),meaning,notes,reviewed=True)
        for theme in ('dark','light'):
            app.setProperty('grammai_theme',theme)
            config=AppConfig(theme=theme);events=EventBus();service=AnalysisService(events=events)
            with patch.object(service,'explain',return_value=True):
                draft=PhraseExplanationDialog(config,events,service,PAYLOAD,book)
                draft.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);draft.show();QTest.qWait(10)
                draft.completed(draft.token,VALUE);draft.notes.setPlainText('Ungkapan santai tentang pekerjaan.')
                grab(draft,'draft-'+theme+'.png');draft.reject()
            deck=LearningDeckDialog(config,book);grab(deck,'deck-'+theme+'.png')
            deck.editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);deck.edit_selected();grab(deck.editor,'card-'+theme+'.png');deck.editor.hide()
            deck.start_review();deck.mode.setCurrentIndex(deck.mode.findData('recall'));deck.tabs.setCurrentIndex(1)
            grab(deck,'practice-'+theme+'.png');deck.reveal_answer();grab(deck,'answer-'+theme+'.png');deck.reject()
            service.shutdown();service.timer.stop()
        print('Native sample-only UI previews:',out.resolve())


if __name__=='__main__':main()
