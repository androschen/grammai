"""Qt-shaped subtitle text with optional outline/shadow, without bitmap effects."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QTextCharFormat,QTextLayout,QTextOption
from PySide6.QtWidgets import QLabel


class SubtitleLabel(QLabel):
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self.outline=True
        self.shadow=True
        self.setMargin(4)
        self._cached_key=None

    def set_readability(self,outline,shadow):
        if (self.outline,self.shadow)!=(outline,shadow):
            self.outline,self.shadow=outline,shadow
            self._cached_key=None
            self.update()

    def _layout(self,width,color,shadow=False,outline=False):
        layout=QTextLayout(self.text(),self.font())
        option=QTextOption()
        option.setAlignment(self.alignment())
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        fmt=QTextCharFormat()
        fmt.setForeground(QColor(0,0,0,190) if shadow else QColor('#101414') if outline else color)
        if outline or shadow:
            fmt.setTextOutline(QPen(QColor(0,0,0,190) if shadow else QColor('#101414'),3 if shadow else 2))
        span=QTextLayout.FormatRange()
        span.start,span.length,span.format=0,len(self.text().encode('utf-16-le'))//2,fmt
        layout.setFormats([span])
        layout.beginLayout()
        height=0
        while True:
            line=layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1,width))
            line.setPosition(QPointF(0,height))
            height+=line.height()
        layout.endLayout()
        return layout,height

    def paintEvent(self,event):
        if not self.text() or not (self.outline or self.shadow):
            super().paintEvent(event)
            return
        rect=self.contentsRect().adjusted(self.margin(),self.margin(),-self.margin(),-self.margin())
        color=self.palette().color(self.foregroundRole())
        key=(self.text(),self.font().toString(),rect.width(),color.rgba(),self.outline,self.shadow,self.devicePixelRatioF())
        if key!=self._cached_key:
            self._foreground,self._text_height=self._layout(rect.width(),color)
            self._outline=self._layout(rect.width(),color,outline=True)[0] if self.outline else None
            self._shadow=self._layout(rect.width(),color,True)[0] if self.shadow else None
            self._cached_key=key
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        origin=QPointF(rect.x(),rect.y()+max(0,(rect.height()-self._text_height)/2))
        if self._shadow:
            self._shadow.draw(painter,origin+QPointF(0,2))
        if self._outline:
            self._outline.draw(painter,origin)
        self._foreground.draw(painter,origin)
