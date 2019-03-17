import signal
import sys
from PySide2.QtWidgets import QApplication
from ui import PiecesMainWindow


class MainObject:
    def __init__(self):
        self._app = QApplication([])
        # needed for when a KeyboardInterrupt is sent before the constructor of
        # PiecesMainWindow has finished
        self._main_window = None
        # for handling KeyboardInterrupts from user
        signal.signal(signal.SIGINT, self._handle_keyboard_interrupt)
        self._main_window = PiecesMainWindow()
        self._main_window.show()
        sys.exit(self._app.exec_())

    def _handle_keyboard_interrupt(self, sig, frame):
        if self._main_window:
            self._main_window.exit()
        else:
            sys.exit(0)


def main():
    MainObject()


if __name__ == '__main__':
    main()
