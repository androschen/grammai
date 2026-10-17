"""Reading-first sentence presentation shared by the details panel/dialog."""
from difflib import SequenceMatcher
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,
    QPushButton,QPlainTextEdit,QComboBox,QTabWidget,QScrollArea,QTextBrowser)
from core.config import LANGUAGE_LABELS


def highlighted(before,after):
    old=[];new=[]
    for tag,a,b,c,d in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
        left,right=escape(before[a:b]),escape(after[c:d])
        old.append(left if tag=='equal' else '<span style="background:#633c3c;color:#ffe0e0;text-decoration:line-through">'+left+'</span>')
        new.append(right if tag=='equal' else '<span style="background:#254c3b;color:#d8ffe9">'+right+'</span>')
    return ''.join(old),''.join(new)


def build_details(study,update,store,analysis,history):
    study.setWindowTitle('Sentence details')
    study.resize(540,700)
    outer=QVBoxLayout(study)
    outer.setContentsMargins(14,14,14,14)
    outer.setSpacing(12)
    header=QHBoxLayout()
    title=QLabel('Sentence details');title.setObjectName('field')
    header.addWidget(title);header.addStretch()
    close=QPushButton('Close');close.clicked.connect(study.reject)
    header.addWidget(close);outer.addLayout(header)
    tabs=QTabWidget();outer.addWidget(tabs,1)
    body=QWidget();layout=QVBoxLayout(body);layout.setSpacing(14)
    scroll=QScrollArea();scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(body)
    tabs.addTab(scroll,'Sentence')
    study.route_label=QLabel();study.route_label.setObjectName('hint')
    layout.addWidget(study.route_label)

    def card(heading,name):
        frame=QFrame();frame.setObjectName(name)
        box=QVBoxLayout(frame);box.setContentsMargins(18,16,18,16);box.setSpacing(8)
        label=QLabel(heading);label.setObjectName('hint');box.addWidget(label)
        hero=QLabel();hero.setWordWrap(True);hero.setTextFormat(Qt.TextFormat.PlainText)
        hero.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hero.setStyleSheet('font-size:22px; font-weight:500;')
        box.addWidget(hero);layout.addWidget(frame)
        return box,hero
    source_box,study.source_display=card('ORIGINAL SPEECH','sentenceSource')
    study.pronunciation=QLabel();study.pronunciation.setWordWrap(True)
    study.pronunciation.setObjectName('phonetic');source_box.addWidget(study.pronunciation)
    controls=QHBoxLayout()
    available=bool(update.audio_id and store.get(update.audio_id) is not None)
    for label,speed in (('Play',1.),('0.8\u00d7',.8)):
        button=QPushButton(label);button.setEnabled(available)
        button.setToolTip('Replay retained audio' if available else 'Audio is unavailable or has expired')
        button.clicked.connect(lambda checked=False,s=speed:study.events.replay_requested.emit(study.subtitle.audio_id,s))
        controls.addWidget(button)
    stop=QPushButton('Stop');stop.clicked.connect(lambda:study.events.replay_requested.emit('',1.));controls.addWidget(stop)
    study.recheck=QPushButton('Recheck');study.recheck.clicked.connect(study._recheck)
    study.recheck.setToolTip('Manual audio recheck, or text-only retranslation if audio expired. Temporarily pauses live recognition.')
    controls.addWidget(study.recheck);layout.addLayout(controls)
    translation_box,study.translation_display=card('TRANSLATION','sentenceTranslation')
    study.target_pronunciation=QLabel();study.target_pronunciation.setObjectName('phonetic');study.target_pronunciation.setWordWrap(True)
    translation_box.addWidget(study.target_pronunciation)
    study.revision=QLabel();study.revision.setWordWrap(True);study.revision.setObjectName('hint');layout.addWidget(study.revision)
    actions=QHBoxLayout()
    study.edit=QPushButton('Edit transcript');study.edit.setCheckable(True);actions.addWidget(study.edit)
    study.apply_recheck=QPushButton('Apply revision');study.apply_recheck.hide();study.apply_recheck.setEnabled(False)
    study.apply_recheck.clicked.connect(study._apply_recheck);actions.addWidget(study.apply_recheck)
    actions.addStretch();layout.addLayout(actions)
    editor=QWidget();edit_layout=QVBoxLayout(editor);edit_layout.setContentsMargins(0,0,0,0)
    study.text=QPlainTextEdit(update.native_text);study.text.setMaximumHeight(100);study.text.setReadOnly(True)
    study.text.setAccessibleName('Original transcript to correct');edit_layout.addWidget(study.text)
    route=QHBoxLayout();study.source=QComboBox();study.target=QComboBox()
    for language,label in LANGUAGE_LABELS.items():
        study.source.addItem(label,language.value);study.target.addItem(label,language.value)
    study.source.setCurrentIndex(study.source.findData(update.source_language))
    study.target.setCurrentIndex(max(0,study.target.findData(update.target_language)))
    for combo in (study.source,study.target):
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    route.addWidget(study.source,1);route.addWidget(QLabel('\u2192'));route.addWidget(study.target,1);edit_layout.addLayout(route)
    study.translate=QPushButton('Translate edited text');study.translate.clicked.connect(study._translate);edit_layout.addWidget(study.translate)
    layout.addWidget(editor);editor.hide()
    study.edit.toggled.connect(editor.setVisible)
    study.edit.toggled.connect(lambda checked:study.text.setReadOnly(not checked or study._busy))
    study.compare_toggle=QPushButton('Compare original');study.compare_toggle.setCheckable(True)
    layout.addWidget(study.compare_toggle)
    study.comparison=QTextBrowser();study.comparison.setOpenExternalLinks(False);study.comparison.setMinimumHeight(220)
    layout.addWidget(study.comparison);study.comparison.hide();study.compare_toggle.toggled.connect(study.comparison.setVisible)
    # Keep plain values for the analysis/editor API; presentation is rendered above.
    study.result=QPlainTextEdit(study);study.result.hide()
    study.original=QPlainTextEdit(study);study.original.hide()
    study.notes=QPlainTextEdit(study);study.notes.hide()
    study.save=QPushButton('Save phrase',study);study.save.hide();study.save.clicked.connect(study._save)
    study.feedback=QLabel('Recheck only when needed. Suggestions stay separate until you apply them.')
    study.feedback.setObjectName('hint');study.feedback.setWordWrap(True);layout.addWidget(study.feedback)
    layout.addStretch()

    def refresh():
        study.source_display.setText(study.text.toPlainText())
        candidate=study._proposal or study.subtitle
        study.translation_display.setText(candidate.target_text or 'Translation unavailable')
        study.pronunciation.setText(candidate.native_phonetics)
        study.target_pronunciation.setText(candidate.phonetics)
        study.route_label.setText(study.source.currentText()+'  \u2192  '+study.target.currentText())
        first_source=study.subtitle.original_native_text if study.subtitle.original_native_text is not None else study.subtitle.native_text
        first_target=study.subtitle.original_target_text if study.subtitle.original_target_text is not None else study.subtitle.target_text
        parts=[]
        for heading,before,after in (('Transcript',first_source,candidate.native_text),('Translation',first_target,candidate.target_text)):
            left,right=highlighted(before,after)
            parts.append('<h3>'+heading+'</h3><p>Original</p><p>'+left+'</p><p>Current / suggested</p><p>'+right+'</p>')
        study.comparison.setHtml(''.join(parts))
    study.text.textChanged.connect(refresh);study.result.textChanged.connect(refresh);study.original.textChanged.connect(refresh)
    study.source.currentIndexChanged.connect(refresh);study.target.currentIndexChanged.connect(refresh)
    study._show_result();study._show_revision();refresh()
    study.events.review_finished.connect(study._finished)
    study.analysis_widget=None
    if analysis is not None:
        from ui.analysis import SentenceAnalysis
        study.analysis_widget=SentenceAnalysis(study,analysis,history)
        study.analysis_widget.applied.connect(study._apply_analysis)
        analysis_scroll=QScrollArea();analysis_scroll.setWidgetResizable(True)
        analysis_scroll.setFrameShape(QFrame.Shape.NoFrame);analysis_scroll.setWidget(study.analysis_widget)
        tabs.addTab(analysis_scroll,'Meaning & context')
