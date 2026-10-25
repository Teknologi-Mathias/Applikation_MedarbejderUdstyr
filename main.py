"""Start IN-BASE: logning -> konfiguration -> services -> log på -> hovedvindue.

Se docs/ARKITEKTUR.md for lagdeling og app/bootstrap.py for, hvilke
implementeringer (Supabase som standard, JSON kun ved INBASE_BACKEND=json)
der bruges. Konfigurationen læses fra %APPDATA%\\IN-BASE\\.env.
"""
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAVN, VERSION, __version__, session
from app.bootstrap import byg_fra_konfiguration, klargoer
from app.infrastructure.database.config import KonfigurationsFejl
from app.infrastructure.database.connection import DatabaseIkkeTilgaengelig
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
    """Den centrale datamappe kan ikke bruges. Brugeren vælger selv offline-drift (kun JSON)."""
    if not tjenester.lagring.understoetter_offline or not tjenester.lagring.offline_kopi_findes():
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
    app.setApplicationVersion(__version__)
    app.setWindowIcon(lav_app_ikon())   # alle vinduer og beskedbokse
    anvend_tema(app)

    try:
        tjenester = byg_fra_konfiguration()
    except (KonfigurationsFejl, DatabaseIkkeTilgaengelig) as fejl:
        log.error("Konfigurationsfejl: %s", fejl)
        QMessageBox.critical(None, "IN-BASE er ikke konfigureret", str(fejl))
        return 1
    try:
        klargoer(tjenester)
    except DataFejl as fejl:
        log.error("Opstart fejlede: %s", fejl)
        if not _tilbyd_offline(tjenester, fejl):
            QMessageBox.critical(None, "Datafejl", str(fejl))
            return 1

    offline_tekst = (
        "Du arbejder OFFLINE på en lokal kopi. Ændringer synkroniseres, når du går online."
        if tjenester.lagring.offline else ""
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


def selvtest() -> int:
    """`IN-BASE.exe --selvtest`: kontrollerer en bygget app uden GUI og uden netværk.

    Indlæser konfigurationen, importerer Supabase-pakkerne og bygger en klient
    (inkl. SSL-certifikater). Resultatet står i loggen; exit-kode 0 = OK.
    """
    import importlib

    from app.infrastructure import stier
    from app.infrastructure.database.config import DatabaseKonfiguration, hent_konfiguration
    from app.infrastructure.database.connection import nulstil_klient, opret_klient

    opsaet_logning()
    try:
        for modul in ("supabase", "postgrest", "supabase_auth", "supabase_functions", "httpx",
                      "certifi", "dotenv", "app.repositories.supabase.sag_repository",
                      "app.repositories.supabase.konto_repository",
                      "app.repositories.supabase.indmelding_repository", "app.ui.hovedvindue"):
            importlib.import_module(modul)
        opret_klient(DatabaseKonfiguration("https://selvtest.supabase.co", "sb_publishable_selvtest"))
        nulstil_klient()
        konfig = hent_konfiguration()
        log.info("Selvtest OK (%s): backend=%s, konfigureret=%s, konfigfil=%s (findes=%s), "
                 "lokal mappe=%s", VERSION, konfig.backend, konfig.er_konfigureret,
                 stier.KONFIG_FIL, stier.KONFIG_FIL.exists(), stier.LOKAL_MAPPE)
        return 0
    except Exception:
        log.exception("Selvtest fejlede")
        return 1


if __name__ == "__main__":
    sys.exit(selvtest() if "--selvtest" in sys.argv else main())
