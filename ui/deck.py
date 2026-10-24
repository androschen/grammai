"""Compact text-only vocabulary and sentence deck; no model calls."""
from html import escape
import logging
LOGGER=logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtGui import QTextDocument,QAbstractTextDocumentLayout,QPalette
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QListWidget,QListWidgetItem,QTabWidget,QStyledItemDelegate,QStyle,QStyleOptionViewItem,
    QFrame,QScrollArea,QSizePolicy,QSplitter)
from core.phrasebook import DeckReadError
from core.preferences import data_dir
from core.learning_cards import vocabulary_card,practice_prompt,answer_text,card_search_text
from ui.copyable_text import CopyableLabel
from ui.theme import style_for

LANGUAGES=[('All languages',''),('Chinese','zh'),('Thai','th'),('English','en'),('Indonesian','id')]
BADGES={'zh':'CN','th':'TH','en':'EN','id':'ID'}


def language_combo():
    combo=QComboBox()
    for label,code in LANGUAGES:combo.addItem(label,code)
    return combo


class CardRowDelegate(QStyledItemDelegate):
    """Paint visible rows, rather than allocating hundreds of nested widgets."""
    def document(self,index,width,palette):
        item=index.data(Qt.ItemDataRole.UserRole) or {}
        badge=BADGES.get(item.get('source_language'),'?')
        due=' · Due' if item.get('_due') else ''
        if item.get('reviewed_by_user') is not True:due=' · Needs review'
        first=escape(item.get('native_text','')[:100]);pronunciation=escape(item.get('native_phonetics','')[:100])
        lines=[f'<b>{badge} · {first}</b>{due}']
        if pronunciation:lines.append(pronunciation)
        lines.append(escape(item.get('target_text','')[:150]))
        doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(self.parent().font())
        doc.setDefaultStyleSheet('body { color: '+palette.color(QPalette.ColorRole.Text).name()+'; }')
        doc.setHtml('<body>'+'<br>'.join(lines)+'</body>');doc.setTextWidth(max(80,width-24))
        return doc

    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index);opt.text=''
        style=opt.widget.style() if opt.widget else self.parent().style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,opt.widget)
        doc=self.document(index,opt.rect.width(),opt.palette)
        painter.save();painter.setClipRect(opt.rect);painter.translate(opt.rect.left()+10,opt.rect.top()+10)
        context=QAbstractTextDocumentLayout.PaintContext();context.palette=opt.palette
        doc.documentLayout().draw(painter,context);painter.restore()

    def sizeHint(self,option,index):
        width=self.parent().viewport().width()
        doc=self.document(index,width,option.palette)
        return QSize(max(100,width),int(doc.size().height())+22)


class LearningDeckContent:
    def __init__(self,config,phrasebook,parent=None,events=None,service=None,embedded=False):
        super().__init__(parent)
        self.config,self.events,self.service=config,events,service
        self.embedded=embedded;self.disposed=False;self._compact=None;self._detail_open=False
        self._loaded_card_id=None;self._loaded_item={};self._drafts={};self._loaded_stamp=None
        self.book=phrasebook;self.items=[];self.loading=False;self.queue=[];self.index=0;self.revealed=False;self.started=False;self.session_results=[]
        self.setWindowTitle('Learning deck')
        if not embedded:self.setStyleSheet(style_for(config.theme));self.resize(700,650)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0) if embedded else outer.setContentsMargins(16,14,16,14);outer.setSpacing(8)
        header=QHBoxLayout();title=QLabel('Learning deck');title.setObjectName('field');header.addWidget(title);header.addStretch()
        self.summary=QLabel();self.summary.setObjectName('hint');header.addWidget(self.summary)
        from ui.icons import icon_button
        close=icon_button('close','Close learning deck',self);close.clicked.connect(lambda:self.accept() if not embedded else None);header.addWidget(close)
        if not embedded:outer.addLayout(header)
        else:close.hide();title.hide()
        self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        if embedded:self.tabs.setCornerWidget(self.summary)
        self.cards_page=QWidget();cards_layout=QVBoxLayout(self.cards_page);cards_layout.setContentsMargins(0,4,0,0)
        self.browser=QWidget();browse=QVBoxLayout(self.browser);browse.setContentsMargins(0,0,0,0)
        self.cards_split=QSplitter(Qt.Orientation.Horizontal);self.cards_split.setChildrenCollapsible(False);self.cards_split.addWidget(self.browser)
        cards_layout.addWidget(self.cards_split);self.tabs.addTab(self.cards_page,'Cards')
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search expressions, meanings or notes');self.search.setClearButtonEnabled(True)
        self.language=language_combo();self.language.setMinimumContentsLength(7);self.language.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        filters.addWidget(self.search,1);filters.addWidget(self.language);browse.addLayout(filters)
        actions=QHBoxLayout();self.start=QPushButton('Practice');self.start.clicked.connect(self.practice_selected_language);actions.addWidget(self.start);actions.addStretch()
        self.open_card=icon_button('edit','Open selected learning card',self);actions.addWidget(self.open_card);browse.addLayout(actions)
        self.list=QListWidget();self.list.setObjectName('learningCards');self.list.setWordWrap(True)
        self.list.setItemDelegate(CardRowDelegate(self.list));self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust);browse.addWidget(self.list,1)
        self.empty=QLabel('No matching cards. Select an expression in a conversation to create one.');self.empty.setWordWrap(True);self.empty.setObjectName('hint');browse.addWidget(self.empty)
        self.retry=QPushButton('Retry reading cards');self.retry.clicked.connect(self.reload);self.retry.hide();browse.addWidget(self.retry)
        self.feedback=QLabel();self.feedback.setWordWrap(True);self.feedback.setObjectName('hint');browse.addWidget(self.feedback)
        from ui.deck_card import DeckCardDialog,DeckCardView
        self.editor=(DeckCardView if embedded else DeckCardDialog)(self,config,events,service)
        if embedded:
            self.cards_split.addWidget(self.editor);self.cards_split.setStretchFactor(0,1);self.cards_split.setStretchFactor(1,2)
            self.editor.back_requested.connect(self.back_to_cards)
            self.open_card.hide()
        for name in ('original','meaning','notes','route','checked','save','delete'):
            setattr(self,name,getattr(self.editor,name))
        self.original.textChanged.connect(self.changed);self.meaning.textChanged.connect(self.changed)
        self.notes.textChanged.connect(self._save_enabled);self.checked.toggled.connect(self._save_enabled)
        self.editor.edit_mode_changed.connect(self._save_enabled)
        self.save.clicked.connect(self.save_card);self.delete.clicked.connect(self.delete_card)
        self.open_card.clicked.connect(self.edit_selected);self.list.itemClicked.connect(lambda item:self.edit_selected())
        self.list.itemActivated.connect(lambda item:self.edit_selected());self.list.currentRowChanged.connect(self.select)
        self.search.textChanged.connect(self.reload);self.language.currentIndexChanged.connect(self.reload)
        practice=QWidget();review=QVBoxLayout(practice);review.setSpacing(10);self.tabs.addTab(practice,'Practice')
        controls=QHBoxLayout();self.practice_language=language_combo();self.mode=QComboBox()
        self.mode.addItem('Understand meaning','understand');self.mode.addItem('Recall expression','recall');self.mode.setAccessibleName('Practice mode')
        self.mode.setToolTip('Recall hides the expression in its example. Sentence cards use meaning → original.')
        self.practice_start=QPushButton('Practice due cards');self.practice_start.clicked.connect(self.start_review)
        controls.addWidget(self.practice_language,1);controls.addWidget(self.mode,1);controls.addWidget(self.practice_start);review.addLayout(controls)
        self.practice_instruction=QLabel();self.practice_instruction.setWordWrap(True);review.addWidget(self.practice_instruction)
        self.progress=QLabel();self.progress.setWordWrap(True);self.progress.setObjectName('hint');review.addWidget(self.progress)
        reading_scroll=QScrollArea();reading_scroll.setWidgetResizable(True);reading_scroll.setFrameShape(QFrame.Shape.NoFrame)
        reading_body=QWidget();reading_body_layout=QVBoxLayout(reading_body);reading_body_layout.setContentsMargins(0,0,0,0)
        self.practice_frame=QFrame();self.practice_frame.setObjectName('sentenceReadingSection')
        self.practice_frame.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        reading=QVBoxLayout(self.practice_frame);reading.setContentsMargins(18,16,18,16);reading.setSpacing(10)
        reading_body_layout.addWidget(self.practice_frame);reading_body_layout.addStretch()
        reading_scroll.setWidget(reading_body);review.addWidget(reading_scroll,1)
        self.focus_expression=CopyableLabel();self.focus_expression.setWordWrap(True);reading.addWidget(self.focus_expression)
        self.front=CopyableLabel();self.front.setStyleSheet('font-size:21px;');self.front.setWordWrap(True);reading.addWidget(self.front)
        self.hint=CopyableLabel();self.hint.setWordWrap(True);reading.addWidget(self.hint)
        self.reveal=QPushButton('Reveal answer');self.reveal.clicked.connect(self.reveal_answer);reading.addWidget(self.reveal)
        self.answer=QWidget();answer=QVBoxLayout(self.answer);answer.setContentsMargins(0,12,0,6)
        self.pronunciation=CopyableLabel();self.back=CopyableLabel();self.practice_usage=CopyableLabel();self.practice_notes=CopyableLabel();self.practice_context=CopyableLabel()
        for label in (self.pronunciation,self.back,self.practice_usage,self.practice_notes,self.practice_context):label.setWordWrap(True);answer.addWidget(label)
        from ui.card_explanation import CardExplanationWidget
        self.practice_explanation=CardExplanationWidget(config,events,service,self)
        answer.addWidget(self.practice_explanation)
        reading.addWidget(self.answer);self.answer.hide()
        grade=QHBoxLayout();self.again=QPushButton('Again · 10 min');self.remembered=QPushButton('Remembered')
        self.again.clicked.connect(lambda:self.grade(False));self.remembered.clicked.connect(lambda:self.grade(True))
        grade.addWidget(self.again);grade.addWidget(self.remembered);review.addLayout(grade)
        self.skip=QPushButton('Skip');self.skip.setToolTip('Leave this card due; do not change its schedule.')
        self.skip.clicked.connect(self.skip_card);grade.addWidget(self.skip)
        self.mode.currentIndexChanged.connect(self.show_card);self.practice_language.currentIndexChanged.connect(self._reset_practice)
        self.tabs.currentChanged.connect(lambda index:self.refresh_if_changed() if index==0 else None)
        self.reload();self.show_card()

    def _save_enabled(self,*args):
        index=self.list.currentRow()
        item=self.items[index] if 0<=index<len(self.items) else None
        changed=bool(item and self.notes.toPlainText().strip()!=item.get('notes',''))
        allowed=self.checked.isChecked() if self.editor.editing else changed
        self.save.setEnabled(bool(allowed and item and not self.loading))

    def reload(self,*args):
        self._stash_draft()
        selected=self.items[self.list.currentRow()]['id'] if 0<=self.list.currentRow()<len(self.items) else None
        query=self.search.text().strip().casefold();language=self.language.currentData()
        try:
            all_items=self.book.items(force=True);due=self.book.due();stats=self.book.stats()
        except (DeckReadError,OSError) as exc:
            self.loading=True;self.list.clear();self.items=[];self.loading=False;self.select(-1)
            self.summary.setText('Deck unavailable');self.empty.setText(str(exc));self.empty.show();self.retry.show()
            self.feedback.setText('Your saved file has not been changed.');self.start.setEnabled(False);self.practice_start.setEnabled(False)
            return
        self._loaded_stamp=self._disk_stamp()
        self.retry.hide();self.practice_start.setEnabled(True);self.feedback.clear()
        self.summary.setToolTip('Saved file: '+str(data_dir()/'phrases.json'))
        self.empty.setText(('No matching cards. Clear the search or change the language.' if all_items else 'No saved cards at: '+str(data_dir()/'phrases.json')))
        LOGGER.info('Deck opened: %s; saved=%s',data_dir()/'phrases.json',len(all_items))
        self.items=[x for x in all_items if (not language or x.get('source_language')==language) and (not query or query in card_search_text(x).casefold())]
        due_ids={x['id'] for x in due}
        self.loading=True;self.list.clear()
        for item in self.items:
            row=QListWidgetItem(item.get('native_text',''))
            row.setData(Qt.ItemDataRole.UserRole,dict(item,_due=item['id'] in due_ids));row.setToolTip('Open card · inspect context, edit meaning and notes')
            self.list.addItem(row)
        self.loading=False
        self.summary.setText(f'{len(all_items)} saved · {len(due)} due')
        self.summary.setToolTip(f"Saved file: {data_dir()/'phrases.json'}\nText only · {stats['bytes']/1024:.1f} KB / 2 MB · 1,000-card limit")
        filtered_due=sum(not language or x.get('source_language')==language for x in due)
        self.start.setText(f'Practice {min(10,filtered_due)} due cards');self.start.setEnabled(filtered_due>0)
        self.empty.setVisible(not self.items)
        index=next((i for i,x in enumerate(self.items) if x['id']==selected),0 if self.items else -1)
        self.list.setCurrentRow(index)
        if index<0:self.select(-1)

    def select(self,index):
        if self.loading:return
        self._stash_draft();self.loading=True
        item=self.items[index] if 0<=index<len(self.items) else {}
        self.original.setPlainText(item.get('native_text',''));self.meaning.setPlainText(item.get('target_text',''));self.notes.setPlainText(item.get('notes',''))
        self.checked.setChecked(False);self.save.setEnabled(False);self.delete.setEnabled(bool(item));self.open_card.setEnabled(bool(item))
        self.route.setText((BADGES.get(item.get('source_language'),'?')+' → '+BADGES.get(item.get('target_language'),'?')+('' if item.get('reviewed_by_user') is True else ' · Needs review')) if item else 'No selected card')
        self.editor.pronunciation.setText(item.get('native_phonetics',''));self.editor.pronunciation.setVisible(bool(item.get('native_phonetics')))
        self.editor.show_context(item)
        self._explanation_data(self.editor.explanation,item)
        self._loaded_card_id=item.get('id');self._loaded_item=dict(item)
        self.editor.feedback.setText('Saved' if item else '')
        draft=self._drafts.get(self._loaded_card_id)
        if draft:
            self.original.setPlainText(draft['original']);self.meaning.setPlainText(draft['meaning']);self.notes.setPlainText(draft['notes'])
            self.editor.edit.setChecked(draft['editing'])
            same_text=draft['baseline']==(item.get('native_text',''),item.get('target_text',''))
            self.checked.setChecked(draft['checked'] and same_text)
            self.editor.feedback.setText('Unsaved changes' if same_text else 'Card changed. Check your draft before saving.')
        self.loading=False;self._save_enabled()
        if self.embedded:self._adapt_layout()

    def _explanation_data(self,widget,item):
        from ml.card_explanation import card_payload
        payload=card_payload(item) if item else None
        identifier=item.get('id')
        def persist(value):
            updated=self.book.save_explanation(identifier,value,self.config.analysis_explanation_language)
            for card in self.items+self.queue:
                if card.get('id')==identifier:card.update(updated)
            if widget is self.editor.explanation and self.editor.example_meaning:
                self.editor.example_meaning.setText(value['sentence_meaning'])
        widget.set_data(item.get('learning_explanation'),payload,persist)

    def edit_selected(self):
        if self.list.currentRow()<0:return
        if self.embedded:
            self._detail_open=True;self._adapt_layout()
        else:
            self.editor.show();self.editor.raise_();self.editor.activateWindow()

    def changed(self):
        if not self.loading:self.checked.setChecked(False);self.save.setEnabled(False)

    def save_card(self):
        index=self.list.currentRow()
        if not (0<=index<len(self.items)):return
        if self.editor.editing and not self.checked.isChecked():return
        try:
            if self.editor.editing:
                self.book.update_card(self.items[index]['id'],self.original.toPlainText(),self.meaning.toPlainText(),self.notes.toPlainText(),True)
            else:
                self.book.update_notes(self.items[index]['id'],self.notes.toPlainText())
            identifier=self.items[index]['id']
            text_changed=(self.original.toPlainText().strip(),self.meaning.toPlainText().strip())!=(self.items[index].get('native_text'),self.items[index].get('target_text')) and self.editor.editing
            if text_changed:self._reset_practice()
            else:
                for card in self.queue:
                    if card.get('id')==identifier:card['notes']=self.notes.toPlainText().strip()
                if self.revealed:self.reveal_answer()
            self._drafts.pop(identifier,None);self._loaded_card_id=None
            self.reload();self.editor.feedback.setText('Saved')
        except (ValueError,OSError) as exc:self.editor.feedback.setText(str(exc))

    def delete_card(self):
        index=self.list.currentRow()
        if 0<=index<len(self.items):
            try:
                identifier=self.items[index]['id'];self.book.delete(identifier);self._drafts.pop(identifier,None);self._loaded_card_id=None
                if not self.embedded:self.editor.hide()
                self._reset_practice();self.reload()
            except OSError as exc:self.editor.feedback.setText(str(exc))

    def practice_selected_language(self):
        self.practice_language.setCurrentIndex(max(0,self.practice_language.findData(self.language.currentData())))
        self.start_review();self.tabs.setCurrentIndex(1)

    def _reset_practice(self,*args):
        self.queue=[];self.index=0;self.started=False;self.session_results=[];self.show_card()

    def start_review(self):
        try:cards=self.book.due(self.practice_language.currentData())[:10]
        except DeckReadError as exc:self.progress.setText(str(exc));return
        self.started=True;self.queue=cards;self.index=0;self.session_results=[];self.show_card()

    def show_card(self,*args):
        self.practice_explanation.set_data(None,None)
        self.revealed=False;self.answer.hide();self.again.setEnabled(False);self.remembered.setEnabled(False)
        self.again.hide();self.remembered.hide()
        active=self.index<len(self.queue);self.practice_frame.setVisible(active);self.reveal.setEnabled(active);self.reveal.setVisible(active)
        item=self.queue[self.index] if active else {}
        recall=self.mode.currentData()=='recall'
        self.practice_instruction.setText('Recall the missing expression before revealing. Pronunciation appears with the answer.' if recall else 'Recall the expression’s meaning in this sentence before revealing.')
        self.focus_expression.setText('Expression: '+item.get('native_text',''))
        self.focus_expression.setVisible(active and vocabulary_card(item) and not recall)
        self.practice_start.setVisible(not active)
        self.skip.setVisible(active)
        prompt,hint=practice_prompt(item,self.mode.currentData());self.front.setText(prompt);self.hint.setText(hint);self.hint.setVisible(bool(hint))
        message='Choose a language, then start practice.' if not self.started else ('Session complete.' if self.queue else 'No due cards. Save and review a card first.')
        if self.started and self.queue and not active:
            remembered=self.session_results.count('remembered')
            again=self.session_results.count('again')
            skipped=self.session_results.count('skipped')
            message=f'Session complete · {remembered} remembered · {again} to revisit · {skipped} skipped'
            self.practice_instruction.setText('Your review schedule is saved. Skipped cards stay due.')
        badge=BADGES.get(item.get('source_language'),'?')
        self.progress.setText(f'{self.index+1} / {len(self.queue)} · {badge}' if active else message)
        interval=min(365,max(1,int(item.get('interval_days',0))*2))
        self.remembered.setText(f'Remembered · {interval} '+('day' if interval==1 else 'days'))

    def reveal_answer(self):
        if self.index>=len(self.queue):return
        item=self.queue[self.index];self.revealed=True
        self._explanation_data(self.practice_explanation,item)
        values=((self.pronunciation,item.get('native_phonetics','')),
            (self.back,answer_text(item,self.mode.currentData())),
            (self.practice_usage,' · '.join(x for x in (item.get('usage',''),item.get('usage_note',''),item.get('uncertainty','')) if x)),
            (self.practice_notes,'Your notes · '+item['notes'] if item.get('notes') else ''),
            (self.practice_context,'Earlier dialogue · '+' / '.join(x.get('text','') for x in item.get('conversation_context',[]) if isinstance(x,dict)) if item.get('conversation_context') else ''))
        for label,text in values:label.setText(text);label.setVisible(bool(text))
        self.answer.show();self.reveal.hide();self.again.show();self.remembered.show();self.again.setEnabled(True);self.remembered.setEnabled(True)

    def grade(self,remembered):
        if not self.revealed or self.index>=len(self.queue):return
        try:self.book.grade(self.queue[self.index]['id'],remembered)
        except (ValueError,OSError) as exc:self.progress.setText(str(exc));return
        self.session_results.append('remembered' if remembered else 'again')
        self.index+=1;self.show_card()

    def skip_card(self):
        if self.index>=len(self.queue):return
        self.session_results.append('skipped');self.index+=1;self.show_card()

    def _stash_draft(self):
        if self.loading or not self._loaded_card_id:return
        changed=(self.original.toPlainText(),self.meaning.toPlainText(),self.notes.toPlainText())!=(self._loaded_item.get('native_text',''),self._loaded_item.get('target_text',''),self._loaded_item.get('notes',''))
        if changed:
            self._drafts[self._loaded_card_id]=dict(original=self.original.toPlainText(),meaning=self.meaning.toPlainText(),notes=self.notes.toPlainText(),editing=self.editor.editing,checked=self.checked.isChecked(),baseline=(self._loaded_item.get('native_text',''),self._loaded_item.get('target_text','')))
        else:self._drafts.pop(self._loaded_card_id,None)

    def _disk_stamp(self):
        try:
            stat=(data_dir()/'phrases.json').stat();return (stat.st_mtime_ns,stat.st_size)
        except FileNotFoundError:return None
        except OSError:return object()

    def refresh_if_changed(self):
        if self._disk_stamp()!=self._loaded_stamp:self.reload()

    def activate(self):
        self.refresh_if_changed()
        if self.embedded:self._adapt_layout()

    def back_to_cards(self):
        self._detail_open=False;self._adapt_layout()

    def _adapt_layout(self):
        if not self.embedded:return
        compact=self.width()<780;has_item=bool(self._loaded_card_id)
        self.editor.back.setVisible(compact)
        self.browser.setVisible(not compact or not (self._detail_open and has_item))
        self.editor.setVisible(has_item and (not compact or self._detail_open))
        if self._compact!=compact and not compact:self.cards_split.setSizes([300,max(400,self.width()-320)])
        self._compact=compact

    def dispose(self):
        if self.disposed:return
        self.disposed=True;self.editor.deactivate();self.editor.explanation.dispose();self.practice_explanation.dispose()


class LearningDeckPage(LearningDeckContent,QWidget):
    def __init__(self,config,phrasebook,parent=None,events=None,service=None):
        super().__init__(config,phrasebook,parent,events,service,embedded=True)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'editor'):self._adapt_layout()


class LearningDeckDialog(LearningDeckContent,QDialog):
    """Compatibility host for standalone diagnostics; production uses LearningDeckPage."""
    def done(self,result):
        self.editor.reject();self.dispose();super().done(result)
