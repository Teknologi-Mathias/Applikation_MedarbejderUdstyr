"""Ikon i proceslinjen og Windows-notifikationer om forsinkede opgaver.

Virker kun, mens programmet kører. Lukkes vinduet, kører programmet videre
i baggrunden (ikonet ved uret), indtil man vælger "Afslut".
"""
from datetime import date

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app import alarmer


class Notifikationer(QObject):
    vis_vindue = Signal()
    afslut = Signal()

    def __init__(self, ikon, parent=None):
        super().__init__(parent)
        # (opgave-id, dato) der allerede er givet besked om – max én gang pr. dag.
        self._givet_besked = set()

        self.tilgaengelig = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(ikon, self)
        self.tray.setToolTip("Medarbejderafvikling")

        menu = QMenu()
        menu.addAction("Åbn Medarbejderafvikling", self.vis_vindue.emit)
        menu.addSeparator()
        menu.addAction("Afslut", self.afslut.emit)
        self.tray.setContextMenu(menu)
        self._menu = menu   # holdes i live

        self.tray.activated.connect(self._ikon_aktiveret)
        self.tray.messageClicked.connect(self.vis_vindue.emit)
        if self.tilgaengelig:
            self.tray.show()

    def _ikon_aktiveret(self, grund):
        if grund in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.vis_vindue.emit()

    def vis_besked(self, titel, tekst):
        if self.tilgaengelig and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(titel, tekst, QSystemTrayIcon.MessageIcon.Information, 10_000)

    def tjek(self, medarbejdere):
        """Giver besked om opgaver, der er blevet forsinkede siden sidst."""
        i_dag = date.today()
        nye = [
            (m, o) for m, o in alarmer.forsinkede(medarbejdere, i_dag)
            if (o.id, i_dag) not in self._givet_besked
        ]
        if not nye:
            return
        self._givet_besked.update((o.id, i_dag) for _, o in nye)

        linjer = [f"{o.navn} – {m.navn} ({o.ansvarlig or 'ingen ansvarlig'})"
                  for m, o in nye[:3]]
        if len(nye) > 3:
            linjer.append(f"… og {len(nye) - 3} mere")
        titel = (
            "1 opgave er forsinket" if len(nye) == 1
            else f"{len(nye)} opgaver er forsinkede"
        )
        self.vis_besked(titel, "\n".join(linjer))
