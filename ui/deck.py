"""Small text-only deck browser and ten-card practice; no model calls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QListWidget,QPlainTextEdit,QCheckBox,QTabWidget,QScrollArea)
from ui.copyable_text import CopyableLabel
from ui.theme import style_for

LANGUAGES=[('All languages',''),('Chinese','zh'),('Thai','th'),('English','en'),('Indonesian','id')]


def language_combo():
    combo=QComboBox()
    for label,code in LANGUAGES:combo.addItem(label,code)
    return combo


class LearningDeckDialog(QDialog):
    def __init__(self,config,phrasebook,parent=None):
        super().__init__(parent)
        self.book=phrasebook;self.items=[];self.loading=False;self.queue=[];self.index=0;self.revealed=False;self.started=False
        self.setWindowTitle('Learning deck');self.setStyleSheet(style_for(config.theme));self.resize(720,640)
        outer=QVBoxLayout(self);outer.setContentsMargins(14,14,14,14);outer.setSpacing(8)
        header=QHBoxLayout();title=QLabel('Saved phrases');title.setObjectName('field');header.addWidget(title);header.addStretch();outer.addLayout(header)
        self.summary=QLabel();self.summary.setWordWrap(True);outer.addWidget(self.summary)
        tabs=QTabWidget();outer.addWidget(tabs,1)
        body=QWidget();browse=QVBoxLayout(body)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);tabs.addTab(scroll,'Cards')
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Find a saved sentence or meaning');self.search.setClearButtonEnabled(True)
        self.language=language_combo();filters.addWidget(self.search,1);filters.addWidget(self.language);browse.addLayout(filters)
        self.list=QListWidget();self.list.setMaximumHeight(110);browse.addWidget(self.list)
        self.route=QLabel();self.route.setWordWrap(True);browse.addWidget(self.route)
        form=QFormLayout();self.original=QPlainTextEdit();self.meaning=QPlainTextEdit();self.notes=QPlainTextEdit()
        for label,edit in (('Original',self.original),('Meaning',self.meaning),('Notes',self.notes)):
            edit.setFixedHeight(65);form.addRow(label,edit);edit.textChanged.connect(self.changed)
        form.setVerticalSpacing(8)
        browse.addLayout(form)
        self.checked=QCheckBox('I checked this original sentence and its meaning');browse.addWidget(self.checked)
        row=QHBoxLayout();self.save=QPushButton('Save');self.delete=QPushButton();from ui.icons import compact_action;compact_action(self.delete,'trash','Delete selected card')
        self.save.clicked.connect(self.save_card);self.delete.clicked.connect(self.delete_card)
        row.addWidget(self.save);row.addWidget(self.delete);browse.addLayout(row)
        self.feedback=QLabel();self.feedback.setWordWrap(True);browse.addWidget(self.feedback);browse.addStretch()
        self.checked.toggled.connect(lambda checked:self.save.setEnabled(bool(checked and self.list.currentRow()>=0)))
        self.list.currentRowChanged.connect(self.select)
        self.search.textChanged.connect(self.reload);self.language.currentIndexChanged.connect(self.reload)
        practice=QWidget();review=QVBoxLayout(practice);tabs.addTab(practice,'Practice')
        tabs.currentChanged.connect(lambda index:self.reload() if index==0 else None)
        note=QLabel('Recall first, then reveal. Up to 10 reviewed cards per session.')
        note.setWordWrap(True);review.addWidget(note)
        controls=QHBoxLayout();self.practice_language=language_combo();start=QPushButton('Practice · 10 cards')
        start.clicked.connect(self.start_review);controls.addWidget(self.practice_language);controls.addWidget(start);review.addLayout(controls)
        self.progress=QLabel('Choose a language or practise all languages.');self.progress.setWordWrap(True);review.addWidget(self.progress)
        self.front=CopyableLabel();self.front.setObjectName('title');self.front.setWordWrap(True);review.addWidget(self.front)
        self.reveal=QPushButton('Reveal answer');self.reveal.clicked.connect(self.reveal_answer);review.addWidget(self.reveal)
        self.answer=QWidget();answer=QVBoxLayout(self.answer);self.pronunciation=CopyableLabel();self.back=CopyableLabel();self.practice_notes=CopyableLabel()
        for label in (self.pronunciation,self.back,self.practice_notes):label.setWordWrap(True);answer.addWidget(label)
        review.addWidget(self.answer);self.answer.hide();review.addStretch()
        grade=QHBoxLayout();self.again=QPushButton('Again · 10 min');self.remembered=QPushButton('Remembered')
        self.again.clicked.connect(lambda:self.grade(False));self.remembered.clicked.connect(lambda:self.grade(True))
        self.remembered.setToolTip('First recall: 1 day. Then double the interval, up to 365 days.')
        grade.addWidget(self.again);grade.addWidget(self.remembered);review.addLayout(grade)
        from ui.icons import icon_button
        close=icon_button('close','Close saved phrases',self);close.clicked.connect(self.accept);header.addWidget(close)
        self.reload();self.show_card()

    def reload(self,*args):
        selected=self.items[self.list.currentRow()]['id'] if 0<=self.list.currentRow()<len(self.items) else None
        query=self.search.text().strip().casefold();language=self.language.currentData()
        all_items=self.book.items()
        self.items=[x for x in all_items if (not language or x.get('source_language')==language) and
            (not query or query in ' '.join(str(x.get(k,'')) for k in ('native_text','target_text','notes')).casefold())]
        self.loading=True;self.list.clear()
        for item in self.items:
            tag='Reviewed' if item.get('reviewed_by_user') is True else 'Needs review'
            self.list.addItem(f"{tag} - {item.get('native_text','')[:100]}")
        self.loading=False
        stats=self.book.stats();reviewed=sum(x.get('reviewed_by_user') is True for x in all_items)
        self.summary.setText(f'{len(all_items)} cards · {reviewed} reviewed')
        self.summary.setToolTip(f"Limit: 1,000 cards · {stats['bytes']/1024:.1f} KB / 2 MB · Text only")
        index=next((i for i,x in enumerate(self.items) if x['id']==selected),0 if self.items else -1)
        self.list.setCurrentRow(index)
        if index<0:self.select(-1)

    def select(self,index):
        if self.loading:return
        self.loading=True
        item=self.items[index] if 0<=index<len(self.items) else {}
        self.original.setPlainText(item.get('native_text',''));self.meaning.setPlainText(item.get('target_text',''));self.notes.setPlainText(item.get('notes',''))
        self.checked.setChecked(False);self.save.setEnabled(False);self.delete.setEnabled(bool(item))
        self.route.setText((str(item.get('source_language','?')).upper()+' → '+str(item.get('target_language','?')).upper()+' · '+('Reviewed by you' if item.get('reviewed_by_user') is True else 'Needs your review')) if item else 'No cards match. Save a reviewed sentence from Details.')
        self.loading=False

    def changed(self):
        if not self.loading:self.checked.setChecked(False);self.save.setEnabled(False)

    def save_card(self):
        index=self.list.currentRow()
        if not (0<=index<len(self.items)) or not self.checked.isChecked():return
        try:
            self.book.update_card(self.items[index]['id'],self.original.toPlainText(),self.meaning.toPlainText(),self.notes.toPlainText(),True)
            self.feedback.setText('Saved as reviewed by you.');self.queue=[];self.index=0;self.started=False;self.show_card();self.reload()
        except (ValueError,OSError) as exc:self.feedback.setText(str(exc))

    def delete_card(self):
        index=self.list.currentRow()
        if 0<=index<len(self.items):
            try:
                self.book.delete(self.items[index]['id']);self.queue=[];self.index=0;self.started=False;self.show_card();self.reload()
            except OSError as exc:self.feedback.setText(str(exc))

    def start_review(self):
        self.started=True;self.queue=self.book.due(self.practice_language.currentData())[:10];self.index=0;self.show_card()

    def show_card(self):
        self.revealed=False;self.answer.hide();self.again.setEnabled(False);self.remembered.setEnabled(False)
        active=self.index<len(self.queue);self.reveal.setEnabled(active)
        self.front.setText(self.queue[self.index].get('native_text','') if active else '')
        message='Start a review when ready.' if not self.started else ('Session finished. Start another review for more due cards.' if self.queue else 'No due cards for this language. Add or review cards on the Cards tab.')
        self.progress.setText(f'Card {self.index+1} / {len(self.queue)}' if active else message)

    def reveal_answer(self):
        if self.index>=len(self.queue):return
        item=self.queue[self.index];self.revealed=True
        self.pronunciation.setText(item.get('native_phonetics',''));self.back.setText(item.get('target_text',''));self.practice_notes.setText(item.get('notes',''))
        self.answer.show();self.again.setEnabled(True);self.remembered.setEnabled(True)

    def grade(self,remembered):
        if not self.revealed or self.index>=len(self.queue):return
        try:self.book.grade(self.queue[self.index]['id'],remembered)
        except (ValueError,OSError) as exc:self.progress.setText(str(exc));return
        self.index+=1;self.show_card()
