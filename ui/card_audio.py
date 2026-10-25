"""Shared compact original-sentence audio controls for saves, reading and Practice."""
from PySide6.QtCore import Qt,Signal,QThreadPool
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QProgressBar
from ui.controls import ToggleSwitch
from ui.icons import icon_button,set_button_icon
from audio.library import AudioLibrary
from audio.tasks import AudioTask


class AudioTransport(QWidget):
    remove_requested=Signal()
    def __init__(self,events,parent=None,removable=False):
        super().__init__(parent);self.events=events;self.key='';self.playing=False;self._disposed=False;self._preview_audio=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,6,0,6);layout.setSpacing(4)
        self.caption=QLabel('Original sentence');self.caption.setObjectName('hint');layout.addWidget(self.caption)
        row=QHBoxLayout();row.setSpacing(6)
        self.play=icon_button('play','Play original sentence',self);self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.progress=QProgressBar();self.progress.setObjectName('cardAudioProgress');self.progress.setTextVisible(False);self.progress.setFixedHeight(5);self.progress.setRange(0,1000);self.progress.setValue(0);row.addWidget(self.progress,1)
        self.time=QLabel('0:00');self.time.setObjectName('hint');row.addWidget(self.time)
        self.speed=QComboBox();self.speed.addItem('1×',1.);self.speed.addItem('0.8×',.8);self.speed.setFixedWidth(90);self.speed.setAccessibleName('Replay speed');self.speed.currentIndexChanged.connect(self._speed_changed);row.addWidget(self.speed)
        self.remove=icon_button('trash','Remove recording; keep card text and notes',self);self.remove.setVisible(removable);self.remove.clicked.connect(self.remove_requested.emit);row.addWidget(self.remove)
        layout.addLayout(row)
        if events is not None:
            events.playback_started.connect(self._started);events.playback_active.connect(self._active);events.playback_position.connect(self._position)
        self.bind({})

    def bind(self,item,locked=False):
        self.stop();self._preview_audio=None;self.progress.setValue(0);metadata=item.get('audio') or {};name=metadata.get('file','')
        self.key='saved:'+name if name else '';self._duration=float(metadata.get('duration',0))
        exists=AudioLibrary().available(item);self.play.setEnabled(exists and not locked and self.events is not None);self.speed.setEnabled(exists and not locked);self.remove.setEnabled(bool(name))
        self.time.setText('0:00 / '+self._format(self._duration))
        self.caption.setText('Reveal to listen' if locked and name else ('Original sentence' if exists else ('Recording unavailable · card text is safe' if name else 'No saved recording')))
        self.setVisible(bool(name));self.setToolTip('' if locked else str(metadata.get('original_text','')))

    def bind_replay(self,store,key,audio):
        self.stop();self._preview_audio=audio
        self.key=key;self._duration=len(audio)/store.sample_rate if audio is not None else 0
        self.progress.setValue(0);self.time.setText('0:00 / '+self._format(self._duration))
        self.caption.hide();self.remove.hide();self.play.setEnabled(audio is not None and self.events is not None)
        self.setVisible(audio is not None)

    @staticmethod
    def _format(seconds):
        seconds=max(0,int(seconds));return f'{seconds//60}:{seconds%60:02d}'

    def toggle(self):
        if self.playing:self.stop()
        elif self.events is not None and self.key and self.play.isEnabled():
            if self._preview_audio is not None:self.events.replay_buffer_requested.emit(self.key,self._preview_audio,float(self.speed.currentData()))
            else:self.events.replay_requested.emit(self.key,float(self.speed.currentData()))

    def _started(self,key):
        self.playing=bool(key) and key==self.key
        set_button_icon(self.play,'stop' if self.playing else 'play');self.play.setToolTip('Stop replay' if self.playing else 'Play original sentence');self.play.setAccessibleName(self.play.toolTip())

    def _active(self,active):
        if not active:self._started('');self.progress.setValue(0)

    def _position(self,key,elapsed,duration):
        if key!=self.key:return
        self.progress.setValue(round(min(1,elapsed/max(1,duration))*1000));self.time.setText(self._format(elapsed/1000)+' / '+self._format(duration/1000))

    def _speed_changed(self,*args):
        if self.playing:self.stop()

    def stop(self):
        if self.playing and self.events is not None:self.events.replay_requested.emit('',1.)
        self.playing=False;set_button_icon(self.play,'play')

    def hideEvent(self,event):
        self.stop();super().hideEvent(event)

    def dispose(self):
        if self._disposed:return
        self._disposed=True;self.stop()
        if self.events is not None:
            for signal,slot in ((self.events.playback_started,self._started),(self.events.playback_active,self._active),(self.events.playback_position,self._position)):
                try:signal.disconnect(slot)
                except (TypeError,RuntimeError):pass


class SaveAudioWidget(QWidget):
    busy_changed=Signal(bool)
    def __init__(self,parent=None):
        super().__init__(parent);self.audio=None;self.busy=False;self._job=None;self._generation=0;self.preview=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,8);layout.setSpacing(4)
        self.include=ToggleSwitch('Include original audio');layout.addWidget(self.include)
        self.hint=QLabel('Original clip expired · text-only saving is available.');self.hint.setObjectName('hint');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.include.setEnabled(False)

    def bind(self,store,key,config,original_text='',language='',events=None):
        self._generation+=1;self.library=AudioLibrary(config.saved_audio_limit_mb)
        self.audio=store.get(key) if store is not None and key else None
        self.rate=getattr(store,'sample_rate',16000);self.original_text=original_text;self.language=language
        if self.preview is not None:
            self.preview.dispose();self.layout().removeWidget(self.preview);self.preview.deleteLater()
        self.preview=AudioTransport(events,self);self.preview.bind_replay(store,key,self.audio);self.layout().addWidget(self.preview)
        available=self.audio is not None
        self.include.setEnabled(available);self.include.setChecked(available)
        if available:
            duration=len(self.audio)/self.rate
            self.hint.setText(f'Original sentence · {duration:.1f}s · about {max(1,round(duration*3))} KB compressed. Saved locally with this card.')
        else:self.hint.setText('Original clip expired · you can still save this card without audio.')

    def commit(self,persist,finished):
        if self.busy:return
        if self.audio is None or not self.include.isChecked():
            try:persist(None);finished(None)
            except (ValueError,OSError) as exc:finished(str(exc))
            return
        self.busy=True;self.include.setEnabled(False);self.busy_changed.emit(True)
        audio=self.audio;rate=self.rate;library=self.library;generation=self._generation
        original_text=self.original_text;language=self.language
        self.hint.setText('Saving compressed audio…')
        self._persist=persist;self._finished=finished
        self._job=AudioTask(lambda:library.save(audio,rate))
        self._job.signals.ready.connect(self._saved)
        QThreadPool.globalInstance().start(self._job)
        self._pending_generation=generation;self._pending_source=(original_text,language)

    def _saved(self,result,error):
        self.busy=False;self.include.setEnabled(self.audio is not None)
        if self._pending_generation!=self._generation:
            self.busy_changed.emit(False);return
        if error is None:
            try:
                result=dict(result,original_text=self._pending_source[0],language=self._pending_source[1])
                self._persist(result)
            except (ValueError,OSError) as exc:error=str(exc)
        self.hint.setText(error or f"Original sentence saved · {result['bytes']/1024:.1f} KB. Reused when other cards share this clip.")
        self._finished(error);self.busy_changed.emit(False)

    def cancel_pending(self,*args):
        if self.preview is not None:self.preview.stop();self.preview._preview_audio=None
        self._generation+=1;self.audio=None
