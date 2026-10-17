"""Windows launch integration, local diagnostics and single-instance activation."""
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import sys
from core.preferences import data_dir


def configure_logging():
    folder=data_dir()/'logs'
    folder.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(folder/'grammai.log',maxBytes=512*1024,backupCount=2,encoding='utf8')
    logging.basicConfig(level=logging.WARNING,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    def crash(kind,value,traceback):
        logging.critical('Unhandled exception',exc_info=(kind,value,traceback))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None,'GrammAI encountered an error','Please restart GrammAI. Diagnostic logs: '+str(folder))
    sys.excepthook=crash


class SingleInstance:
    def __init__(self):
        from PySide6.QtNetwork import QLocalServer
        self.server=QLocalServer()
        self.name='GrammAI-'+hashlib.sha256(str(data_dir().resolve()).encode()).hexdigest()[:20]

    def acquire(self):
        from PySide6.QtNetwork import QLocalSocket,QLocalServer
        socket=QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(500):
            socket.write(b'activate');socket.waitForBytesWritten(500);socket.disconnectFromServer()
            return False
        if not self.server.listen(self.name):
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                raise RuntimeError('Cannot start the GrammAI instance listener')
        return True

    def on_activate(self,callback):
        def connection():
            while self.server.hasPendingConnections():
                socket=self.server.nextPendingConnection()
                socket.disconnectFromServer();socket.deleteLater()
                callback()
        self.server.newConnection.connect(connection)
