import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import data_manager
from app.data_manager import DataFejl
from app.ui.hovedvindue import MainWindow
from app.ui.theme import anvend_tema


def main():
    app = QApplication(sys.argv)
    anvend_tema(app)

    try:
        data_manager.klargoer_data_mappe()
        window = MainWindow()
    except DataFejl as fejl:
        QMessageBox.critical(None, "Datafejl", str(fejl))
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
