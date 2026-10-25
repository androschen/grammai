"""Subtitle appearance editor with the real renderer over a sample scene."""
from dataclasses import replace
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QColor,QLinearGradient,QPainter
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QSlider,QComboBox,QCheckBox,QSpinBox,QPushButton
from core.events import EventBus,SubtitleUpdate
from ui.overlay import SubtitleOverlay

APPEARANCE_PRESETS={
    'Cinema':dict(opacity=12,hud_opacity=0,show_hud=False,show_original=False,pronunciation=False,
        outline=True,shadow=True,font_size=30,padding=12,corners=12,max_width=80),
    'Learning':dict(opacity=55,hud_opacity=75,show_hud=True,show_original=True,pronunciation=True,
        outline=True,shadow=True,font_size=28,padding=18,corners=16,max_width=72),
    'High contrast':dict(opacity=90,hud_opacity=100,show_hud=True,show_original=True,pronunciation=True,
        outline=True,shadow=True,font_size=34,padding=24,corners=16,max_width=80),
}


class SubtitlePreview(QWidget):
    def __init__(self,config,parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.setMinimumWidth(200)
        self.setAccessibleName('Live subtitle appearance preview over a sample scene')
        self.config=replace(config)
        self.events=EventBus(self)
        self.overlay=SubtitleOverlay(self.events,self.config,self,preview=True)
        self.overlay.apply_subtitle(SubtitleUpdate('Nǐ hǎo, jīntiān zěnmeyàng?','你好，今天怎么样？','Hello, how are you today?'))
        self.overlay._hud.meter.update_volume(46)

    def apply(self,config):
        self.config=replace(config)
        self.overlay.preview_appearance(self.config)
        self.arrange()
        self.update()

    def arrange(self):
        if not hasattr(self,'overlay'):
            return
        width,height=self.overlay.fit_content(max(200,(self.width()-16)*self.config.overlay_max_width/100))
        # The sample is intentionally scaled to the editor, not to desktop pixels.
        self.setMinimumHeight(max(230,min(520,height+44)))
        self.overlay.resize(width,height)
        self.overlay.move((self.width()-width)//2,max(24,self.height()-height-8))
        self.overlay.layout().activate()

    def resizeEvent(self,event):
        self.arrange()
        super().resizeEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        gradient.setColorAt(0,QColor('#293b36'))
        gradient.setColorAt(1,QColor('#18211f'))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(),14,14)
        painter.setBrush(QColor(40,67,61,110))
        painter.drawEllipse(-50,self.height()-100,self.width()+100,250)
        painter.setPen(QColor('#ffffff'))
        painter.drawText(14,22,'LIVE PREVIEW  /  sample scene')


class AppearanceEditor(QWidget):
    def __init__(self,config,events,parent=None):
        super().__init__(parent)
        self.config,self.events=config,events
        self._loading=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
        self.theme=QComboBox();self.theme.addItem('Dark','dark');self.theme.addItem('Light','light');self.theme.setCurrentIndex(max(0,self.theme.findData(config.theme)))
        self.preset=QComboBox();self.preset.addItems(['Custom','Cinema','Learning','High contrast'])
        self.opacity=self._slider(0,100,round(config.overlay_opacity*100/255))
        self.hud_opacity=self._slider(0,100,config.overlay_hud_opacity)
        self.max_width=self._slider(35,95,config.overlay_max_width)
        self.font_size=self._spin(16,48,config.subtitle_font_size)
        self.padding=self._spin(8,36,config.overlay_padding);self.corners=self._spin(0,32,config.overlay_corner_radius)
        form=QFormLayout();form.setVerticalSpacing(10);form.addRow('App theme',self.theme);form.addRow('Subtitle style',self.preset)
        form.addRow('Background opacity',self._slider_row(self.opacity,'%'));form.addRow('Subtitle text size',self.font_size);layout.addLayout(form)
        self.preview=SubtitlePreview(config,self);layout.addWidget(self.preview)
        hint=QLabel('Preview changes here and on active subtitles. Save changes to keep them. Leaving Settings restores the saved appearance.')
        hint.setObjectName('hint');hint.setWordWrap(True);layout.addWidget(hint)
        self.outline=self._check('Text outline',config.overlay_text_outline);self.shadow=self._check('Text shadow',config.overlay_text_shadow)
        self.show_hud=self._check('Device, languages and sound meter',config.overlay_show_hud)
        self.show_original=self._check('Show original transcript',config.overlay_show_original);self.pronunciation=self._check('Show Pinyin / Thai pronunciation',config.show_pronunciation)
        layout.addWidget(self.show_original);layout.addWidget(self.pronunciation)
        self.position=QComboBox();self.position.addItem('Bottom of screen','bottom');self.position.addItem('Top of screen','top');self.position.setCurrentIndex(max(0,self.position.findData(config.overlay_position)))
        advanced=QWidget();details=QVBoxLayout(advanced);details.setContentsMargins(0,6,0,0)
        form=QFormLayout();form.addRow('Maximum screen width',self._slider_row(self.max_width,'%'));form.addRow('HUD opacity',self._slider_row(self.hud_opacity,'%'));form.addRow('Panel padding',self.padding);form.addRow('Corner rounding',self.corners);form.addRow('Subtitle position',self.position);details.addLayout(form)
        self.show_overlay=self._check('Show floating subtitles while translating',config.show_overlay)
        for widget in (self.outline,self.shadow,self.show_hud,self.show_overlay):details.addWidget(widget)
        toggle=QPushButton('Advanced subtitle layout');toggle.setCheckable(True);toggle.toggled.connect(advanced.setVisible);layout.addWidget(toggle);layout.addWidget(advanced);advanced.hide()
        self._style_widgets=(self.opacity,self.hud_opacity,self.max_width,self.font_size,self.padding,self.corners,
            self.position,self.outline,self.shadow,self.show_hud,self.show_original,self.pronunciation)
        for widget in self._style_widgets:
            signal=(widget.valueChanged if isinstance(widget,(QSlider,QSpinBox)) else
                widget.toggled if isinstance(widget,QCheckBox) else widget.currentIndexChanged)
            signal.connect(self._changed)
        self.preset.currentTextChanged.connect(self._preset)
        self._preview_timer=QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(30)
        self._preview_timer.timeout.connect(self._preview)
        self.preview.apply(config)

    def _slider(self,low,high,value):
        widget=QSlider(Qt.Orientation.Horizontal)
        widget.setRange(low,high)
        widget.setValue(value)
        return widget

    def _slider_row(self,slider,suffix):
        row=QHBoxLayout()
        row.addWidget(slider,1)
        value=QLabel(f'{slider.value()}{suffix}')
        value.setMinimumWidth(42)
        value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda number:value.setText(f'{number}{suffix}'))
        row.addWidget(value)
        return row

    def _spin(self,low,high,value):
        widget=QSpinBox()
        widget.setRange(low,high)
        widget.setValue(value)
        return widget

    def _check(self,label,value):
        widget=QCheckBox(label)
        widget.setChecked(value)
        return widget

    def _preset(self,name):
        if name not in APPEARANCE_PRESETS:
            return
        self._loading=True
        for key,value in APPEARANCE_PRESETS[name].items():
            widget=getattr(self,key)
            widget.setChecked(value) if isinstance(widget,QCheckBox) else widget.setValue(value)
        self._loading=False
        self._preview_timer.start()

    def _changed(self):
        if self._loading:
            return
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(0)
        self._preview_timer.start()

    def apply_to(self,config):
        config.theme=self.theme.currentData()
        config.subtitle_font_size=self.font_size.value()
        config.overlay_opacity=round(self.opacity.value()*255/100)
        config.overlay_hud_opacity=self.hud_opacity.value()
        config.overlay_max_width=self.max_width.value()
        config.overlay_padding=self.padding.value()
        config.overlay_corner_radius=self.corners.value()
        config.overlay_position=self.position.currentData()
        config.overlay_text_outline=self.outline.isChecked()
        config.overlay_text_shadow=self.shadow.isChecked()
        config.overlay_show_hud=self.show_hud.isChecked()
        config.overlay_show_original=self.show_original.isChecked()
        config.show_pronunciation=self.pronunciation.isChecked()
        config.show_overlay=self.show_overlay.isChecked()
        return config

    def _preview(self):
        draft=self.apply_to(replace(self.config))
        self.preview.apply(draft)
        self.events.overlay_appearance_preview.emit(draft)

    def restore(self):
        self._preview_timer.stop()
        self.events.overlay_appearance_preview.emit(None)
