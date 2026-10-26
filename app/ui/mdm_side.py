"""Siderne Telefoner (MDM) og Arkiv: driftstelefoner registreret ved ERP-enhedsnavn og klargjort
fra IN-BASE.

Kun for brugere med modulet Telefoner (og administratorer). Siderne henter fra Supabase, når de
åbnes eller efter en handling – aldrig i baggrunden. Telefoner, der fjernes fra listen, flyttes til
Arkiv (ikke slettet), så nulstillingskoden mm. bevares.
"""
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QMenu, QMessageBox, QToolButton

from app.domain import mdm_enhed as md
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, vis_dato
from app.ui.mdm_dialoger import KlargoeringDialog, OpdateringDialog, TelefonDialog
from app.ui.sag_liste_side import Filtervalg, Kolonne, SagListeSide
from app.ui.theme import status_stil


def _tid(tekst: str) -> str:
    return f"{vis_dato(tekst[:10])} {tekst[11:16]}".strip() if tekst else ""


def _handlingsknap(menu: QMenu) -> QToolButton:
    knap = QToolButton()
    knap.setText("Handling")
    knap.setProperty("variant", "menu")
    knap.setCursor(Qt.CursorShape.PointingHandCursor)
    knap.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    knap.setMenu(menu)
    return knap


class _MdmListeSide(SagListeSide):
    """Fælles for Telefoner og Arkiv: kolonner, låsning, koder og CSV-eksport."""

    def __init__(self, service, titel, undertitel, ekstra_kolonner=(), parent=None):
        kolonner = [
            Kolonne("Enhedsnavn", 130, lambda e: e.navn, tooltip=lambda e: e.note),
            Kolonne("Telefonnr.", 140, lambda e: e.telefonnummer),
            Kolonne("Status", 160, lambda e: e.status, stil=lambda e: status_stil(e.status),
                    sortering=lambda e: md.STATUSSER.index(e.status)
                    if e.status in md.STATUSSER else 99),
            Kolonne("Mail", 60, lambda e: "Ja" if e.mail else "",
                    tooltip=lambda e: "Firma-mail (IMAP) i Gmail" if e.mail else ""),
            Kolonne("Model", 170, lambda e: e.visningsmodel),
            Kolonne("Serienr.", 140, lambda e: e.serienummer, tooltip=lambda e: e.imei),
            Kolonne("Android", 80, lambda e: e.android_version),
            *ekstra_kolonner,
            Kolonne("Klargjort", 0, lambda e: _tid(e.klargjort), sortering=lambda e: e.klargjort),
        ]
        filtre = [Filtervalg("Status", lambda: list(md.STATUSSER), lambda e: e.status)]
        super().__init__(titel, undertitel, kolonner, filtre=filtre, sorter_efter=0,
                         parent=parent, soegning=lambda e: f"{e.imei} {e.note}")
        self.service = service
        self.soegefelt.setPlaceholderText("Søg på enhedsnavn, nummer, serienr., IMEI …")

        # Almindelige brugere ser siden, men den er låst (ingen data, ingen knapper).
        self.laast_label = QLabel("🔒  Du har ikke adgang til Telefoner (MDM). Kontakt en "
                                  "administrator, hvis du skal have adgang.")
        self.laast_label.setObjectName("advarsel")
        self.laast_label.setWordWrap(True)
        self.layout().insertWidget(1, self.laast_label)
        self._admin_widgets = [self.soegefelt, self.tabel, *self.filter_felter]
        self.tabel.doubleClicked.connect(lambda _i: self._paa_valgt(self.dobbeltklik))

    def _tilfoej_knapper(self, *knapper) -> None:
        for knap in knapper:
            self.tilfoej_knap(knap)
        self._admin_widgets.extend(knapper)

    def _tilfoej_menu(self, punkter) -> None:
        """punkter: [(tekst, funktion(enhed)), ...]; (None, None) giver en streg."""
        menu = QMenu(self)
        for tekst, funktion in punkter:
            if tekst is None:
                menu.addSeparator()
            else:
                menu.addAction(tekst, lambda f=funktion: self._paa_valgt(f))
        knap = _handlingsknap(menu)
        self.tilfoej_handling(knap)
        self._admin_widgets.append(knap)

    def _eksportknap(self):
        knap = lav_knap("Eksportér CSV…")
        knap.setToolTip("Alle telefoner (også arkiverede) med nulstillings- og ændringskoder "
                        "– til opbevaring offline.")
        knap.clicked.connect(self.eksporter)
        return knap

    def dobbeltklik(self, enhed) -> None:
        self.vis_kode(enhed)

    def anvend_rolle(self, admin: bool) -> None:
        self.laast_label.setVisible(not admin)
        for widget in self._admin_widgets:
            widget.setEnabled(admin)
        if not admin:
            self.ryd()

    def hent(self):
        raise NotImplementedError

    ### ----- data -----------------------------------------------------------

    def opdater(self) -> None:
        adgang = self.service.har_adgang()
        self.anvend_rolle(adgang)
        if not adgang:
            return
        alle = udfoer(self, self.hent)
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

    ### ----- koder og eksport -----------------------------------------------

    def eksporter(self) -> None:
        sti, _ = QFileDialog.getSaveFileName(
            self, "Eksportér telefoner og koder",
            f"IN-BASE telefoner {date.today().isoformat()}.csv", "CSV-fil (*.csv)")
        if not sti:
            return
        antal = udfoer(self, self.service.eksporter_csv, sti)
        if antal is not FEJL:
            QMessageBox.information(
                self, "Eksportér CSV",
                f"{antal} telefoner (inkl. arkiverede) med koder er gemt i:\n{sti}\n\n"
                "Filen kan åbnes i Excel. Opbevar den et sikkert sted.")

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

    def vis_supportkode(self, enhed) -> None:
        kode = md.supportkode(enhed.nulstillingskode or self.service.reservekode())
        if not kode:
            QMessageBox.information(self, "Supportkode",
                                    f"{enhed.navn} har ingen nulstillingskode – og dermed ingen "
                                    "supportkode.")
            return
        QMessageBox.information(
            self, "Supportkode",
            f"{enhed.navn}: {kode}\n\n"
            "Koden må gives til brugeren ved fejlfinding. Den kan kun vise og skjule Chrome "
            "(uden Google-konto) – ikke nulstille telefonen.\n\n"
            "1. Åbn Telefon-appen og tast *#*#46227#*#*\n"
            "2. Indtast supportkoden og vælg \"Vis Chrome\".\n"
            "3. Når fejlen er løst: samme sted, vælg \"Skjul Chrome\".")


class MdmSide(_MdmListeSide):
    def __init__(self, service, parent=None):
        super().__init__(
            service, "Telefoner (MDM)",
            "Driftstelefoner registreret ved enhedsnavn fra ERP (fx ISM589) og klargjort med "
            "QR-kode direkte fra IN-BASE. Kun basale apps, FL-UPDATE og FL-TMS.", parent=parent)

        self.mangler_label = QLabel("")
        self.mangler_label.setObjectName("advarsel")
        self.mangler_label.setWordWrap(True)
        self.layout().insertWidget(1, self.mangler_label)

        ny = lav_knap("+ Ny telefon", "primary")
        ny.clicked.connect(self.ny)
        klargoer = lav_knap("Klargør (QR-kode)…")
        klargoer.clicked.connect(lambda: self._paa_valgt(self.klargoer))
        opdater = lav_knap("Opdater telefoner…")
        opdater.setToolTip("Klargjorte telefoner henter den nyeste styrings-app fra denne pc – "
                           "uden nulstilling.")
        opdater.clicked.connect(self.opdater_telefoner)
        self._tilfoej_knapper(ny, klargoer, opdater, self._eksportknap())
        self._tilfoej_menu((("Ret oplysninger…", self.rediger),
                            ("Vis nulstillingskode…", self.vis_kode),
                            ("Vis supportkode (Chrome)…", self.vis_supportkode),
                            (None, None),
                            ("Slå firma-mail til…", lambda e: self.skift_mail(e, True)),
                            ("Slå firma-mail fra…", lambda e: self.skift_mail(e, False)),
                            (None, None),
                            ("Markér som udgået", self.udgaaet), (None, None),
                            ("Fjern fra listen (til Arkiv)…", self.arkiver)))
        self.anvend_rolle(False)

    def dobbeltklik(self, enhed) -> None:
        self.rediger(enhed)

    def anvend_rolle(self, admin: bool) -> None:
        super().anvend_rolle(admin)
        if not admin:
            self.mangler_label.hide()

    def hent(self):
        return self.service.hent_alle()

    def opdater(self) -> None:
        if self.service.har_adgang():
            mangler = self.service.klargoering_mangler()
            self.mangler_label.setText(mangler)
            self.mangler_label.setVisible(bool(mangler))
        super().opdater()

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

    def skift_mail(self, enhed, til: bool) -> None:
        """Viser ændringskoden til telefonen og gemmer derefter, at mail er slået til/fra."""
        kode = md.aendringskode(enhed.nulstillingskode, md.MAIL_TIL if til else md.MAIL_FRA)
        if not kode:
            QMessageBox.information(self, "Firma-mail",
                                    f"{enhed.navn} har ingen nulstillingskode – klargør den igen.")
            return
        handling = "slå firma-mail til" if til else "slå firma-mail fra"
        if self._bekraeft(
                "Firma-mail",
                f"{enhed.navn}: ændringskode {kode}\n\n"
                "1. Åbn \"IN-BASE indstillinger\" på telefonen (eller tast *#*#46227#*#*).\n"
                "2. Indtast koden og vælg \"Brug ændringskode\".\n"
                "3. Telefonen bekræfter ændringen.\n\n"
                f"Koden må gives til brugeren – den kan kun {handling}. Kræver IN-BASE "
                "Klargøring 4.0 eller nyere på telefonen.\n\n"
                f"Gem i IN-BASE, at {enhed.navn} {'har' if til else 'ikke har'} firma-mail?"):
            if udfoer(self, self.service.saet_mail, enhed, til) is not FEJL:
                self.opdater()

    def opdater_telefoner(self) -> None:
        apk = udfoer(self, self.service.opdaterings_apk)
        if apk is not FEJL:
            OpdateringDialog(self, apk).exec()

    def udgaaet(self, enhed) -> None:
        if self._bekraeft("Markér som udgået", f"Markér {enhed.navn} som udgået?"):
            if udfoer(self, self.service.marker_udgaaet, enhed) is not FEJL:
                self.opdater()

    def arkiver(self, enhed) -> None:
        if self._bekraeft("Fjern fra listen",
                          f"Fjern {enhed.navn} fra listen?\n\nTelefonen flyttes til Arkiv med "
                          "nulstillingskoden – intet slettes, og den kan gendannes derfra."):
            if udfoer(self, self.service.arkiver, enhed) is not FEJL:
                self.opdater()


class MdmArkivSide(_MdmListeSide):
    """Telefoner fjernet fra listen. Koderne kan stadig ses, og telefonen kan gendannes."""

    def __init__(self, service, parent=None):
        super().__init__(
            service, "Arkiv",
            "Telefoner fjernet fra Telefoner (MDM). De er ikke slettet – nulstillingskoder mm. "
            "er bevaret, og telefonerne kan gendannes.",
            [Kolonne("Arkiveret", 130, lambda e: _tid(e.arkiveret),
                     sortering=lambda e: e.arkiveret)], parent=parent)
        self._tilfoej_knapper(self._eksportknap())
        self._tilfoej_menu((("Vis nulstillingskode…", self.vis_kode),
                            ("Vis supportkode (Chrome)…", self.vis_supportkode),
                            (None, None),
                            ("Gendan til Telefoner", self.gendan), (None, None),
                            ("Slet permanent…", self.slet)))
        self.anvend_rolle(False)

    def hent(self):
        return self.service.hent_arkiverede()

    def gendan(self, enhed) -> None:
        if udfoer(self, self.service.gendan, enhed) is not FEJL:
            self.opdater()

    def slet(self, enhed) -> None:
        if self._bekraeft(
                "Slet permanent",
                f"Slet {enhed.navn} permanent?\n\nNulstillingskoden forsvinder, og telefonen kan "
                "ikke længere nulstilles med den. Eksportér evt. en CSV-fil først.\n\n"
                "Det kan ikke fortrydes."):
            if udfoer(self, self.service.slet, enhed) is not FEJL:
                self.opdater()
