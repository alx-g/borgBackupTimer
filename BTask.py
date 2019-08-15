from PyQt5.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot


class BTaskSignals(QObject):
    done = pyqtSignal()
    fail = pyqtSignal()


class BTask(QRunnable):
    def __init__(self, func, *args, **kwargs):
        super(BTask, self).__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = BTaskSignals()

    @pyqtSlot(name='borgBackupTimer_BTask')
    def run(self):
        ret = False
        try:
            ret = self.func(*self.args, **self.kwargs)
        except:
            ret = False
        finally:
            if ret:
                self.signals.done.emit()
            else:
                self.signals.fail.emit()

