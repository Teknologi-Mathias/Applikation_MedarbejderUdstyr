"""Controllere: binder dialoger og knapper til et moduls service.

Brugerfladen indeholder ingen forretningsregler – controlleren åbner
dialoger, kalder servicen via udfoer() (ensartet fejlhåndtering) og beder
hovedvinduet opdatere visningerne bagefter.
"""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app import session
from app.domain import skabelon as sk
from app.domain.opgave import Opgave
from app.ui import action_liste as al
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import laes_dato, vis_dato
from app.ui.medarbejder_dialog import MedarbejderDialog
from app.ui.onboarding_dialog import OnboardingDialog
from app.ui.rykker_dialog import RykkerDialog
from app.ui.sag_dialog import SagDialog


def _vaelg_dato(parent, titel, nuvaerende) -> str | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(titel)
    felt = QDateEdit()
    felt.setCalendarPopup(True)
    felt.setDisplayFormat("dd-MM-yyyy")
    dato = laes_dato(nuvaerende)
    felt.setDate(dato if dato.isValid() else QDate.currentDate())
    knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    knapper.accepted.connect(dialog.accept)
    knapper.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addWidget(felt)
    layout.addWidget(knapper)
    return felt.date().toString("yyyy-MM-dd") if dialog.exec() else None


class ModulController:
    def __init__(self, vindue, tjenester, service):
        self.vindue = vindue          # forælder til dialoger + opdater_alle()
        self.t = tjenester
        self.service = service

    ### ----- hjælpere -------------------------------------------------------

    def _opdater(self):
        self.vindue.opdater_alle()

    def _hent(self, sag_id):
        sag = udfoer(self.vindue, self.service.hent, sag_id)
        if sag is FEJL:
            return None
        if sag is None:
            QMessageBox.warning(self.vindue, "Sag ikke fundet",
                                "Sagen findes ikke længere (slettet eller flyttet af en anden).")
            self._opdater()
        return sag

    def _udfoer(self, funktion, *args, **kwargs):
        resultat = udfoer(self.vindue, funktion, *args, efter_konflikt=self._opdater, **kwargs)
        self._opdater()
        return resultat

    def ansvarlige(self) -> list[str]:
        """Afdelingerne fra Indstillinger → Organisation efterfulgt af brugerne."""
        ind = udfoer(self.vindue, self.t.indstillinger.hent)
        afdelinger = [] if ind is FEJL else list(ind["ansvarlige"])
        brugere = udfoer(self.vindue, self.t.auth.brugere)
        brugernavne = [] if brugere is FEJL else sorted(
            b["brugernavn"] for b in brugere if b.get("aktiv", True))
        return afdelinger + [b for b in brugernavne if b not in afdelinger]

    ### ----- fælles handlinger ----------------------------------------------

    def aabn_sag(self, sag_id, opgave_id="", start_fane=SagDialog.FANE_OPGAVER, kun_laesning=False):
        sag = self._hent(sag_id)
        if sag is None:
            return
        if sag.arkiveret:
            kun_laesning = True
        dialog = SagDialog(self.vindue, sag, self.ansvarlige(), fokus_opgave_id=opgave_id or None,
                           kun_laesning=kun_laesning, start_fane=start_fane)
        if dialog.exec() and not kun_laesning:
            self._udfoer(self.service.gem_aendret, sag, dialog.sag)

    def vis_historik(self, sag_id):
        self.aabn_sag(sag_id, start_fane=SagDialog.FANE_TIDSLINJE)

    def arkiver(self, sag_id):
        sag = self._hent(sag_id)
        if sag and self._bekraeft("Arkivér", f"Vil du arkivere {sag.navn}?"):
            self._udfoer(self.service.arkiver, sag)

    def aktiver(self, sag_id):
        sag = self._hent(sag_id)
        if sag and self._bekraeft("Gør aktiv", f"Vil du gøre {sag.navn} aktiv igen?"):
            self._udfoer(self.service.aktiver, sag)

    def slet(self, sag_id):
        if not session.er_admin():
            return
        sag = self._hent(sag_id)
        if sag and self._bekraeft(
            "Slet permanent",
            f"Vil du slette {sag.navn} permanent?\n\nHandlingen kan ikke fortrydes.",
            advarsel=True,
        ):
            self._udfoer(self.service.slet, sag)

    def tilfoej_notat(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        tekst, ok = QInputDialog.getMultiLineText(
            self.vindue, "Tilføj notat",
            f"Notat til {sag.navn}s tidslinje.\nNotatet kan ikke ændres, når det er gemt.",
        )
        if ok and tekst.strip():
            self._udfoer(self.service.tilfoej_notat, sag, tekst)

    def action_handling(self, handling, sag_id, opgave_id):
        """Hurtige handlinger fra Action Center (højreklik)."""
        if handling == al.HISTORIK:
            return self.vis_historik(sag_id)
        sag = self._hent(sag_id)
        if sag is None:
            return
        if handling == al.UDFOERT:
            self._udfoer(self.service.marker_opgave_udfoert, sag, opgave_id)
        elif handling in (al.I_GANG, al.AFVENTER):
            status = Opgave.I_GANG if handling == al.I_GANG else Opgave.AFVENTER
            self._udfoer(self.service.saet_opgave_status, sag, opgave_id, status)
        elif handling == al.FRIST:
            opgave = sag.find_opgave(opgave_id)
            ny = _vaelg_dato(self.vindue, f"Ny frist: {opgave.navn if opgave else ''}",
                             opgave.frist if opgave else "")
            if ny:
                self._udfoer(self.service.aendr_frist, sag, opgave_id, ny)
        elif handling == al.ANSVARLIG:
            navn, ok = QInputDialog.getItem(self.vindue, "Tildel ansvarlig", "Ansvarlig:",
                                            self.ansvarlige(), 0, True)
            if ok:
                self._udfoer(self.service.tildel_ansvarlig, sag, navn, opgave_id or None)

    def _bekraeft(self, titel, tekst, advarsel=False):
        knapper = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        vis = QMessageBox.warning if advarsel else QMessageBox.question
        return vis(self.vindue, titel, tekst, knapper, QMessageBox.StandardButton.No) \
            == QMessageBox.StandardButton.Yes


class OffboardingController(ModulController):

    def opret(self):
        skabeloner = udfoer(self.vindue, self.t.skabeloner.sagsskabeloner, "offboarding")
        if skabeloner is FEJL:
            return
        dialog = MedarbejderDialog(self.vindue, skabeloner=skabeloner)
        if not dialog.exec():
            return
        data = dialog.hent_data()
        sag = self._udfoer(self.service.opret, self.service.ny_sag(data), data["skabelon"])
        if sag is not FEJL:
            self.aabn_sag(sag.id)

    def rediger(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        dialog = MedarbejderDialog(self.vindue, sag)
        if dialog.exec():
            self._udfoer(self.service.rediger, sag, dialog.hent_data())

    def opret_rykker(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        mails = udfoer(self.vindue, self.t.skabeloner.aktive, sk.MAIL)
        if mails is FEJL:
            return
        dialog = RykkerDialog(self.vindue, sag, mails, self.t.skabeloner.relevant_mailskabelon(sag))
        if dialog.exec():
            self._udfoer(self.service.registrer_rykker, sag, dialog.rykker)

    def marker_rykker_sendt(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        usendte = sag.usendte_rykkere()
        if not usendte:
            QMessageBox.information(self.vindue, "Ingen kladder",
                                    "Der er ingen rykkere, som venter på at blive sendt.")
            return
        valg = [f"{r.kategori} – oprettet {vis_dato(r.oprettet[:10])} – {r.emne}" for r in usendte]
        tekst, ok = QInputDialog.getItem(
            self.vindue, "Marker rykker som sendt",
            "Hvilken rykker er sendt?\nMarker den først, når mailen faktisk er afsendt.",
            valg, 0, False,
        )
        if ok:
            self._udfoer(self.service.marker_rykker_sendt, sag, usendte[valg.index(tekst)].id)

    def registrer_returlabel(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        link, ok = QInputDialog.getText(self.vindue, "Returlabel sendt",
                                        "Tracking-link til returpakken (valgfrit):",
                                        QLineEdit.EchoMode.Normal, sag.tracking_link)
        if ok:
            self._udfoer(self.service.registrer_returlabel, sag, link)


class OnboardingController(ModulController):

    def _omraader(self):
        ind = udfoer(self.vindue, self.t.indstillinger.hent)
        return [] if ind is FEJL else ind["omraader"]

    def opret(self):
        skabeloner = udfoer(self.vindue, self.t.skabeloner.sagsskabeloner, "onboarding")
        if skabeloner is FEJL:
            return
        dialog = OnboardingDialog(self.vindue, None, skabeloner, self._omraader(), self.ansvarlige())
        if not dialog.exec():
            return
        data = dialog.hent_data()
        sag = self._udfoer(self.service.opret, self.service.ny_sag(data), data["skabelon"], data)
        if sag is not FEJL:
            self.aabn_sag(sag.id)

    def rediger(self, sag_id):
        sag = self._hent(sag_id)
        if sag is None:
            return
        dialog = OnboardingDialog(self.vindue, sag, (), self._omraader(), self.ansvarlige())
        if not dialog.exec():
            return
        data = dialog.hent_data()
        opdateret = self._udfoer(self.service.rediger, sag, data)
        if opdateret is FEJL:
            return
        if (data["status_manuel"], data["status_begrundelse"]) != (
            opdateret.status_manuel, opdateret.status_begrundelse
        ):
            self._udfoer(self.service.saet_manuel_status, opdateret,
                         data["status_manuel"], data["status_begrundelse"])
