"""Selectable reading text with explicit keyboard and context-menu copying."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QMenu


class CopyableLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.explain_handler=None
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def copy(self):
        text=self.selectedText() if self.hasSelectedText() else self.text()
        if text:
            QApplication.clipboard().setText(text)

    def select_all(self):
        self.setSelection(0,len(self.text().encode('utf-16-le'))//2)

    def event(self, event):
        # QLabel's text control can consume shortcuts before keyPressEvent.
        if event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):
            copy=event.matches(QKeySequence.StandardKey.Copy)
            select=event.matches(QKeySequence.StandardKey.SelectAll)
            if copy or select:
                if event.type()==QEvent.Type.KeyPress:
                    self.copy() if copy else self.select_all()
                event.accept()
                return True
        if event.type()==QEvent.Type.ContextMenu:
            self.contextMenuEvent(event)
            return True
        return super().event(event)

    def create_copy_menu(self):
        menu=QMenu(self)
        copy=menu.addAction('Copy' if self.hasSelectedText() else 'Copy text')
        copy.setEnabled(bool(self.text()))
        copy.triggered.connect(self.copy)
        select=menu.addAction('Select all')
        select.setEnabled(bool(self.text()))
        select.triggered.connect(self.select_all)
        if self.explain_handler is not None:
            phrase=self.selectedText().strip()
            explain=menu.addAction('Create learning card (local AI)')
            explain.setEnabled(bool(phrase) and len(phrase)<=120)
            explain.setToolTip('Select a word or phrase (up to 120 characters).')
            explain.triggered.connect(lambda:self.explain_handler(phrase))
        return menu

    def contextMenuEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        menu=self.create_copy_menu()
        try:
            menu.exec(event.globalPos())
        finally:
            menu.deleteLater()
        event.accept()
