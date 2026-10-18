"""Small palette-aware vector icons, requiring no font or network dependency."""
from PySide6.QtCore import Qt,QRectF,QSize,QPointF
from PySide6.QtGui import QIcon,QIconEngine,QPainter,QPen,QPixmap,QPalette,QColor
from PySide6.QtWidgets import QPushButton,QApplication

class LineIcon(QIconEngine):
    def __init__(self,name):super().__init__();self.name=name
    def clone(self):return LineIcon(self.name)
    def pixmap(self,size,mode,state):
        pix=QPixmap(size);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);self.paint(p,QRectF(0,0,size.width(),size.height()),mode,state);p.end();return pix
    def paint(self,painter,rect,mode,state):
        p=painter;p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing);p.translate(rect.x(),rect.y());p.scale(rect.width()/24,rect.height()/24)
        color=QColor('#e7eded' if QApplication.instance().property('grammai_theme')!='light' else '#24372e')
        p.setPen(QPen(color,1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(Qt.BrushStyle.NoBrush)
        def line(a,b,c,d):p.drawLine(QPointF(a,b),QPointF(c,d))
        n=self.name
        paths={'play':[(8,5,18,12),(18,12,8,19),(8,19,8,5)],'pause':[(8,5,8,19),(16,5,16,19)],'chevron':[(9,6,15,12),(15,12,9,18)],'close':[(6,6,18,18),(18,6,6,18)],'bookmark':[(6,4,18,4),(18,4,18,20),(18,20,12,16),(12,16,6,20),(6,20,6,4)],'chart':[(4,4,4,20),(4,20,21,20),(7,15,11,10),(11,10,15,13),(15,13,20,6)],'route':[(4,7,19,7),(16,4,19,7),(19,7,16,10),(20,17,5,17),(8,14,5,17),(5,17,8,20)],'trash':[(7,7,8,20),(8,20,17,20),(17,20,18,7),(5,6,20,6),(9,3,16,3)],'search':[(15,15,21,21)],'audio':[(5,13,5,19),(19,13,19,19)],'appearance':[(12,4,12,20)],'sparkles':[(12,3,14,9),(14,9,20,11),(20,11,14,13),(14,13,12,19),(12,19,10,13),(10,13,4,11),(4,11,10,9),(10,9,12,3),(19,2,19,6),(17,4,21,4)],'edit':[(5,16,16,5),(16,5,19,8),(19,8,8,19),(8,19,4,20),(4,20,5,16)],'stop':[(6,6,18,6),(18,6,18,18),(18,18,6,18),(6,18,6,6)]}
        for segment in paths.get(n,[]):line(*segment)
        if n in ('cc','cc-on'):
            if n=='cc-on':
                p.setBrush(color);p.drawRoundedRect(QRectF(2,4,20,15),2,2)
                inverse=QColor('#111617' if QApplication.instance().property('grammai_theme')!='light' else '#f3f6f3')
                p.setPen(QPen(inverse,1.9,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            else:p.drawRoundedRect(QRectF(2,4,20,15),2,2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for x in (5,13):p.drawArc(QRectF(x,8,6,7),45*16,270*16)
        elif n=='sliders':
            for y,x in ((6,9),(12,16),(18,7)):
                line(3,y,x-2,y);line(x+2,y,21,y);p.drawEllipse(QRectF(x-2,y-2,4,4))
        elif n=='more':
            for x in (5,12,19):p.drawEllipse(QRectF(x-1,11,2,2))
        elif n=='sun':
            p.drawEllipse(QRectF(8,8,8,8))
            for segment in [(12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12),(5,5,7,7),(17,17,19,19),(5,19,7,17),(17,7,19,5)]:line(*segment)
        elif n=='moon':
            from PySide6.QtGui import QPainterPath
            path=QPainterPath();path.moveTo(17,3);path.cubicTo(3,-1,0,17,11,21);path.cubicTo(17,23,22,18,22,13);path.cubicTo(13,18,8,8,17,3);p.drawPath(path)
        elif n=='conversation':p.drawRoundedRect(QRectF(4,4,16,13),3,3);line(8,17,7,21);line(7,21,13,17)
        elif n=='overlay':p.drawRoundedRect(QRectF(3,5,18,14),2,2);line(7,14,17,14);line(9,17,15,17)
        elif n=='audio':p.drawArc(QRectF(4,3,16,17),0,180*16)
        elif n=='settings':
            p.drawEllipse(QRectF(5,5,14,14));p.drawEllipse(QRectF(9,9,6,6))
            for a,b,c,d in [(12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12)]:line(a,b,c,d)
        elif n=='appearance':p.drawEllipse(QRectF(4,4,16,16))
        elif n=='search':p.drawEllipse(QRectF(4,4,12,12))
        p.restore()

def set_button_icon(button,name):button.setIcon(QIcon(LineIcon(name)));button.setIconSize(QSize(19,19))
def icon_button(name,label,parent=None):
    button=QPushButton(parent);button.setObjectName('iconButton');button.setFixedSize(36,36);button.setToolTip(label);button.setAccessibleName(label);set_button_icon(button,name);return button


def compact_action(button,name,label):
    """Keep existing signal connections while giving a common action an icon."""
    button.setText('');button.setObjectName('iconButton');button.setFixedSize(32,32)
    button.setAccessibleName(label);button.setToolTip(label);set_button_icon(button,name)
