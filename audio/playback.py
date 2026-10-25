"""Qt replay for session clips and asynchronously decoded saved recordings."""
import numpy as np
from PySide6.QtCore import QObject,QBuffer,QByteArray,QIODevice,Slot,QTimer,QThreadPool
from PySide6.QtMultimedia import QAudio,QAudioFormat,QAudioSink,QMediaDevices


class AudioReplay(QObject):
    def __init__(self,events,store,parent=None):
        super().__init__(parent)
        self.events,self.store=events,store
        self._sink=None
        self._buffer=None
        self._generation=0;self._key='';self._duration_ms=0
        self._timer=QTimer(self);self._timer.setInterval(100);self._timer.timeout.connect(self._position)
        events.replay_requested.connect(self.play)
        events.replay_buffer_requested.connect(self.play_buffer)

    @Slot(str,float)
    def play(self,key,speed=1.):
        self._stop_pronunciation()
        self.stop()
        if not key:
            return
        if key.startswith('saved:'):
            from audio.library import AudioLibrary
            from audio.tasks import AudioTask
            generation=self._generation
            self._load=AudioTask(lambda:AudioLibrary().load(key[6:]))
            self._load.signals.ready.connect(lambda audio,error:self._loaded(generation,key,speed,audio,error))
            QThreadPool.globalInstance().start(self._load)
            return
        audio=self.store.get(key)
        if audio is None:
            self.events.status_changed.emit('Replay expired. Audio is kept in RAM for at most 60 seconds.')
            return
        self._start(key,speed,audio)

    @Slot(str,object,float)
    def play_buffer(self,key,audio,speed=1.):
        self._stop_pronunciation()
        self.stop()
        samples=np.asarray(audio,dtype=np.float32).reshape(-1)
        if not 0<len(samples)<=self.store.sample_rate*60 or not np.isfinite(samples).all():
            self.events.status_changed.emit('Preview audio is unavailable.');return
        self._start(key,speed,samples)

    def _stop_pronunciation(self):
        service=getattr(self.events,'pronunciation_service',None)
        if service is not None:service.stop()

    def _loaded(self,generation,key,speed,audio,error):
        if generation!=self._generation:return
        if error:self.events.status_changed.emit(error);return
        self._start(key,speed,audio)

    def _start(self,key,speed,audio):
        device=QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self.events.status_changed.emit('No audio output device is available for replay.')
            return
        format=QAudioFormat()
        format.setSampleRate(self.store.sample_rate)
        format.setChannelCount(1)
        format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(format):
            format=device.preferredFormat()
        speed=max(.5,min(1.5,float(speed)))
        count=max(1,round(len(audio)*format.sampleRate()/self.store.sample_rate/speed))
        samples=np.interp(np.arange(count)*self.store.sample_rate*speed/format.sampleRate(),
                          np.arange(len(audio)),audio)
        samples=np.repeat(samples[:,None],format.channelCount(),axis=1)
        kind=format.sampleFormat()
        if kind==QAudioFormat.SampleFormat.Float:
            pcm=samples.astype('<f4')
        elif kind==QAudioFormat.SampleFormat.Int32:
            pcm=(np.clip(samples,-1,1)*2147483647).astype('<i4')
        elif kind==QAudioFormat.SampleFormat.UInt8:
            pcm=((np.clip(samples,-1,1)+1)*127.5).astype('u1')
        else:
            pcm=(np.clip(samples,-1,1)*32767).astype('<i2')
        self._buffer=QBuffer(self)
        self._buffer.setData(QByteArray(pcm.tobytes()))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink=QAudioSink(device,format,self)
        self._sink.stateChanged.connect(self._state)
        self._key=key;self._duration_ms=round(len(audio)/self.store.sample_rate/speed*1000)
        self.events.setProperty('replay_active',True)
        self.events.playback_started.emit(key)
        self.events.playback_active.emit(True)
        self.events.status_changed.emit('Replaying original audio; capture is suppressed to avoid feedback.')
        self._sink.start(self._buffer)
        self._timer.start()

    @Slot(QAudio.State)
    def _state(self,state):
        if self._sink is None or self.sender() is not self._sink:
            return
        if state==QAudio.State.IdleState:
            self.stop()
        elif state==QAudio.State.StoppedState and self._sink.error()!=QAudio.Error.NoError:
            self.stop()
            self.events.status_changed.emit('Audio replay failed. Check your output device.')

    def _position(self):
        if self._sink:self.events.playback_position.emit(self._key,int(self._sink.processedUSecs()/1000),self._duration_ms)

    def stop(self):
        self._generation+=1;self._timer.stop();self.events.playback_started.emit('')
        self.events.setProperty('replay_active',False)
        sink,self._sink=self._sink,None
        buffer,self._buffer=self._buffer,None
        if sink:
            sink.stop()
            sink.deleteLater()
        if buffer:
            buffer.close()
            buffer.deleteLater()
        if sink:
            QTimer.singleShot(200,self,self._resume_capture)

    def _resume_capture(self):
        if self._sink is None and not self.events.property('pronunciation_active'):
            self.events.playback_active.emit(False)
