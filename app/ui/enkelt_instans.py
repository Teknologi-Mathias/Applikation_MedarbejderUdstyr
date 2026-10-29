"""Kun én IN-BASE pr. Windows-bruger.

IN-BASE kører videre i baggrunden ved uret. Startes programmet igen, beder den
nye proces den kørende om at vise sit vindue og afslutter selv (ellers ville to
kopier vise de samme påmindelser og forvirre installeren).

Mens programmet kører, holdes desuden Windows-mutexen MUTEX. Samme navn står som
AppMutex i installer/IN-BASE.iss, så installeren kan se, at IN-BASE kører. Før
en opdatering frigives begge (frigiv()), og programmet lukker.
"""
import getpass
import logging
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

MUTEX = "IN-BASE-Instans"     # = AppMutex i installer/IN-BASE.iss
_VENT_MS = 300


def _servernavn() -> str:
    try:
        bruger = getpass.getuser()
    except Exception:
        bruger = "ukendt"
    return f"IN-BASE-{bruger}"


class EnkeltInstans(QObject):
    vis = Signal()          # en ny start bad om at vise vinduet

    def __init__(self, navn: str | None = None, mutex: str | None = MUTEX):
        super().__init__()
        self.navn = navn or _servernavn()
        self.mutex_navn = mutex
        self._server = None
        self._mutex = None

    def koerer_allerede(self) -> bool:
        """Kører IN-BASE allerede? Så bedes den vise sit vindue."""
        sok = QLocalSocket()
        sok.connectToServer(self.navn)
        if not sok.waitForConnected(_VENT_MS):
            return False
        sok.write(b"vis")
        sok.waitForBytesWritten(_VENT_MS)
        sok.disconnectFromServer()
        return True

    def start(self) -> None:
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._forbindelse)
        if not self._server.listen(self.navn):
            QLocalServer.removeServer(self.navn)       # efterladt efter et nedbrud
            if not self._server.listen(self.navn):
                log.warning("Enkelt-instans: kunne ikke lytte på %s (%s)", self.navn,
                            self._server.errorString())
        self._mutex = _opret_mutex(self.mutex_navn)

    def _forbindelse(self) -> None:
        while self._server and self._server.hasPendingConnections():
            sok = self._server.nextPendingConnection()
            sok.disconnected.connect(sok.deleteLater)
            self.vis.emit()

    def frigiv(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._mutex:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._mutex)
            self._mutex = None


def _opret_mutex(navn: str | None):
    if not navn or sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        opret = ctypes.windll.kernel32.CreateMutexW
        opret.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        opret.restype = wintypes.HANDLE
        return opret(None, False, navn)
    except (AttributeError, OSError):
        log.warning("Windows-mutex kunne ikke oprettes", exc_info=True)
        return None
