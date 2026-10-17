"""Small painted controls; no animation timers or extra UI dependencies."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPalette
from PySide6.QtWidgets import QCheckBox


class ToggleSwitch(QCheckBox):
    """Keyboard-accessible QCheckBox with a switch-shaped visual."""
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)
        self.toggled.connect(self.update)

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text())+60,32)

    def hitButton(self,pos):
        return self.rect().contains(pos)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else .45)
        y=(self.height()-22)/2
        track=QRectF(1,y,38,22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#b3f2ce' if self.isChecked() else '#43514c'))
        painter.drawRoundedRect(track,11,11)
        painter.setBrush(QColor('#183025' if self.isChecked() else '#e0e8e4'))
        painter.drawEllipse(QRectF(20 if self.isChecked() else 4,y+3,16,16))
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.setFont(self.font())
        painter.drawText(self.rect().adjusted(50,0,0,0),Qt.AlignmentFlag.AlignVCenter,self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#9ce9c0'),1))
            painter.drawRoundedRect(track.adjusted(-1,-2,2,2),12,12)
