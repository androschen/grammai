"""Render the real Qt UI with public sample text; never capture the user's desktop."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from audio.replay import ReplayStore
from core.config import AppConfig,TargetLanguage
from core.events import EventBus,SubtitleUpdate
from core.revisions import revised_update
from core.analysis import AnalysisService
from ui.theme import style_for
from ml.phonetics import phonetics_auto
from ui.learning import StudyDialog
from ui.panel import ControlPanel


def main():
    app=QApplication.instance() or QApplication([])
    for filename in ('segoeui.ttf','seguisym.ttf','msyh.ttc','tahoma.ttf'):
        path=Path('C:/Windows/Fonts')/filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI',10))
    config=AppConfig(source_language='zh',target_language=TargetLanguage.ENGLISH)
    events=EventBus()
    service=AnalysisService(events=events,config=config)
    with patch('ui.panel.list_audio_sources',return_value=[]):
        panel=ControlPanel(config,events)
    examples=[
        ('zh','今天想吃什么？','What would you like to eat today?'),
        ('en','Something simple. We can grab lunch nearby.','Something simple. We can grab lunch nearby.'),
        ('th','ไปกินข้าวกันเถอะ',"Let's go get something to eat."),
        ('id','gua beli nasi dulu',"I'll buy some rice first."),
        ('zh','不用着急，我们还有时间。',"No rush. We still have time."),
        ('en',"Sounds good. Let's meet downstairs.","Sounds good. Let's meet downstairs."),
        ('zh','我们先去吃饭吧。',"Let's get something to eat first."),
    ]
    start=datetime(2026,10,17,12,30)
    for index,(language,source,target) in enumerate(examples):
        update=SubtitleUpdate('',target,source,native_phonetics=phonetics_auto(source),
            source_language=language,target_language='en',created_at=start+timedelta(seconds=index*8))
        if index==len(examples)-1:
            original=SubtitleUpdate('',"Let's go eat first.",source,
                source_language='zh',target_language='en',created_at=update.created_at)
            update=revised_update(original,target_text=target,native_phonetics=phonetics_auto(source),ai_refined=True)
        panel._on_subtitle(update)
    dialog=StudyDialog(update,config,events,ReplayStore(),Mock(),panel,analysis=service)
    dialog.setStyleSheet(style_for(config.theme))
    screen=Mock();screen.availableGeometry.return_value=QRect(0,0,1920,1080)
    with patch.object(panel,'screen',return_value=screen):
        panel.open_sentence_details(dialog)
    panel.resize(1320,840)
    panel._workspace.setSizes([800,430])
    panel.set_status('UI preview with sample sentences — no audio is being captured.')
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
    panel.show()
    for _ in range(8):
        QTest.qWait(30)
    destination=Path(__file__).resolve().parents[1]/'docs'/'images'/'grammai-desktop.png'
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not panel.grab().save(str(destination)):
        raise RuntimeError('Could not save the README screenshot')
    dialog.grab().save(str(destination.parent/'grammai-sentence.png'))
    dialog.bookmark.click();QTest.qWait(50)
    dialog.save_popup.grab().save(str(destination.parent/'grammai-save.png'))
    panel.mark_quitting();panel.close();service.shutdown()
    print(destination)


if __name__=='__main__':
    main()
