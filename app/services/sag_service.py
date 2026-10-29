"""Forretningsregler fælles for alle sagstyper (onboarding og offboarding).

Brugerfladen kalder kun services – aldrig repositories direkte. Alle
ændringer går gennem gem_aendret(), som validerer, skriver forskellene i
tidslinjen og gemmer med optimistisk låsning (KonfliktFejl ved samtidige
ændringer).
"""
import logging
from datetime import date
from typing import Optional

from app.domain import afhaengighed
from app.domain.opgave import Opgave, laes_iso_dato
from app.domain.sag import Sag
from app.repositories.base import SagRepository
from app.repositories.fejl import KonfliktFejl, ValideringsFejl
from app.services import workflow

log = logging.getLogger(__name__)


class SagService:
    def __init__(self, repo: SagRepository):
        self.repo = repo
        self.proces = repo.proces

    ### ----- læsning --------------------------------------------------------

    def hent_aktive(self) -> list[Sag]:
        return self.repo.hent_aktive()

    def hent_arkiverede(self) -> list[Sag]:
        return self.repo.hent_arkiverede()

    def hent(self, sag_id: str) -> Optional[Sag]:
        return self.repo.hent(sag_id)

    def signatur(self) -> tuple:
        return self.repo.signatur()

    ### ----- validering -----------------------------------------------------

    def valider(self, sag: Sag) -> None:
        """Fælles regler. Underklasser tilføjer deres egne."""
        if not (sag.navn or "").strip():
            raise ValideringsFejl("Navn skal udfyldes.")
        if sag.status_manuel and not sag.status_begrundelse:
            raise ValideringsFejl("En manuelt låst status kræver en begrundelse.")
        for opgave in sag.opgaver:
            if opgave.status == Opgave.UNDTAGET and not opgave.begrundelse:
                raise ValideringsFejl(f"'{opgave.navn}' er undtaget uden begrundelse.")
            if opgave.frist and laes_iso_dato(opgave.frist) is None:
                raise ValideringsFejl(f"'{opgave.navn}' har en ugyldig frist.")
        fejl = afhaengighed.find_fejl(sag.opgaver)
        if fejl:
            raise ValideringsFejl(" ".join(fejl))

    def loennr_optaget(self, loennr: str, undtagen_id: str | None = None) -> bool:
        loennr = (loennr or "").strip()
        if not loennr:
            return False
        return any(
            s.loennr == loennr and s.id != undtagen_id
            for s in self.hent_aktive() + self.hent_arkiverede()
        )

    ### ----- oprettelse og ændring ------------------------------------------

    def forbered_opgaver(self, sag: Sag, data: dict | None = None) -> None:
        """Kaldes, når opgaverne er oprettet – før validering og gem. Underklasser
        bruger den til fx betingede opgaver. data = formularens øvrige felter."""

    def opret(self, sag: Sag, skabelon: dict | None, data: dict | None = None) -> Sag:
        if skabelon:
            sag.opgaver = workflow.opret_opgaver(skabelon, sag.startdato())
            sag.skabelon = workflow.skabelon_reference(skabelon)
        self.forbered_opgaver(sag, data)
        self.valider(sag)
        if self.loennr_optaget(sag.loennr, sag.id):
            raise ValideringsFejl("Der findes allerede en sag med dette lønnr.")
        workflow.registrer_oprettelse(sag, skabelon)
        if sag.status_manuel:
            sag.historik.tilfoej(f"Status låst manuelt: {sag.status_manuel}",
                                 sag.status_begrundelse)
        log.info("Opretter %s-sag %s", self.proces, sag.id)
        return self.repo.gem(sag)

    def gem_aendret(self, gammel: Sag, ny: Sag, registrer: bool = True) -> Sag:
        """Gemmer en ændret kopi. registrer=True skriver forskellene i tidslinjen."""
        self.valider(ny)
        if ny.loennr != gammel.loennr and self.loennr_optaget(ny.loennr, ny.id):
            raise ValideringsFejl("Der findes allerede en sag med dette lønnr.")
        if registrer:
            workflow.registrer_aendringer(gammel, ny)
        else:
            workflow.registrer_statusskift(gammel.status, ny)
        try:
            return self.repo.gem(ny)
        except KonfliktFejl:
            # En kollega har gemt sagen imens. Flet mine ændringer ind i den
            # aktuelle udgave; kun ændringer af det samme giver en reel konflikt.
            aktuel = self.repo.hent(ny.id)
            if aktuel is None:
                raise
            flettet = workflow.flet(gammel, ny, aktuel)
            self.valider(flettet)
            log.info("Samtidig ændring af %s-sag %s flettet", self.proces, ny.id)
            return self.repo.gem(flettet)

    def saet_manuel_status(self, sag: Sag, status: str | None, begrundelse: str) -> Sag:
        ny = sag.kopi()
        if status is None or status == ny.beregnet_status() and not begrundelse:
            ny.status_manuel, ny.status_begrundelse = None, ""
        else:
            if not (begrundelse or "").strip():
                raise ValideringsFejl("Skriv hvorfor status låses manuelt.")
            ny.status_manuel = ny.normaliser_status(status)
            ny.status_begrundelse = begrundelse.strip()
        return self.gem_aendret(sag, ny)

    ### ----- arkiv ----------------------------------------------------------

    def arkiver(self, sag: Sag, kommentar: str = "") -> Sag:
        ny = sag.kopi()
        ny.arkiveret = date.today().isoformat()
        ny.historik.tilfoej("Sag arkiveret", kommentar or f"Status ved arkivering: {ny.status}",
                            data={"type": "arkiveret", "status": ny.status})
        return self.repo.arkiver(ny)

    def aktiver(self, sag: Sag) -> Sag:
        ny = sag.kopi()
        ny.arkiveret = ""
        ny.historik.tilfoej("Sag gjort aktiv igen", data={"type": "aktiveret"})
        return self.repo.aktiver(ny)

    def slet(self, sag: Sag) -> None:
        log.info("Sletter %s-sag %s permanent", self.proces, sag.id)
        self.repo.slet(sag)

    ### ----- tidslinje og opgaver (bruges også fra Action Center) -----------

    def tilfoej_notat(self, sag: Sag, tekst: str) -> Sag:
        if not (tekst or "").strip():
            raise ValideringsFejl("Notatet er tomt.")
        ny = sag.kopi()
        ny.historik.tilfoej("Notat", tekst.strip())
        return self.gem_aendret(sag, ny, registrer=False)

    def _opgave(self, sag: Sag, opgave_id: str) -> Opgave:
        opgave = sag.find_opgave(opgave_id)
        if opgave is None:
            raise ValideringsFejl("Opgaven findes ikke længere i sagen.")
        return opgave

    def marker_opgave_udfoert(self, sag: Sag, opgave_id: str) -> Sag:
        return self.saet_opgave_status(sag, opgave_id, Opgave.UDFOERT)

    def saet_opgave_status(self, sag: Sag, opgave_id: str, status: str) -> Sag:
        """Statusskift fra tabeller og hurtige handlinger (ikke Undtaget – det kræver en begrundelse)."""
        ny = sag.kopi()
        opgave = self._opgave(ny, opgave_id)
        if status != Opgave.IKKE_STARTET and ny.er_blokeret(opgave):
            raise ValideringsFejl(
                f"'{opgave.navn}' kan ikke udføres endnu. {ny.blokeringsaarsag(opgave)}."
            )
        if opgave.status == Opgave.UNDTAGET:
            opgave.begrundelse = ""          # relevant igen
        opgave.saet_status(status)
        return self.gem_aendret(sag, ny)

    def undtag_opgave(self, sag: Sag, opgave_id: str, begrundelse: str) -> Sag:
        """Opgaven er ikke relevant for forløbet (Undtaget kræver en begrundelse)."""
        if not (begrundelse or "").strip():
            raise ValideringsFejl("Skriv hvorfor opgaven ikke er relevant.")
        ny = sag.kopi()
        opgave = self._opgave(ny, opgave_id)
        opgave.saet_status(Opgave.UNDTAGET)
        opgave.begrundelse = begrundelse.strip()
        return self.gem_aendret(sag, ny)

    def aendr_frist(self, sag: Sag, opgave_id: str, ny_frist: str) -> Sag:
        if laes_iso_dato(ny_frist) is None:
            raise ValideringsFejl("Ugyldig dato.")
        ny = sag.kopi()
        self._opgave(ny, opgave_id).frist = ny_frist
        return self.gem_aendret(sag, ny)

    def tildel_ansvarlig(self, sag: Sag, ansvarlig: str, opgave_id: str | None = None) -> Sag:
        ansvarlig = (ansvarlig or "").strip()
        if not ansvarlig:
            raise ValideringsFejl("Vælg en ansvarlig.")
        ny = sag.kopi()
        if opgave_id:
            self._opgave(ny, opgave_id).ansvarlig = ansvarlig
        else:
            ny.ansvarlig = ansvarlig
        return self.gem_aendret(sag, ny)
