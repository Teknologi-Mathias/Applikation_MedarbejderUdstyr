import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import brugere, data_manager, session
from app.data_manager import DataFejl
from app.ui.hovedvindue import MainWindow
from app.ui.login_dialog import LoginDialog
from app.ui.theme import anvend_tema

### Senere kigge på tema ændring hhvis muligt ift. farveskabelon i seperat indstillign. 

def main():
    app = QApplication(sys.argv)
    anvend_tema(app)

    try:
        data_manager.klargoer_data_mappe()
        brugere.hent()   # opretter admin/admin første gang
    except DataFejl as fejl:
        QMessageBox.critical(None, "Datafejl", str(fejl))
        return 1

    # Programmet åbner først efter et vellykket log på.
    login = LoginDialog()
    if not login.exec():
        return 0
    session.log_ind(login.bruger)

    try:
        window = MainWindow()
    except DataFejl as fejl:
        QMessageBox.critical(None, "Datafejl", str(fejl))
        return 1

    window.anvend_rolle()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
