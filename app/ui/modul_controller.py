"""Controllere: binder dialoger og knapper til et moduls service.

Brugerfladen indeholder ingen forretningsregler – controlleren åbner
dialoger, kalder servicen via udfoer() (ensartet fejlhåndtering) og beder
hovedvinduet opdatere visningerne bagefter.
"""
from PySide6.QtCore import QDate
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
)

from app import session
from app.domain import skabelon as sk
from app.domain import statusprik as prik
from app.domain.opgave import Opgave
from app.domain.sag import Sag
from app.services.onboarding_service import opgave_med_noegle
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


def _vis_menu(menu: QMenu, pos=None) -> None:
    """Drop down-menuen: lige under cellen (pos fra tabellen), ellers ved musen."""
    menu.exec(pos if pos is not None else QCursor.pos())


def _menupunkt(menu: QMenu, tekst: str, funktion, valgt: bool = False):
    handling = menu.addAction(tekst, funktion)
    handling.setCheckable(True)
    handling.setChecked(valgt)
    return handling


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
        """Kalder servicen. En gemt sag lægges direkte ind i visningen (intet hentes
        igen); en konflikt genindlæser (efter_konflikt); andet (fx sletning) genindlæser."""
        resultat = udfoer(self.vindue, funktion, *args, efter_konflikt=self._opdater, **kwargs)
        if isinstance(resultat, Sag):
            self.vindue.sag_gemt(resultat)
        elif resultat is not FEJL:
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
        if dialog.exec() and not kun_laesning and self._foer_gem(dialog.sag):
            self._udfoer(self.service.gem_aendret, sag, dialog.sag)

    def _foer_gem(self, ny) -> bool:
        """Kaldes, før sagsvinduets ændringer gemmes. False = gem ikke."""
        return True

    def hurtig_status(self, sag_id, noegle, pos=None):
        """Klik på et statusfelt i "Aktive forløb" (app/domain/statusprik.py): en drop
        down-menu under cellen. Valget gemmes straks og vises uden genindlæsning."""

    def _ingen_opgave(self, felt: str) -> None:
        QMessageBox.information(self.vindue, felt,
                                f"Forløbet har ingen opgave for \"{felt}\" (se skabelonen).")

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
        if handling == al.ARKIVER:
            return self.arkiver(sag_id)
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

    def hurtig_status(self, sag_id, noegle, pos=None):
        sag = self._hent(sag_id)
        if sag is None:
            return
        menu = QMenu(self.vindue)
        if noegle == prik.TANKKORT:
            opgaver = prik.tankkort_opgaver(sag)
            if not opgaver:
                return self._ingen_opgave("Tankkort spærret")
            nu = prik.tankkort(sag).tekst
            _menupunkt(menu, "Ikke relevant", lambda: self._ikke_relevant(sag, opgaver),
                       nu == "Ikke relevant")
            for tekst, status in (("Ikke behandlet", Opgave.IKKE_STARTET),
                                  ("Behandlet", Opgave.UDFOERT)):
                _menupunkt(menu, tekst, lambda s=status: self._saet_alle(sag, opgaver, s),
                           nu == tekst)
        elif noegle == prik.TOEJ:
            opgaver = prik.toej_opgaver(sag)
            if not opgaver:
                return self._ingen_opgave("Tøj og udstyr")
            gruppe = [o.id for o in opgaver]
            afleveret = {o.id for o in opgaver if o.status == Opgave.UDFOERT}
            for o in opgaver:
                _menupunkt(menu, o.udstyr, lambda i=o.id: self._udfoer(
                    self.service.marker_afleveret, sag, afleveret ^ {i}, gruppe),
                    o.id in afleveret)
            menu.addSeparator()
            menu.addAction("Intet afleveret", lambda: self._udfoer(
                self.service.marker_afleveret, sag, [], gruppe))
            menu.addAction("Alt afleveret", lambda: self._udfoer(
                self.service.marker_afleveret, sag, gruppe, gruppe))
        elif noegle == prik.TELEFON:
            opgaver = prik.telefon_opgaver(sag)
            if not opgaver:
                return self._ingen_opgave("Telefon & SIM-kort")
            nu = prik.telefon(sag).tekst
            for tekst, status in (("Intet afleveret", Opgave.IKKE_STARTET),
                                  ("Alt afleveret", Opgave.UDFOERT)):
                _menupunkt(menu, tekst, lambda s=status: self._saet_alle(sag, opgaver, s),
                           nu == tekst)
        elif noegle == prik.NAV:
            opgave = prik.nav_opgave(sag)
            if opgave is None:
                return self._ingen_opgave("Lukket i NAV?")
            for tekst, status in (("Nej", Opgave.IKKE_STARTET), ("Ja", Opgave.UDFOERT)):
                _menupunkt(menu, tekst, lambda s=status: self._saet_alle(sag, [opgave], s),
                           (opgave.status == Opgave.UDFOERT) == (status == Opgave.UDFOERT))
        _vis_menu(menu, pos)

    def _saet_alle(self, sag, opgaver, status):
        """Samme status på feltets opgaver (oftest én) – ét gem pr. ændret opgave."""
        for o in opgaver:
            if o.status == status:
                continue
            sag = self._udfoer(self.service.saet_opgave_status, sag, o.id, status)
            if sag is FEJL:
                return

    def _ikke_relevant(self, sag, opgaver):
        """"Ikke relevant" (fx intet tankkort): opgaverne undtages med en fast begrundelse."""
        for o in opgaver:
            if o.status == Opgave.UNDTAGET:
                continue
            sag = self._udfoer(self.service.undtag_opgave, sag, o.id,
                               prik.IKKE_RELEVANT_BEGRUNDELSE)
            if sag is FEJL:
                return

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
        """Opret kandidat. Efter gem vises kandidaten markeret i oversigten med en
        bekræftelse – sagsvinduet åbnes ikke af sig selv, så "Annuller" aldrig kan
        forveksles med at fortryde en oprettelse, der allerede er gemt."""
        skabeloner = udfoer(self.vindue, self.t.skabeloner.sagsskabeloner, "onboarding")
        profiler = udfoer(self.vindue, self.t.indstillinger.udstyrsprofiler)
        if skabeloner is FEJL or profiler is FEJL:
            return
        dialog = OnboardingDialog(self.vindue, None, skabeloner, self._omraader(),
                                  self.ansvarlige(), profiler)
        if not dialog.exec():
            return
        data = dialog.hent_data()
        sag = self._udfoer(self.service.opret, self.service.ny_sag(data), data["skabelon"], data)
        if sag is not FEJL:
            self.vindue.vis_oprettet(sag)

    ### ----- statusfelter (kontrakt, udstyr, opfølgning) ---------------------

    def hurtig_status(self, sag_id, noegle, pos=None):
        sag = self._hent(sag_id)
        if sag is None:
            return
        menu = QMenu(self.vindue)
        if noegle == prik.KONTRAKT:
            opgave = opgave_med_noegle(sag, prik.KONTRAKT)
            if opgave is None:
                return self._ingen_opgave("Kontrakt")
            for tekst, status in (("Ikke sendt", Opgave.IKKE_STARTET),
                                  ("Sendt (afventer underskrift)", Opgave.AFVENTER),
                                  ("Modtaget retur", Opgave.UDFOERT)):
                _menupunkt(menu, tekst, lambda s=status: self.saet_kontrakt(sag, s),
                           opgave.status == status)
        elif noegle == prik.UDSTYR:
            poster = sag.behov.udstyrsposter()
            if not poster:
                QMessageBox.information(self.vindue, "Udstyr",
                                        "Der er ikke valgt udstyr til forløbet.")
                return
            sendt = set(sag.behov.sendte_poster())
            for n, tekst in poster:
                _menupunkt(menu, tekst, lambda n=n: self._udfoer(
                    self.service.marker_udstyr_sendt, sag, sendt ^ {n}), n in sendt)
            menu.addSeparator()
            menu.addAction("Intet udstyr sendt", lambda: self._udfoer(
                self.service.marker_udstyr_sendt, sag, []))
            menu.addAction("Alt udstyr sendt", lambda: self._udfoer(
                self.service.marker_udstyr_sendt, sag, [n for n, _ in poster]))
        elif noegle == prik.OPFOELGNING:
            opgave = opgave_med_noegle(sag, prik.OPFOELGNING)
            if opgave is None:
                return self._ingen_opgave("Opfølgning")
            for tekst, status in (("Ikke afholdt", Opgave.IKKE_STARTET),
                                  ("Afholdt", Opgave.UDFOERT)):
                _menupunkt(menu, tekst, lambda s=status: self._udfoer(
                    self.service.saet_opgave_status, sag, opgave.id, s),
                    (opgave.status == Opgave.UDFOERT) == (status == Opgave.UDFOERT))
        _vis_menu(menu, pos)

    def saet_kontrakt(self, sag, status):
        """Manglende lønnr./ansættelsesdato (står på kontrakten) spørges der om her
        i stedet for en fejl."""
        felter = self._kontraktfelter(sag) if status != Opgave.IKKE_STARTET else {}
        if felter is not None:
            self._udfoer(self.service.saet_kontrakt, sag, status, **felter)

    def _kontraktfelter(self, sag) -> dict | None:
        """Spørger efter de felter, kontrakten mangler. None = annulleret."""
        felter = {}
        mangler = self.service.mangler_til_kontrakt(sag)
        if "loennr" in mangler:
            loennr, ok = QInputDialog.getText(
                self.vindue, "Lønnr. mangler",
                f"Lønnr. står på kontrakten – indtast lønnr. fra ERP for {sag.navn}:")
            if not ok or not loennr.strip():
                return None
            felter["loennr"] = loennr.strip()
        if "ansaettelsesdato" in mangler:
            dato = _vaelg_dato(self.vindue, f"Ansættelsesdato: {sag.navn}", "")
            if not dato:
                return None
            felter["ansaettelsesdato"] = dato
        return felter

    def _foer_gem(self, ny) -> bool:
        if not ny.kontrakt_sendt():
            return True
        felter = self._kontraktfelter(ny)
        if felter is None:
            return False
        self.service.udfyld_kontraktfelter(ny, **felter)
        return True

    def action_handling(self, handling, sag_id, opgave_id):
        """Kontrakten sendt/udført fra Action Center: spørg efter manglende felter."""
        if handling in (al.UDFOERT, al.AFVENTER):
            sag = self._hent(sag_id)
            if sag is None:
                return
            opgave = sag.find_opgave(opgave_id)
            if opgave is not None and opgave.noegle == prik.KONTRAKT:
                return self.saet_kontrakt(
                    sag, Opgave.UDFOERT if handling == al.UDFOERT else Opgave.AFVENTER)
        return super().action_handling(handling, sag_id, opgave_id)

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
