import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from data_manager import DataFejl
from gui import MainWindow
from theme import anvend_tema


def main():
    app = QApplication(sys.argv)
    anvend_tema(app)

    try:
        window = MainWindow()
    except DataFejl as fejl:
        QMessageBox.critical(None, "Datafejl", str(fejl))
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
