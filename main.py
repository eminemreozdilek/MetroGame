import sys
from PySide6 import QtWidgets
from gui import TrainLineUI

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = TrainLineUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
