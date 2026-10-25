"""Short audio IO jobs; never encode or decode on the GUI/capture thread."""
from PySide6.QtCore import QObject,QRunnable,Signal

class AudioTaskSignals(QObject):
    ready=Signal(object,object)

class AudioTask(QRunnable):
    def __init__(self,work):
        super().__init__();self.work=work;self.signals=AudioTaskSignals()
    def run(self):
        try:result=self.work();error=None
        except Exception as exc:result=None;error=str(exc) or type(exc).__name__
        self.signals.ready.emit(result,error)
