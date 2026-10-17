"""On-demand sentence study and a text-only saved phrasebook."""
from PySide6.QtCore import Qt,Slot
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QPlainTextEdit,QComboBox,QFormLayout,QDialogButtonBox,QListWidget,QMessageBox,QTabWidget,QWidget,QScrollArea)
from core.config import LANGUAGE_LABELS
from ui.theme import style_for
from core.revisions import revision_label


class StudyDialog(QDialog):
    def __init__(self,update,config,events,store,phrasebook,parent=None,analysis=None,history=None):
        super().__init__(parent)
        self.subtitle=update
        self.config,self.events,self.store,self.phrasebook=config,events,store,phrasebook
        self._busy=False
        self._proposal=None
        from ui.sentence_view import build_details
        build_details(self,update,store,analysis,history)

    def _apply_analysis(self,update):
        self._proposal=None
        self.apply_recheck.hide()
        self.subtitle=update
        self._show_result()
        self.events.subtitle_corrected.emit(update)

    def _show_result(self):
        self.result.setPlainText('\n'.join(x for x in (self.subtitle.phonetics,self.subtitle.target_text,self.subtitle.native_phonetics) if x))
        if hasattr(self,'original'):
            self._show_revision()

    def _show_revision(self):
        label=revision_label(self.subtitle)
        self.revision.setText((label+' — revised, not verified correct.') if label else 'Original live version; no text changes applied.')
        self.compare_toggle.setVisible(bool(self.subtitle.revision_count))
        self.original.setPlainText('First transcript\n'+(self.subtitle.original_native_text or '')+
            '\n\nFirst translation\n'+(self.subtitle.original_target_text or ''))

    def _recheck(self):
        self._translate(recheck=True)

    def _apply_recheck(self):
        proposal=self._proposal
        if proposal is None:
            return
        if (self.text.toPlainText().strip()!=proposal.native_text or
            self.source.currentData()!=proposal.source_language or
            self.target.currentData()!=proposal.target_language):
            self.feedback.setText('Transcript or language changed. Recheck again before applying.')
            self.apply_recheck.setEnabled(False)
            return
        self.subtitle=proposal
        self._proposal=None
        self.apply_recheck.hide()
        self._show_result()
        self.events.subtitle_corrected.emit(proposal)
        self.feedback.setText('Revision applied to session history. Original wording is retained below; revised does not mean verified correct.')

    def _translate(self, checked=False, recheck=False):
        if self._busy:
            return
        text=self.text.toPlainText().strip()
        if not text or len(text)>4000 or self.source.currentData() is None:
            self.feedback.setText('Choose the spoken language and enter 1-4,000 characters.')
            return
        self._busy=True
        self._proposal=None
        self.apply_recheck.hide()
        self.translate.setEnabled(False)
        self.recheck.setEnabled(False)
        self.text.setReadOnly(True)
        self.source.setEnabled(False)
        self.target.setEnabled(False)
        if self.analysis_widget:
            self.analysis_widget.cancel_request()
            self.analysis_widget.apply.setEnabled(False)
            self.analysis_widget.run.setEnabled(False)
            self.analysis_widget.save_example.setEnabled(False)
        self.save.setEnabled(False)
        self.feedback.setText('Rechecking once. Live recognition pauses until this finishes. Expired audio uses text-only retranslation.' if recheck else 'Retranslating once. Live inference pauses until this finishes.')
        self.events.review_requested.emit({'update':self.subtitle,'text':text,
            'source':self.source.currentData(),'target':self.target.currentData(),'recheck':recheck})

    @Slot(object)
    def _finished(self,result):
        if result.get('id')!=self.subtitle.uid:
            return
        self._busy=False
        self.translate.setEnabled(True)
        self.recheck.setEnabled(True)
        self.text.setReadOnly(not self.edit.isChecked())
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        if self.analysis_widget:
            self.analysis_widget.run.setEnabled(True)
        self.save.setEnabled(True)
        if 'error' in result:
            self.feedback.setText('Retranslation failed: '+result['error'])
        else:
            if result.get('requires_confirmation'):
                proposal=result['update']
                self._proposal=proposal
                self.text.setPlainText(proposal.native_text)
                self.result.setPlainText('\n'.join(x for x in (proposal.phonetics,proposal.target_text,proposal.native_phonetics) if x))
                self.compare_toggle.show()
                self.original.setPlainText('Current transcript\n'+self.subtitle.native_text+'\n\nCurrent translation\n'+self.subtitle.target_text)
                self.revision.setText('Suggested revision — review against the current version below.')
                changed=(proposal.native_text,proposal.target_text)!=(self.subtitle.native_text,self.subtitle.target_text)
                self.apply_recheck.setVisible(changed)
                self.apply_recheck.setEnabled(changed)
                if not changed:
                    self.revision.setText('Recheck found no text changes.')
                mode='Audio recheck' if result.get('mode')=='audio' else 'Text-only retranslation; audio was not available'
                self.feedback.setText(mode+f" ({result.get('duration_ms',0)/1000:.1f}s). "+('Apply only after reviewing the suggestion.' if changed else 'No text changes.'))
                return
            self.subtitle=result['update']
            self.text.setPlainText(self.subtitle.native_text)
            self._show_result()
            mode='Audio recheck' if result.get('mode')=='audio' else 'Text-only retranslation (audio was not rechecked)'
            duration=result.get('duration_ms',0)/1000
            changed=bool(revision_label(self.subtitle))
            self.feedback.setText(f'{mode} finished in {duration:.1f}s. '+('Revision retained in session history; review before trusting it.' if changed else 'No text changes.'))

    def _save(self):
        if (self.text.toPlainText().strip()!=self.subtitle.native_text or self.target.currentData()!=self.subtitle.target_language or (self.source.currentData() is not None and self.source.currentData()!=self.subtitle.source_language)):
            self.feedback.setText('Translate the corrected transcript before saving it with a translation.')
            return
        try:
            self.phrasebook.save(self.subtitle,self.notes.toPlainText())
            self.feedback.setText('Saved as text only. Open Saved phrases from the main window.')
        except (ValueError,OSError) as exc:
            self.feedback.setText(str(exc))

    def done(self,result):
        if self.analysis_widget:
            self.analysis_widget.dispose()
        self.events.replay_requested.emit("",1.)
        try:
            self.events.review_finished.disconnect(self._finished)
        except (TypeError,RuntimeError):
            pass
        super().done(result)


class PhrasebookDialog(QDialog):
    def __init__(self,config,phrasebook,parent=None):
        super().__init__(parent)
        self.phrasebook=phrasebook
        self.setWindowTitle('Saved phrases')
        self.setStyleSheet(style_for(config.theme))
        self.resize(680,560)
        layout=QVBoxLayout(self)
        title=QLabel('Your phrasebook')
        title.setObjectName('title')
        layout.addWidget(title)
        self.summary=QLabel()
        layout.addWidget(self.summary)
        self.list=QListWidget()
        self.list.currentRowChanged.connect(self._select)
        layout.addWidget(self.list,1)
        self.detail=QPlainTextEdit()
        self.detail.setReadOnly(True)
        layout.addWidget(self.detail,1)
        row=QHBoxLayout()
        delete=QPushButton('Delete selected')
        delete.clicked.connect(self._delete)
        row.addWidget(delete)
        row.addStretch()
        close=QPushButton('Close')
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self._reload()

    def _reload(self):
        self.items=self.phrasebook.items()
        self.list.clear()
        for item in self.items:
            self.list.addItem(item.get('target_text') or item.get('native_text',''))
        self.summary.setText(f'{len(self.items)} / 1,000 phrases. Text only, with a 2 MB total limit.')
        if self.items:
            self.list.setCurrentRow(0)
        else:
            self.detail.setPlainText('No saved phrases yet. Open Study on a subtitle to save one.')

    def _select(self,index):
        if 0<=index<len(self.items):
            item=self.items[index]
            self.detail.setPlainText('\n'.join(item.get(k,'') for k in ('phonetics','target_text','native_phonetics','native_text','notes')))

    def _delete(self):
        index=self.list.currentRow()
        if 0<=index<len(self.items):
            try:
                self.phrasebook.delete(self.items[index]['id'])
                self._reload()
            except OSError as exc:
                QMessageBox.warning(self,'Could not delete',str(exc))
