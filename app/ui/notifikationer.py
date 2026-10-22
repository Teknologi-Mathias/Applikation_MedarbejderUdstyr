"""Ikon i proceslinjen og Windows-notifikationer.

Hvad der skal mindes om, afgøres af PaamindelsesService (gentagelser,
regler). Denne klasse viser kun beskederne – og kun hvis brugeren har
Windows-notifikationer slået til under Indstillinger. Action Center viser
de samme ting uanset denne indstilling.

Virker kun, mens programmet kører. Lukkes vinduet, kører programmet videre
i baggrunden (ikonet ved uret), indtil man vælger "Afslut".
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app import APP_NAVN


class Notifikationer(QObject):
    vis_vindue = Signal()
    afslut = Signal()
    aabn_sag = Signal(str, str, str)   # (proces, sag_id, opgave_id) ved klik på besked

    def __init__(self, ikon, parent=None):
        super().__init__(parent)
        self.slaaet_til = True
        self._sidste_sag = None

        self.tilgaengelig = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(ikon, self)
        self.tray.setToolTip(APP_NAVN)

        menu = QMenu()
        menu.addAction(f"Åbn {APP_NAVN}", self.vis_vindue.emit)
        menu.addSeparator()
        menu.addAction("Afslut", self.afslut.emit)
        self.tray.setContextMenu(menu)
        self._menu = menu   # holdes i live

        self.tray.activated.connect(self._ikon_aktiveret)
        self.tray.messageClicked.connect(self._besked_klikket)
        if self.tilgaengelig:
            self.tray.show()

    def _ikon_aktiveret(self, grund):
        if grund in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.vis_vindue.emit()

    def _besked_klikket(self):
        self.vis_vindue.emit()
        if self._sidste_sag:
            self.aabn_sag.emit(*self._sidste_sag)

    def vis_besked(self, titel, tekst, sag=None) -> bool:
        """Viser en Windows-notifikation, hvis det er slået til. Returnerer om den blev vist."""
        if not (self.slaaet_til and self.tilgaengelig and QSystemTrayIcon.supportsMessages()):
            return False
        self._sidste_sag = sag
        # Logoet vises i notifikationen (i stedet for Windows' standardikon).
        self.tray.showMessage(titel, tekst, self.tray.icon(), 10_000)
        return True

    def vis_paamindelser(self, paamindelser) -> None:
        for p in paamindelser:
            self.vis_besked(p.titel, p.tekst, (p.modul, p.sag_id, ""))
