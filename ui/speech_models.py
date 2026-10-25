"""Compact native model picker: download/check icons and accessible state labels."""
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox
from core.speech_models import TITLES,installed,selected_id
from ui.icons import LineIcon

class SpeechModelCombo(QComboBox):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.running_id=None
        self.setAccessibleName('Speech recognition model');self.refresh()
    def refresh(self):
        selected=self.currentData() or selected_id(self.config)
        states={key:installed(key,self.config) for key in TITLES}
        signature=(tuple(states.items()),self.running_id,selected_id(self.config)=='external')
        if getattr(self,'_signature',None)==signature:return
        self._signature=signature
        with QSignalBlocker(self):
            self.clear()
            if selected_id(self.config)=='external':self.addItem('Current / custom model','external')
            for available,heading in ((True,'Installed'),(False,'Available to download')):
                keys=[key for key in TITLES if states[key]==available]
                if not keys:continue
                self.addItem(heading,None);header=self.model().item(self.count()-1);header.setEnabled(False)
                for key in keys:
                    state='Running' if available and key==self.running_id else 'Installed' if available else 'Not downloaded'
                    self.addItem(QIcon(LineIcon('check' if available else 'download')),TITLES[key]+(' · Running' if state=='Running' else ''),key)
                    index=self.count()-1;caption=state+(' · Experimental speech backend' if key=='speech-qwen' else '')
                    self.setItemData(index,caption,Qt.ItemDataRole.ToolTipRole);self.setItemData(index,caption,Qt.ItemDataRole.AccessibleDescriptionRole)
            index=self.findData(selected);self.setCurrentIndex(index if index>=0 else self.findData('external'))
    def showPopup(self):
        self.refresh();super().showPopup()
