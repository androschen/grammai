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
        events.subtitle_corrected.connect(self._external_update)
        events.review_state_changed.connect(self._external_update)

    def _external_update(self,update):
        if update.uid==self.subtitle.uid and not self._busy and self._proposal is None and self.text.toPlainText()==self.subtitle.native_text:
            metadata_only=(update.native_text,update.target_text,update.revision_count)==(self.subtitle.native_text,self.subtitle.target_text,self.subtitle.revision_count)
            self.subtitle=update
            if metadata_only:
                self._refresh_review_status();return
            self.text.setPlainText(update.native_text)
            self._show_result()

    def _apply_analysis(self,update):
        self._proposal=None
        self.apply_recheck.hide()
        self.subtitle=update
        self.text.setPlainText(update.native_text)
        self._show_result()
        self.events.subtitle_corrected.emit(update)

    def _show_result(self):
        self.result.setPlainText('\n'.join(x for x in (self.subtitle.phonetics,self.subtitle.target_text,self.subtitle.native_phonetics) if x))
        if hasattr(self,'original'):
            self._show_revision()

    def _show_revision(self):
        label=revision_label(self.subtitle)
        self.revision.setText((label+' — revised, not verified correct.') if label else 'Original live version; no text changes applied.')

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
        self.save.setEnabled(self.reviewed.isChecked() and self._proposal is None)
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
                    self._proposal=None;self._show_result()
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
        def report(text):
            self.feedback.setText(text);self.learning_feedback.setText(text)
        if self._busy or self._proposal is not None or getattr(self,'_save_stale',False):
            report('Review the current sentence and confirm it before saving.');return
        if not self.subtitle.native_text.strip() or not self.subtitle.target_text.strip() or self.subtitle.translation_status=='unavailable':
            report('A transcript and an available meaning are required before saving.');return
        if (self.text.toPlainText().strip()!=self.subtitle.native_text or self.target.currentData()!=self.subtitle.target_language or (self.source.currentData() is not None and self.source.currentData()!=self.subtitle.source_language)):
            report('Translate the corrected transcript before saving it with a translation.')
            return
        if not self.reviewed.isChecked():
            report('Confirm that you checked the original sentence and its meaning before saving.');return
        try:
            from dataclasses import replace
            from ml.phonetics import phonetics_auto
            meaning=self.save_meaning.toPlainText().strip()
            if not meaning or len(meaning)>4000:raise ValueError('Enter a meaning of 1–4,000 characters.')
            value=replace(self.subtitle,target_text=meaning,phonetics=phonetics_auto(meaning))
            self.phrasebook.save(value,self.notes.toPlainText(),reviewed=True)
            report('Saved as text only. Open Learning deck from the main window.')
        except (ValueError,OSError) as exc:
            report(str(exc))


    def done(self,result):
        try:
            self.events.subtitle_corrected.disconnect(self._external_update)
        except (TypeError,RuntimeError):
            pass
        try:self.events.review_state_changed.disconnect(self._external_update)
        except (TypeError,RuntimeError):pass
        try:self.events.playback_active.disconnect(self._playback_changed)
        except (TypeError,RuntimeError):pass
        self.save_popup.reject()
        if self.analysis_widget:
            self.analysis_widget.dispose()
        self.events.replay_requested.emit("",1.)
        try:
            self.events.review_finished.disconnect(self._finished)
        except (TypeError,RuntimeError):
            pass
        super().done(result)


from ui.deck import LearningDeckDialog as PhrasebookDialog
