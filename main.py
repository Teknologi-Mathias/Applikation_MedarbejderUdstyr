"""Start IN-BASE: logning -> services -> datamappe -> log på -> hovedvindue.

Se docs/ARKITEKTUR.md for lagdeling og app/bootstrap.py for, hvilke
implementeringer (JSON i dag, Supabase senere) der bruges.
"""
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAVN, VERSION, session
from app.bootstrap import byg_tjenester, klargoer
from app.infrastructure.logning import opsaet_logning
from app.repositories.fejl import DataFejl
from app.ui.hjaelpere import lav_app_ikon
from app.ui.hovedvindue import MainWindow
from app.ui.login_dialog import LoginDialog
from app.ui.theme import anvend_tema

log = logging.getLogger("in-base")

# Egen identitet over for Windows, så proceslinjen og notifikationer viser
# IN-BASE-logoet – også når programmet køres fra kildekoden (python.exe).
WINDOWS_APP_ID = "MASAN.IN-BASE"


def _saet_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        log.warning("Kunne ikke sætte Windows AppUserModelID", exc_info=True)


def _tilbyd_offline(tjenester, fejl) -> bool:
    """Den centrale datamappe kan ikke bruges. Brugeren vælger selv offline-drift."""
    if not tjenester.lagring.offline_kopi_findes():
        return False
    info = tjenester.lagring.offline_info()
    svar = QMessageBox.question(
        None, "Ingen forbindelse",
        f"{fejl}\n\nDer findes en lokal kopi fra {info.get('kopieret', 'ukendt tidspunkt')}. "
        "Vil du arbejde offline på den? Ændringer gemmes lokalt og synkroniseres, "
        "når du går online igen.",
    )
    if svar != QMessageBox.StandardButton.Yes:
        return False
    tjenester.lagring.gaa_offline()
    return True


def main():
    opsaet_logning()
    _saet_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAVN)
    app.setApplicationVersion(VERSION.lstrip("V"))
    app.setWindowIcon(lav_app_ikon())   # alle vinduer og beskedbokse
    anvend_tema(app)

    tjenester = byg_tjenester()
    try:
        klargoer(tjenester)
    except DataFejl as fejl:
        log.error("Opstart fejlede: %s", fejl)
        if not _tilbyd_offline(tjenester, fejl):
            QMessageBox.critical(None, "Datafejl", str(fejl))
            return 1

    offline_tekst = (
        "Du arbejder OFFLINE på en lokal kopi. Ændringer synkroniseres, når du går online."
        if tjenester.datakilde.offline else ""
    )
    # Programmet åbner først efter et vellykket log på.
    login = LoginDialog(tjenester.auth, offline_tekst=offline_tekst)
    if not login.exec():
        return 0
    session.log_ind(login.bruger)

    window = MainWindow(tjenester)
    window.efter_log_paa()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
