import sys
from PySide2.QtWidgets import QApplication
from ui import PiecesMainWindow

if __name__ == '__main__':
	app = QApplication([])
	main_window = PiecesMainWindow()
	main_window.show()
	sys.exit(app.exec_())
