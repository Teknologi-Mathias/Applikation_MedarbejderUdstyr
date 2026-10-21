"""Ikon i proceslinjen og Windows-notifikationer om forsinkede opgaver.

Virker kun, mens programmet kører. Lukkes vinduet, kører programmet videre
i baggrunden (ikonet ved uret), indtil man vælger "Afslut".
"""
from datetime import date

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app import APP_NAVN, alarmer, skabeloner as sk


class Notifikationer(QObject):
    vis_vindue = Signal()
    afslut = Signal()

    def __init__(self, ikon, parent=None):
        super().__init__(parent)
        # (opgave-id, dato) der allerede er givet besked om – max én gang pr. dag.
        self._givet_besked = set()

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

    def tjek(self, medarbejdere, skabeloner):
        """Viser påmindelser ud fra de aktive påmindelsesskabeloner.

        Hver påmindelse vises højst én gang pr. dag. Rammer en skabelon mere end
        3 ting på én gang, samles de i én besked.
        """
        i_dag = date.today()
        nye = {}
        for skabelon, noegle, vaerdier in alarmer.paamindelser(skabeloner, medarbejdere, i_dag):
            if (noegle, i_dag) in self._givet_besked:
                continue
            self._givet_besked.add((noegle, i_dag))
            nye.setdefault(skabelon["id"], (skabelon, []))[1].append(vaerdier)

        for skabelon, alle_vaerdier in nye.values():
            # Manglende værdier vises som "–" i stedet for at blokere påmindelsen.
            vaerdier = {k: "–" for k in sk.PAAMINDELSE_VARIABLER} | alle_vaerdier[0]
            titel, _ = sk.flet(skabelon["titel"], vaerdier, sk.PAAMINDELSE_VARIABLER)
            tekst, _ = sk.flet(skabelon["tekst"], vaerdier, sk.PAAMINDELSE_VARIABLER)
            if len(alle_vaerdier) > 3:
                titel = f"{skabelon['navn']}: {len(alle_vaerdier)} sager"
                tekst = ", ".join(v["navn"] for v in alle_vaerdier[:5]) + (
                    " m.fl." if len(alle_vaerdier) > 5 else ""
                )
            elif len(alle_vaerdier) > 1:
                tekst += f"\n(+ {len(alle_vaerdier) - 1} mere)"
            self.vis_besked(titel, tekst)
