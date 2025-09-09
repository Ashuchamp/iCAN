import sys
from PySide6.QtWidgets import QApplication
import pyqtgraph as pg
from .main_window import Main


def main():
    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    win = Main()
    win.show()
    sys.exit(app.exec())

