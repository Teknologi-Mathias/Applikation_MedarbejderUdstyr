"""Ønsker & Udvikling: oprettelse, behandling, kommentarer og historik.

Servicen validerer input og rettigheder, så brugeren får en tydelig besked,
FØR noget sendes. Den egentlige adgangskontrol ligger i databasen (RLS og
RPC'erne i migrering 006) – også hvis nogen går uden om programmet.

Den aktuelle bruger kommer fra aktuel_bruger() (sat i bootstrap). Indsender
og forfatter bestemmes dog altid af lagringen ud fra login – ikke herfra.
"""
import logging
from typing import Callable, Optional

from app.domain import indmelding as im
from app.domain.bruger import normaliser_brugernavn
from app.domain.indmelding import Detaljer, Indmelding, Kommentar
from app.repositories.base import IndmeldingRepository
from app.repositories.fejl import ValideringsFejl
from app.services.auth_service import ROLLE_ADMIN

log = logging.getLogger(__name__)

KUN_ADMIN = ("Kun administratorer kan ændre status, prioritet, ansvarlig, planlagt version "
             "og løsning.")
KUN_EGNE = "Du kan kun redigere dine egne indmeldinger, mens de har status Indsendt."


def _rens(noegle: str, vaerdi) -> str:
    tekst = str(vaerdi or "")
    if noegle == "ansvarlig":
        return normaliser_brugernavn(tekst)
    return tekst.strip() if noegle in ("titel", "kategori", "status", "prioritet",
                                       "planlagt_version") else tekst.rstrip()


def valider(ind: Indmelding) -> None:
    """Regler for en (ny eller ændret) indmelding. ValideringsFejl ved brud."""
    if not ind.titel.strip():
        raise ValideringsFejl("Skriv en titel.")
    if len(ind.titel) > im.MAKS_TITEL:
        raise ValideringsFejl(f"Titlen må højst være {im.MAKS_TITEL} tegn.")
    if ind.kategori not in im.KATEGORIER:
        raise ValideringsFejl("Vælg en kategori.")
    if not ind.beskrivelse.strip():
        raise ValideringsFejl("Skriv en kort beskrivelse.")
    if ind.status not in im.STATUSSER:
        raise ValideringsFejl(f"Ukendt status: {ind.status}")
    if ind.prioritet not in im.PRIORITETER:
        raise ValideringsFejl(f"Ukendt prioritet: {ind.prioritet}")
    if len(ind.planlagt_version) > im.MAKS_VERSION:
        raise ValideringsFejl(f"Planlagt version må højst være {im.MAKS_VERSION} tegn.")
    for noegle in ("beskrivelse", "problem", "oensket_resultat", "effekt", "supplerende",
                   "loesning"):
        if len(getattr(ind, noegle)) > im.MAKS_TEKST:
            raise ValideringsFejl(f"{im.FELT_NAVNE[noegle]} må højst være "
                                  f"{im.MAKS_TEKST:,} tegn.".replace(",", "."))
    if ind.status == im.AFVIST and not ind.loesning.strip():
        raise ValideringsFejl("Skriv en begrundelse i feltet Løsning, når en indmelding afvises.")


class IndmeldingService:
    def __init__(self, repo: IndmeldingRepository,
                 aktuel_bruger: Callable[[], Optional[dict]] = lambda: None):
        self.repo = repo
        self._aktuel_bruger = aktuel_bruger

    ### ----- rettigheder (til brugerfladen og som første kontrol) -----------

    def _brugernavn(self) -> str:
        bruger = self._aktuel_bruger()
        if not bruger:
            raise ValideringsFejl("Du er ikke logget på.")
        return bruger["brugernavn"]

    def er_administrator(self) -> bool:
        bruger = self._aktuel_bruger()
        return bool(bruger) and bruger.get("rolle") == ROLLE_ADMIN

    def er_min(self, ind: Indmelding) -> bool:
        bruger = self._aktuel_bruger()
        return bool(bruger) and normaliser_brugernavn(ind.indsender) == \
            normaliser_brugernavn(bruger["brugernavn"])

    def er_tildelt_mig(self, ind: Indmelding) -> bool:
        bruger = self._aktuel_bruger()
        return bool(bruger) and bool(ind.ansvarlig) and \
            normaliser_brugernavn(ind.ansvarlig) == normaliser_brugernavn(bruger["brugernavn"])

    def kan_redigere_tekst(self, ind: Indmelding) -> bool:
        return self.er_administrator() or (self.er_min(ind) and ind.status == im.INDSENDT)

    ### ----- læsning --------------------------------------------------------

    def hent_alle(self) -> list[Indmelding]:
        """Nyeste først."""
        return sorted(self.repo.hent_alle(), key=lambda i: i.nummer, reverse=True)

    def hent(self, indmelding_id: str) -> Optional[Indmelding]:
        return self.repo.hent(indmelding_id)

    def detaljer(self, indmelding_id: str) -> Optional[Detaljer]:
        ind = self.repo.hent(indmelding_id)
        if ind is None:
            return None
        kommentarer = self.repo.kommentarer(ind.id)
        if not self.er_administrator():   # Supabase filtrerer allerede (RLS); JSON gør ikke
            kommentarer = [k for k in kommentarer if not k.intern]
        return Detaljer(ind, kommentarer, self.repo.historik(ind.id))

    def signatur(self) -> tuple:
        return self.repo.signatur()

    ### ----- skrivning ------------------------------------------------------

    def opret(self, data: dict) -> Indmelding:
        """data: tekstfelterne (titel, kategori, beskrivelse, ...)."""
        self._brugernavn()
        felter = {k: _rens(k, data.get(k)) for k in im.TEKSTFELTER}
        valider(Indmelding(**felter))
        ny = self.repo.opret(felter)
        log.info("Indmelding %s oprettet (%s)", ny.visningsnummer, ny.kategori)
        return ny

    def opdater(self, ind: Indmelding, aendringer: dict) -> Indmelding:
        """Gemmer de felter i aendringer, der faktisk er ændret. KonfliktFejl, hvis
        indmeldingen er ændret af en anden siden den blev hentet."""
        self._brugernavn()
        ukendte = set(aendringer) - set(im.TEKSTFELTER) - set(im.BEHANDLINGSFELTER)
        if ukendte:
            raise ValideringsFejl(f"Ukendt felt: {', '.join(sorted(ukendte))}")
        rene = {k: _rens(k, v) for k, v in aendringer.items()}
        rene = {k: v for k, v in rene.items() if v != getattr(ind, k)}
        if not rene:
            return ind
        if any(k in im.BEHANDLINGSFELTER for k in rene) and not self.er_administrator():
            raise ValideringsFejl(KUN_ADMIN)
        if any(k in im.TEKSTFELTER for k in rene) and not self.kan_redigere_tekst(ind):
            raise ValideringsFejl(KUN_EGNE)
        if "status" in rene and not im.overgang_tilladt(ind.status, rene["status"]):
            raise ValideringsFejl(
                f'Status kan ikke ændres fra "{ind.status}" til "{rene["status"]}". '
                f"Mulige: {', '.join(im.OVERGANGE.get(ind.status, ())) or 'ingen'}.")
        valider(Indmelding.fra_dict({**ind.til_dict(), **rene}))
        gemt = self.repo.opdater(ind.id, ind.version, rene)
        log.info("Indmelding %s ændret: %s", gemt.visningsnummer, ", ".join(sorted(rene)))
        return gemt

    def tilfoej_kommentar(self, indmelding_id: str, tekst: str, intern: bool = False) -> Kommentar:
        self._brugernavn()
        tekst = (tekst or "").strip()
        if not tekst:
            raise ValideringsFejl("Skriv en kommentar.")
        if len(tekst) > im.MAKS_KOMMENTAR:
            raise ValideringsFejl(f"En kommentar må højst være {im.MAKS_KOMMENTAR:,} tegn."
                                  .replace(",", "."))
        if intern and not self.er_administrator():
            raise ValideringsFejl("Kun administratorer kan skrive interne noter.")
        return self.repo.tilfoej_kommentar(indmelding_id, tekst, bool(intern))

    def slet(self, ind: Indmelding) -> None:
        if not self.er_administrator():
            raise ValideringsFejl("Kun administratorer kan slette indmeldinger.")
        self.repo.slet(ind.id)
        log.info("Indmelding %s slettet", ind.visningsnummer)
