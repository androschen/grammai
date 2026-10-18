"""Reading-first sentence presentation shared by the details panel/dialog."""
from difflib import SequenceMatcher
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,
    QPushButton,QPlainTextEdit,QComboBox,QTabWidget,QScrollArea,QTextBrowser,QCheckBox,QSizePolicy)
from core.config import LANGUAGE_LABELS
from ui.copyable_text import CopyableLabel


def highlighted(before,after):
    old=[];new=[]
    for tag,a,b,c,d in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
        left,right=escape(before[a:b]),escape(after[c:d])
        old.append(left if tag=='equal' else '<span style="background:#633c3c;color:#ffe0e0;text-decoration:line-through">'+left+'</span>')
        new.append(right if tag=='equal' else '<span style="background:#254c3b;color:#d8ffe9">'+right+'</span>')
    return ''.join(old),''.join(new)


class HistoryComparison(QTextBrowser):
    """Fit short revision comparisons instead of reserving a large empty editor."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('translationHistory');self.setOpenExternalLinks(False)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_content)
    def fit_content(self,*args):
        from math import ceil
        height=min(420,max(120,ceil(self.document().size().height())+20))
        if self.height()!=height:self.setFixedHeight(height)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_content()


def build_details(study,update,store,analysis,history):
    from PySide6.QtWidgets import QDialog
    from ui.icons import icon_button
    study.setWindowTitle('Sentence details');study.resize(480,700)
    outer=QVBoxLayout(study);outer.setContentsMargins(14,12,14,12);outer.setSpacing(8)
    header=QHBoxLayout();title=QLabel('Sentence');title.setObjectName('field');header.addWidget(title);header.addStretch()
    study.replay=icon_button('play','Replay retained audio',study)
    study.speed=QComboBox();study.speed.addItem('1×',1.);study.speed.addItem('0.8×',.8);study.speed.setFixedWidth(78);study.speed.setAccessibleName('Replay speed')
    def replay():
        available=bool(study.subtitle.audio_id and store.get(study.subtitle.audio_id) is not None)
        if available:study.events.replay_requested.emit(study.subtitle.audio_id,study.speed.currentData())
        else:study.feedback.setText('Audio is unavailable or has expired.')
    study.replay.clicked.connect(replay);header.addWidget(study.replay);header.addWidget(study.speed)
    study.bookmark=icon_button('bookmark','Save to deck',study);header.addWidget(study.bookmark)
    more=icon_button('more','Audio and transcript tools',study);more.setCheckable(True);header.addWidget(more)
    close=icon_button('close','Close sentence details',study);close.clicked.connect(study.reject);header.addWidget(close);outer.addLayout(header)
    tabs=QTabWidget();study.pages=tabs;outer.addWidget(tabs,1)
    body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(8,12,8,12);layout.setSpacing(7);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(body);tabs.addTab(scroll,'Sentence')
    def section(name,heading):
        frame=QFrame();frame.setObjectName(name);frame.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        box=QVBoxLayout(frame);box.setContentsMargins(10,10,10,10);box.setSpacing(5)
        caption=QLabel(heading);caption.setObjectName('hint');box.addWidget(caption)
        layout.addWidget(frame)
        return frame,box
    study.reading_section,source_box=section('sentenceReadingSection','Original speech')
    study.route_label=QLabel();study.route_label.setObjectName('hint');source_box.addWidget(study.route_label)
    study.source_display=CopyableLabel();study.source_display.setWordWrap(True);study.source_display.setStyleSheet('font-size:20px;font-weight:500;');source_box.addWidget(study.source_display)
    study.pronunciation=CopyableLabel();study.pronunciation.setWordWrap(True);study.pronunciation.setObjectName('phonetic');source_box.addWidget(study.pronunciation)
    study.translation_section,translation_box=section('sentenceTranslationSection','Translation')
    study.translation_display=CopyableLabel();study.translation_display.setWordWrap(True);study.translation_display.setStyleSheet('font-size:16px;');translation_box.addWidget(study.translation_display)
    study.target_pronunciation=CopyableLabel();study.target_pronunciation.setWordWrap(True);study.target_pronunciation.setObjectName('phonetic');translation_box.addWidget(study.target_pronunciation)
    for label in (study.route_label,study.source_display,study.pronunciation,study.translation_display,study.target_pronunciation):
        label.setTextFormat(Qt.TextFormat.PlainText);label.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop);label.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
    def explain_selection(phrase,original):
        from dataclasses import replace
        candidate=study._proposal or study.subtitle
        value=replace(candidate,native_text=study.text.toPlainText())
        study.events.phrase_explain_requested.emit({'update':value,'phrase':phrase,'sentence':study.source_display.text() if original else study.translation_display.text(),'language':study.source.currentData() if original else study.target.currentData(),'text_role':'original' if original else 'translation'})
    study.source_display.explain_handler=lambda phrase:explain_selection(phrase,True)
    study.translation_display.explain_handler=lambda phrase:explain_selection(phrase,False)
    tools=QWidget();tool_layout=QVBoxLayout(tools);tool_layout.setContentsMargins(0,0,0,0);tools.hide();more.toggled.connect(tools.setVisible);layout.addWidget(tools)
    actions=QHBoxLayout();stop=icon_button('stop','Stop replay',study);stop.clicked.connect(lambda:study.events.replay_requested.emit('',1.));actions.addWidget(stop)
    study.recheck=QPushButton('Recheck audio');study.recheck.clicked.connect(study._recheck);study.recheck.setToolTip('One audio recheck; expired audio uses text-only retranslation. Temporarily pauses live inference.');actions.addWidget(study.recheck)
    study.edit=QPushButton('Edit transcript');study.edit.setCheckable(True);actions.addWidget(study.edit);tool_layout.addLayout(actions)
    editor=QWidget();edit_layout=QVBoxLayout(editor);edit_layout.setContentsMargins(0,0,0,0)
    study.text=QPlainTextEdit(update.native_text);study.text.setMaximumHeight(90);study.text.setReadOnly(True);study.text.setAccessibleName('Original transcript to correct');edit_layout.addWidget(study.text)
    route=QHBoxLayout();study.source=QComboBox();study.target=QComboBox()
    for language,label in LANGUAGE_LABELS.items():study.source.addItem(label,language.value);study.target.addItem(label,language.value)
    study.source.setCurrentIndex(study.source.findData(update.source_language));study.target.setCurrentIndex(max(0,study.target.findData(update.target_language)))
    for combo in (study.source,study.target):combo.setMinimumContentsLength(6);combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    route.addWidget(study.source,1);route.addWidget(QLabel('→'));route.addWidget(study.target,1);edit_layout.addLayout(route)
    study.translate=QPushButton('Retranslate');study.translate.clicked.connect(study._translate);edit_layout.addWidget(study.translate);layout.addWidget(editor);editor.hide()
    study.edit.toggled.connect(editor.setVisible);study.edit.toggled.connect(lambda checked:study.text.setReadOnly(not checked or study._busy))
    study.apply_recheck=QPushButton('Use reviewed revision');study.apply_recheck.hide();study.apply_recheck.setEnabled(False);study.apply_recheck.clicked.connect(study._apply_recheck);layout.addWidget(study.apply_recheck)
    study.revision=QLabel();study.revision.hide()
    study.history_section=QFrame();study.history_section.setObjectName('sentenceHistorySection');study.history_section.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
    history_box=QVBoxLayout(study.history_section);history_box.setContentsMargins(10,12,10,10);history_box.setSpacing(5)
    study.compare_toggle=QLabel('Translation history');study.compare_toggle.setObjectName('field');history_box.addWidget(study.compare_toggle)
    study.comparison=HistoryComparison(study);history_box.addWidget(study.comparison);layout.addWidget(study.history_section)
    study.result=QPlainTextEdit(study);study.result.hide();study.original=QPlainTextEdit(study);study.original.hide()
    study.feedback=QLabel();study.feedback.setObjectName('hint');study.feedback.setWordWrap(True);study.feedback.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum);layout.addWidget(study.feedback)
    layout.addStretch(1)
    # Separate save popup: opening, editing, and saving never trigger inference.
    study.save_popup=QDialog(study);study.save_popup.setWindowTitle('Save to deck');study.save_popup.setWindowModality(Qt.WindowModality.WindowModal);study.save_popup.resize(430,450)
    saving=QVBoxLayout(study.save_popup);saving.setContentsMargins(16,14,16,14);saving.setSpacing(8)
    save_header=QHBoxLayout();save_title=QLabel('Save to deck');save_title.setObjectName('field');save_header.addWidget(save_title);save_header.addStretch()
    save_close=icon_button('close','Close save popup',study.save_popup);save_close.clicked.connect(study.save_popup.reject);save_header.addWidget(save_close);saving.addLayout(save_header)
    study.save_preview=CopyableLabel();study.save_preview.setWordWrap(True);saving.addWidget(study.save_preview)
    saving.addWidget(QLabel('Meaning'));study.save_meaning=QPlainTextEdit(update.target_text);study.save_meaning.setMaximumHeight(85);study.save_meaning.setAccessibleName('Reviewed meaning to save');saving.addWidget(study.save_meaning)
    study.notes=QPlainTextEdit();study.notes.setMaximumHeight(70);study.notes.setPlaceholderText('Notes · optional');saving.addWidget(study.notes)
    study.reviewed=QCheckBox('I checked the original and meaning');saving.addWidget(study.reviewed)
    study.save=QPushButton('Save to deck');study.save.setEnabled(False);study.save.clicked.connect(study._save);saving.addWidget(study.save)
    study.learning_feedback=QLabel();study.learning_feedback.setWordWrap(True);saving.addWidget(study.learning_feedback);saving.addStretch()
    study._save_snapshot=study.subtitle;study._save_stale=False
    def save_enabled():study.save.setEnabled(study.reviewed.isChecked() and not study._busy and study._proposal is None and not study._save_stale)
    study.reviewed.toggled.connect(save_enabled)
    study.save_meaning.textChanged.connect(lambda:study.reviewed.setChecked(False))
    def open_save():
        if study._busy or study._proposal or study.text.toPlainText()!=study.subtitle.native_text:
            study.feedback.setText('Finish reviewing the transcript before saving.');return
        study._save_snapshot=study.subtitle;study._save_stale=False;study.reviewed.setChecked(False)
        study.save_meaning.setPlainText(study.subtitle.target_text);study.learning_feedback.setText('Text only · No audio saved');study.save_popup.open()
    study.bookmark.clicked.connect(open_save)
    def refresh():
        snapshot=(study.text.toPlainText(),study.subtitle.target_text,study.source.currentData(),study.target.currentData())
        if snapshot!=getattr(study,'_review_snapshot',None):
            study.reviewed.setChecked(False);study._review_snapshot=snapshot
            if study.save_popup.isVisible():
                study._save_stale=True;study.learning_feedback.setText('Sentence changed. Close and reopen this popup to review the latest wording.')
        save_enabled();study.save_preview.setText(study.subtitle.native_text+'\n'+study.subtitle.native_phonetics)
        candidate=study._proposal or study.subtitle
        source=study.text.toPlainText();study.source_display.setText(source);study.translation_display.setText(candidate.target_text or 'Translation unavailable')
        study.translation_section.setVisible(candidate.target_text!=source or not candidate.target_text)
        study.translation_display.setVisible(candidate.target_text!=source or not candidate.target_text)
        study.pronunciation.setText(candidate.native_phonetics);study.pronunciation.setVisible(bool(candidate.native_phonetics))
        study.target_pronunciation.setText(candidate.phonetics);study.target_pronunciation.setVisible(bool(candidate.phonetics and candidate.phonetics!=candidate.native_phonetics))
        study.route_label.setText(study.source.currentText()+' → '+study.target.currentText())
        study.replay.setEnabled(bool(study.subtitle.audio_id and store.get(study.subtitle.audio_id) is not None))
        study.replay.setToolTip('Replay retained audio' if study.replay.isEnabled() else 'Audio is unavailable or has expired')
        first_source=study.subtitle.original_native_text if study.subtitle.original_native_text is not None else study.subtitle.native_text
        first_target=study.subtitle.original_target_text if study.subtitle.original_target_text is not None else study.subtitle.target_text
        parts=[]
        for heading,before,after in (('Transcript changes',first_source,candidate.native_text),('Translation history',first_target,candidate.target_text)):
            if before==after:continue
            left,right=highlighted(before,after);parts.append(('<h3>'+heading+'</h3>' if heading=='Transcript changes' else '')+'<p>First version</p><p>'+left+'</p><p>Current'+(' / proposed' if study._proposal else '')+'</p><p>'+right+'</p>')
        study.comparison.setHtml(''.join(parts));study.comparison.fit_content();study.comparison.setVisible(bool(parts));study.compare_toggle.setVisible(bool(parts));study.history_section.setVisible(bool(parts))
    study._refresh_details=refresh
    study.text.textChanged.connect(refresh);study.result.textChanged.connect(refresh);study.original.textChanged.connect(refresh);study.source.currentIndexChanged.connect(refresh);study.target.currentIndexChanged.connect(refresh)
    study._show_result();study._show_revision();refresh();study.events.review_finished.connect(study._finished)
    study.analysis_widget=None
    if analysis is not None:
        from ui.analysis import SentenceAnalysis
        study.analysis_widget=SentenceAnalysis(study,analysis,history);study.analysis_widget.applied.connect(study._apply_analysis)
        analysis_scroll=QScrollArea();analysis_scroll.setWidgetResizable(True);analysis_scroll.setFrameShape(QFrame.Shape.NoFrame);analysis_scroll.setWidget(study.analysis_widget);tabs.addTab(analysis_scroll,'Meaning & context')
