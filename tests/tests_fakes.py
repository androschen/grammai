from PySide6.QtCore import QThread, Signal

class FakeCapture(QThread):
    device_resolved=Signal(object)
    def __init__(self,*args):
        super().__init__()
    def run(self):
        while not self.isInterruptionRequested():
            self.msleep(5)
    def stop(self):
        self.stop_requested = True
        self.requestInterruption()

class SlowEngine:
    active=0
    maximum=0
    def configure(self,config):
        self.config=config
    def ensure_loaded(self,**kwargs):
        type(self).active+=1
        type(self).maximum=max(type(self).maximum,type(self).active)
        QThread.msleep(150)
        type(self).active-=1
    def ensure_translator(self):
        pass
    def reset_failures(self):
        pass
