"""Lightweight Qt-painted rolling charts, backed by the shared monitor history."""
from time import monotonic
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QToolTip


class ResourceGraph(QWidget):
    def __init__(self, events, fields, title, unit, maximum=None, parent=None):
        super().__init__(parent)
        self.events, self.fields, self.title, self.unit = events, fields, title, unit
        self.maximum = maximum
        self.setMinimumHeight(108)
        self.setMouseTracking(True)
        self.setAccessibleName(title + ' over the last two minutes')
        events.metrics_changed.connect(self._metrics)

    def _metrics(self, data):
        if data.get('kind') == 'live':
            self.update()

    def _points(self):
        return self.events.property('resource_history') or ()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(6, 27, max(1, self.width()-12), max(1, self.height()-48))
        from PySide6.QtWidgets import QApplication
        from ui.theme_tokens import palette_for
        colors=palette_for(QApplication.instance().property('grammai_theme'))
        color=QColor(colors['ink'])
        painter.setPen(color)
        painter.drawText(6, 17, self.title)
        points = self._points()
        now = monotonic()
        if len(self.fields)==1:
            value=points[-1][1].get(self.fields[0][0]) if points else None
            label=(f'{value:.1f} {self.unit}' if self.unit=='%' else f'{value:.0f} {self.unit}') if value is not None else 'Unavailable'
            x=self.width()-6-painter.fontMetrics().horizontalAdvance(label)
            if x>painter.fontMetrics().horizontalAdvance(self.title)+14:painter.drawText(x,17,label)
        values = [data[key] for stamp, data in points for key, _, _ in self.fields
                  if now-120 <= stamp <= now and data.get(key) is not None]
        top = self.maximum or max(1, max(values, default=1)*1.15)
        painter.setPen(QPen(QColor(colors['line']),1))
        for fraction in (0, .5, 1):
            y = rect.top()+fraction*rect.height()
            painter.drawLine(QPointF(rect.left(),y), QPointF(rect.right(),y))
        for key, label, hue in self.fields:
            path = QPainterPath()
            connected = False
            for stamp, data in points:
                value = data.get(key)
                if stamp < now-120 or value is None:
                    connected = False
                    continue
                point = QPointF(rect.right()-(now-stamp)/120*rect.width(),
                                rect.bottom()-min(top,max(0,value))/top*rect.height())
                if connected:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                connected = True
            painter.setPen(QPen(QColor(colors.get(hue,hue)),2))
            painter.drawPath(path)
        for stamp, label in self.events.property('resource_markers') or ():
            if now-120 <= stamp <= now:
                x = rect.right()-(now-stamp)/120*rect.width()
                painter.setPen(QPen(QColor(colors['alert']),1,Qt.PenStyle.DotLine))
                painter.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom()))
        painter.setPen(color)
        painter.drawText(6,self.height()-5,'2 min ago')
        painter.drawText(max(6,self.width()-115),self.height()-5,f'{top:.0f} {self.unit} / Now')
        if not points:
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Waiting for samples')

    def mouseMoveEvent(self, event):
        points = self._points()
        if not points:
            return
        now = monotonic()
        fraction = min(1,max(0,(event.position().x()-6)/max(1,self.width()-12)))
        stamp, data = min(points,key=lambda item:abs(item[0]-(now-120+120*fraction)))
        text = [f'{max(0,now-stamp):.0f}s ago']
        for key,label,_ in self.fields:
            value=data.get(key)
            text.append(f'{label}: {value:.1f} {self.unit}' if value is not None else f'{label}: unavailable')
        text += [label for time,label in self.events.property('resource_markers') or () if abs(time-stamp)<1]
        QToolTip.showText(event.globalPosition().toPoint(),'\n'.join(text),self)

    def leaveEvent(self, event):
        QToolTip.hideText()
