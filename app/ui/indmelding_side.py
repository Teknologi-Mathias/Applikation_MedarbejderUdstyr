"""Siden Ønsker & Udvikling: virksomhedens fælles forbedringskø.

Bygger på den fælles listeside (søgning, filtre, sortering). Alle medlemmer
ser hele køen; filteret "Visning" skelner mellem egne indmeldinger, dem man
er ansvarlig for, og de øvrige. Dobbeltklik åbner detaljerne.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.domain import indmelding as im
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, vis_dato
from app.ui.indmelding_dialog import IndmeldingDialog, NyIndmeldingDialog
from app.ui.sag_liste_side import Filtervalg, Kolonne, SagListeSide
from app.ui.theme import prioritet_stil, status_stil

MINE, TILDELT, OEVRIGE = "Mine indmeldinger", "Tildelt mig", "Øvrige"


class IndmeldingSide(SagListeSide):
    def __init__(self, service, hent_brugernavne, parent=None):
        """hent_brugernavne: () -> aktive brugernavne (til "Ansvarlig")."""
        kolonner = [
            Kolonne("Nr.", 70, lambda i: i.visningsnummer, sortering=lambda i: i.nummer),
            Kolonne("Titel", 290, lambda i: i.titel, tooltip=lambda i: i.beskrivelse[:300]),
            Kolonne("Kategori", 170, lambda i: i.kategori),
            Kolonne("Status", 160, lambda i: i.status, stil=lambda i: status_stil(i.status),
                    sortering=lambda i: im.STATUSSER.index(i.status)
                    if i.status in im.STATUSSER else 99),
            Kolonne("Prioritet", 110, lambda i: i.prioritet,
                    stil=lambda i: prioritet_stil(i.prioritet),
                    sortering=lambda i: im.PRIORITETER.index(i.prioritet)
                    if i.prioritet in im.PRIORITETER else -1),
            Kolonne("Indsender", 110, lambda i: i.indsender),
            Kolonne("Ansvarlig", 110, lambda i: i.ansvarlig),
            Kolonne("Version", 90, lambda i: i.planlagt_version),
            Kolonne("Oprettet", 105, lambda i: vis_dato(i.oprettet[:10]),
                    sortering=lambda i: i.oprettet),
            Kolonne("Ændret", 0, lambda i: vis_dato(i.opdateret[:10]),
                    sortering=lambda i: i.opdateret),
        ]
        filtre = [
            Filtervalg("Visning", lambda: [MINE, TILDELT, OEVRIGE], lambda i: self._visning(i)),
            Filtervalg("Status", lambda: list(im.STATUSSER), lambda i: i.status),
            Filtervalg("Kategori", lambda: list(im.KATEGORIER), lambda i: i.kategori),
            Filtervalg("Prioritet", lambda: list(im.PRIORITETER), lambda i: i.prioritet),
        ]
        super().__init__(
            "Ønsker & Udvikling",
            "Fejlmeldinger, nye ønsker og forbedringsforslag – fra indsendelse til udgivelse. "
            "Dobbeltklik for at se detaljer, kommentarer og historik.",
            kolonner, filtre=filtre, sorter_efter=0, parent=parent,
            soegning=lambda i: f"{i.beskrivelse} {i.problem} {i.oensket_resultat}",
        )
        self.service = service
        self.hent_brugernavne = hent_brugernavne
        self.soegefelt.setPlaceholderText("Søg i titel og beskrivelse …")
        self.tabel.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder)

        ny = lav_knap("+ Ny indmelding", "primary")
        ny.clicked.connect(self.ny)
        aabn = lav_knap("Åbn")
        aabn.clicked.connect(self.aabn_valgt)
        self.slet_knap = lav_knap("Slet", "danger", tooltip="Kun administratorer")
        self.slet_knap.clicked.connect(self.slet_valgt)
        for knap in (ny, aabn, self.slet_knap):
            self.tilfoej_knap(knap)
        self.tabel.doubleClicked.connect(lambda _i: self.aabn_valgt())

    def _visning(self, ind) -> str:
        if self.service.er_min(ind):
            return MINE
        return TILDELT if self.service.er_tildelt_mig(ind) else OEVRIGE

    def anvend_rolle(self, admin: bool) -> None:
        self.slet_knap.setVisible(admin)

    ### ----- data -----------------------------------------------------------

    def opdater(self) -> None:
        alle = udfoer(self, self.service.hent_alle)
        if alle is not FEJL:
            self.vis(alle)

    def _valgt_eller_besked(self):
        indmelding_id = self.valgt_id()
        if indmelding_id is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en indmelding i listen først.")
        return indmelding_id

    ### ----- handlinger -----------------------------------------------------

    def ny(self) -> None:
        dialog = NyIndmeldingDialog(self, self.service)
        if dialog.exec() and dialog.indmelding is not None:
            self.opdater()
            self.aabn(dialog.indmelding.id)

    def aabn_valgt(self) -> None:
        indmelding_id = self._valgt_eller_besked()
        if indmelding_id:
            self.aabn(indmelding_id)

    def aabn(self, indmelding_id: str) -> None:
        detaljer = udfoer(self, self.service.detaljer, indmelding_id)
        if detaljer is FEJL:
            return
        if detaljer is None:
            QMessageBox.warning(self, "Ikke fundet", "Indmeldingen findes ikke længere.")
            self.opdater()
            return
        dialog = IndmeldingDialog(self, self.service, detaljer, self.hent_brugernavne())
        dialog.exec()
        if dialog.aendret:
            self.opdater()

    def slet_valgt(self) -> None:
        indmelding_id = self._valgt_eller_besked()
        if indmelding_id is None:
            return
        ind = next((i for i in self._sager if i.id == indmelding_id), None)
        if ind is None:
            return
        svar = QMessageBox.warning(
            self, "Slet indmelding",
            f"Vil du slette {ind.visningsnummer} \"{ind.titel}\" permanent?\n\n"
            "Kommentarer og historik slettes også. Overvej i stedet at afvise den.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if svar == QMessageBox.StandardButton.Yes and udfoer(self, self.service.slet, ind) is not FEJL:
            self.opdater()
