"""Siden Telefoner (MDM): driftstelefoner registreret ved ERP-enhedsnavn og klargjort fra IN-BASE.

Kun for administratorer. Siden henter fra Supabase, når den åbnes eller
efter en handling – aldrig i baggrunden.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMenu, QMessageBox, QToolButton

from app.domain import mdm_enhed as md
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, vis_dato
from app.ui.mdm_dialoger import KlargoeringDialog, TelefonDialog
from app.ui.sag_liste_side import Filtervalg, Kolonne, SagListeSide
from app.ui.theme import status_stil


def _tid(tekst: str) -> str:
    return f"{vis_dato(tekst[:10])} {tekst[11:16]}".strip() if tekst else ""


class MdmSide(SagListeSide):
    def __init__(self, service, parent=None):
        kolonner = [
            Kolonne("Enhedsnavn", 130, lambda e: e.navn, tooltip=lambda e: e.note),
            Kolonne("Telefonnr.", 140, lambda e: e.telefonnummer),
            Kolonne("Status", 160, lambda e: e.status, stil=lambda e: status_stil(e.status),
                    sortering=lambda e: md.STATUSSER.index(e.status)
                    if e.status in md.STATUSSER else 99),
            Kolonne("Model", 170, lambda e: e.visningsmodel),
            Kolonne("Serienr.", 140, lambda e: e.serienummer, tooltip=lambda e: e.imei),
            Kolonne("Android", 80, lambda e: e.android_version),
            Kolonne("Klargjort", 0, lambda e: _tid(e.klargjort), sortering=lambda e: e.klargjort),
        ]
        filtre = [Filtervalg("Status", lambda: list(md.STATUSSER), lambda e: e.status)]
        super().__init__(
            "Telefoner (MDM)",
            "Driftstelefoner registreret ved enhedsnavn fra ERP (fx ISM589) og klargjort med "
            "QR-kode direkte fra IN-BASE. Kun basale apps, FL-UPDATE og FL-TMS.",
            kolonner, filtre=filtre, sorter_efter=0, parent=parent,
            soegning=lambda e: f"{e.imei} {e.note}",
        )
        self.service = service
        self.soegefelt.setPlaceholderText("Søg på enhedsnavn, nummer, serienr., IMEI …")

        self.mangler_label = QLabel("")
        self.mangler_label.setObjectName("advarsel")
        self.mangler_label.setWordWrap(True)
        self.layout().insertWidget(1, self.mangler_label)

        # Almindelige brugere ser siden, men den er låst (ingen data, ingen knapper).
        self.laast_label = QLabel("🔒  Telefoner (MDM) er kun for administratorer. Kontakt en "
                                  "administrator, hvis en telefon skal oprettes eller klargøres.")
        self.laast_label.setObjectName("advarsel")
        self.laast_label.setWordWrap(True)
        self.layout().insertWidget(1, self.laast_label)

        ny = lav_knap("+ Ny telefon", "primary")
        ny.clicked.connect(self.ny)
        klargoer = lav_knap("Klargør (QR-kode)…")
        klargoer.clicked.connect(lambda: self._paa_valgt(self.klargoer))
        handling = self._handlingsmenu()
        self._admin_widgets = (ny, klargoer, handling, self.soegefelt, self.tabel,
                               *self.filter_felter)
        for knap in (ny, klargoer):
            self.tilfoej_knap(knap)
        self.tilfoej_handling(handling)
        self.tabel.doubleClicked.connect(lambda _i: self._paa_valgt(self.rediger))
        self.anvend_rolle(False)

    def _handlingsmenu(self):
        menu = QMenu(self)
        for tekst, funktion in (("Ret oplysninger…", self.rediger),
                                ("Vis nulstillingskode…", self.vis_kode),
                                ("Markér som udgået", self.udgaaet), (None, None),
                                ("Fjern fra listen", self.slet)):
            if tekst is None:
                menu.addSeparator()
            else:
                menu.addAction(tekst, lambda f=funktion: self._paa_valgt(f))
        knap = QToolButton()
        knap.setText("Handling")
        knap.setProperty("variant", "menu")
        knap.setCursor(Qt.CursorShape.PointingHandCursor)
        knap.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        knap.setMenu(menu)
        return knap

    def anvend_rolle(self, admin: bool) -> None:
        self.laast_label.setVisible(not admin)
        for widget in self._admin_widgets:
            widget.setEnabled(admin)
        if not admin:
            self.ryd()
            self.mangler_label.hide()

    ### ----- data -----------------------------------------------------------

    def opdater(self) -> None:
        admin = self.service.er_administrator()
        self.anvend_rolle(admin)
        if not admin:
            return
        mangler = self.service.klargoering_mangler()
        self.mangler_label.setText(mangler)
        self.mangler_label.setVisible(bool(mangler))
        alle = udfoer(self, self.service.hent_alle)
        if alle is not FEJL:
            self.vis(alle)

    def _paa_valgt(self, funktion):
        enhed_id = self.valgt_id()
        enhed = next((e for e in self._sager if e.id == enhed_id), None)
        if enhed is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en telefon i listen først.")
            return
        funktion(enhed)

    def _bekraeft(self, titel, tekst) -> bool:
        return QMessageBox.question(
            self, titel, tekst, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    ### ----- handlinger -----------------------------------------------------

    def ny(self) -> None:
        dialog = TelefonDialog(self, self.service)
        if dialog.exec() and dialog.resultat is not None:
            self.opdater()
            self.klargoer(dialog.resultat)

    def rediger(self, enhed) -> None:
        if TelefonDialog(self, self.service, enhed).exec():
            self.opdater()

    def klargoer(self, enhed) -> None:
        if enhed.status == md.KLARGJORT and not self._bekraeft(
                "Klargør igen", f"{enhed.navn} er allerede klargjort. Klargøre den igen "
                "(telefonen skal fabriksnulstilles)?"):
            return
        dialog = KlargoeringDialog(self, self.service, enhed)
        dialog.exec()
        if dialog.klargjort:
            self.opdater()

    def vis_kode(self, enhed) -> None:
        if not enhed.nulstillingskode:
            reserve = self.service.reservekode()
            QMessageBox.information(
                self, "Nulstillingskode",
                f"{enhed.navn} er klargjort uden egen nulstillingskode.\n\n"
                + (f"Brug reservekoden: {reserve}\n\nKræver, at telefonen har IN-BASE Klargøring "
                   "version 2 (opdatér den via Bluetooth – se docs/MDM_OPSAETNING.md).\n"
                   "Tast derefter *#*#46227#*#* i Telefon-appen."
                   if reserve else "Der findes ingen reservekode på denne pc."))
            return
        QMessageBox.information(
            self, "Nulstillingskode",
            f"{enhed.navn}: {enhed.nulstillingskode}\n\n"
            "Fabriksnulstil telefonen sådan:\n"
            "1. Åbn Telefon-appen og tast *#*#46227#*#*\n"
            "2. Indtast koden og vælg \"Fabriksnulstil telefonen\".\n\n"
            "Del ikke koden med brugeren af telefonen.")

    def udgaaet(self, enhed) -> None:
        if self._bekraeft("Markér som udgået", f"Markér {enhed.navn} som udgået?"):
            if udfoer(self, self.service.marker_udgaaet, enhed) is not FEJL:
                self.opdater()

    def slet(self, enhed) -> None:
        if self._bekraeft("Fjern fra listen", f"Fjern {enhed.navn} fra IN-BASE?"):
            if udfoer(self, self.service.slet, enhed) is not FEJL:
                self.opdater()
