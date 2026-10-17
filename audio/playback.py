"""In-memory replay through Qt audio. No temporary audio files."""
import numpy as np
from PySide6.QtCore import QObject,QBuffer,QByteArray,QIODevice,Slot,QTimer
from PySide6.QtMultimedia import QAudio,QAudioFormat,QAudioSink,QMediaDevices


class AudioReplay(QObject):
    def __init__(self,events,store,parent=None):
        super().__init__(parent)
        self.events,self.store=events,store
        self._sink=None
        self._buffer=None
        events.replay_requested.connect(self.play)

    @Slot(str,float)
    def play(self,key,speed=1.):
        self.stop()
        if not key:
            return
        audio=self.store.get(key)
        if audio is None:
            self.events.status_changed.emit('Replay expired. Audio is kept in RAM for at most 60 seconds.')
            return
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
        self.events.playback_active.emit(True)
        self.events.status_changed.emit('Replaying original audio; capture is suppressed to avoid feedback.')
        self._sink.start(self._buffer)

    @Slot(QAudio.State)
    def _state(self,state):
        if self._sink is None or self.sender() is not self._sink:
            return
        if state==QAudio.State.IdleState:
            self.stop()
        elif state==QAudio.State.StoppedState and self._sink.error()!=QAudio.Error.NoError:
            self.stop()
            self.events.status_changed.emit('Audio replay failed. Check your output device.')

    def stop(self):
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
        if self._sink is None:
            self.events.playback_active.emit(False)
