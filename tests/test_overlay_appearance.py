"""Appearance preview rollback, transparency endpoints, and overlay safety."""
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.config import AppConfig
from core.events import EventBus,SubtitleUpdate
from core.preferences import save_config,load_config
from ui.overlay import SubtitleOverlay
from ui.settings import SettingsDialog

APP=QApplication.instance() or QApplication([])


class OverlayAppearanceTests(unittest.TestCase):
    def test_preview_does_not_mutate_preferences_and_cancel_restores(self):
        config=AppConfig(overlay_opacity=140)
        events=EventBus()
        overlay=SubtitleOverlay(events,config)
        with patch('ui.settings.list_audio_sources',return_value=[]):
            dialog=SettingsDialog(config,events,page=2)
        state_events=[]
        events.state_changed.connect(state_events.append)
        dialog.appearance.opacity.setValue(0)
        QTest.qWait(60)
        self.assertEqual(overlay.appearance.overlay_opacity,0)
        self.assertEqual(config.overlay_opacity,140)
        self.assertEqual(state_events,[])
        dialog.reject()
        self.assertEqual(overlay.appearance.overlay_opacity,140)
        self.assertIsNone(overlay._preview_config)
        overlay.close()

    def test_apply_keeps_new_opacity_when_dialog_is_cancelled_later(self):
        config=AppConfig()
        events=EventBus()
        overlay=SubtitleOverlay(events,config)
        with patch('ui.settings.list_audio_sources',return_value=[]):
            dialog=SettingsDialog(config,events,page=2)
        dialog.appearance.opacity.setValue(100)
        self.assertTrue(dialog.apply())
        self.assertEqual(config.overlay_opacity,255)
        dialog.appearance.opacity.setValue(0)
        QTest.qWait(60)
        dialog.reject()
        self.assertEqual(overlay.appearance.overlay_opacity,255)
        overlay.close()

    def test_zero_background_keeps_opaque_text(self):
        config=AppConfig(overlay_opacity=0,overlay_show_hud=False,overlay_show_original=False,
            show_pronunciation=False,overlay_text_outline=False,overlay_text_shadow=False)
        overlay=SubtitleOverlay(EventBus(),config,preview=True)
        overlay.apply_subtitle(SubtitleUpdate('','Readable subtitles',''))
        overlay.resize(*overlay.fit_content(700))
        overlay.show()
        QTest.qWait(10)
        image=overlay.grab().toImage()
        rect=overlay._stack.geometry()
        point=(rect.left()+6,rect.center().y())
        self.assertEqual(image.pixelColor(*point).alpha(),0)
        opaque_white=sum(1 for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x,y).alpha()>245 and image.pixelColor(x,y).red()>240)
        self.assertGreater(opaque_white,10)
        overlay.preview_appearance(replace(config,overlay_opacity=255))
        self.assertEqual(overlay.grab().toImage().pixelColor(*point).alpha(),255)
        self.assertEqual(overlay.windowOpacity(),1.)
        overlay.close()

    def test_presets_and_independent_hud(self):
        with patch('ui.settings.list_audio_sources',return_value=[]):
            dialog=SettingsDialog(AppConfig(),EventBus(),page=2)
        editor=dialog.appearance
        editor.preset.setCurrentText('Cinema')
        QTest.qWait(60)
        self.assertFalse(editor.preview.overlay._hud.isVisible())
        self.assertTrue(editor.outline.isChecked())
        self.assertFalse(editor.show_original.isChecked())
        self.assertFalse(editor.pronunciation.isChecked())
        self.assertFalse(dialog._pronunciation.isChecked())
        editor.preset.setCurrentText('High contrast')
        self.assertEqual(editor.opacity.value(),90)
        self.assertEqual(editor.font_size.value(),34)
        editor.preset.setCurrentText('Learning')
        self.assertEqual(editor.opacity.value(),55)
        self.assertTrue(editor.pronunciation.isChecked())
        dialog.reject()

    def test_preferences_restore_all_appearance_fields(self):
        config=AppConfig(overlay_opacity=0,overlay_hud_opacity=30,overlay_show_hud=False,
            overlay_show_original=False,overlay_text_outline=False,overlay_text_shadow=False,
            overlay_max_width=55,overlay_padding=12,overlay_corner_radius=4)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder,patch.dict(os.environ,GRAMMAI_DATA_DIR=folder):
            save_config(config)
            loaded=load_config()
        for name in ('overlay_opacity','overlay_hud_opacity','overlay_show_hud','overlay_show_original',
            'overlay_text_outline','overlay_text_shadow','overlay_max_width','overlay_padding','overlay_corner_radius'):
            self.assertEqual(getattr(loaded,name),getattr(config,name))

    def test_real_overlay_retains_clickthrough_flags_and_compact_layout(self):
        overlay=SubtitleOverlay(EventBus(),AppConfig(overlay_show_hud=False,show_pronunciation=False,overlay_show_original=False))
        flags=overlay.windowFlags()
        for flag in (Qt.WindowType.FramelessWindowHint,Qt.WindowType.WindowStaysOnTopHint,Qt.WindowType.WindowTransparentForInput):
            self.assertTrue(flags&flag)
        overlay.apply_subtitle(SubtitleUpdate('','Hello',''))
        overlay._place_at_bottom()
        short_width=overlay.width()
        short_height=overlay.height()
        font=overlay._stack.target.font().toString()
        overlay.apply_subtitle(SubtitleUpdate('','A much longer sentence that should wrap naturally across the screen. '*4,''))
        overlay._place_at_bottom()
        self.assertEqual(overlay.width(),short_width)
        self.assertEqual(overlay.height(),short_height)
        self.assertEqual(overlay._stack.target.font().toString(),font)
        self.assertGreater(len(overlay._pages[0][1]),1)
        full=overlay._stack.target.text()
        overlay._next_page()
        self.assertEqual(overlay._stack.target.text(),full)
        self.assertEqual(overlay.height(),short_height)
        overlay.reset_text()
        self.assertEqual(overlay._page,0)
        self.assertFalse(overlay._page_timer.isActive())
        self.assertGreater(overlay.height(),80)
        overlay.close()
