"""Kalender: kalendere, begivenheder, serier, påmindelser og import.

Servicen validerer input, så brugeren får en tydelig besked, FØR noget sendes.
Adgangskontrollen ligger i databasen (RPC'erne i migrering 020–022): alle ser
alle kalendere, kun ejeren ændrer, administratorer kan slette.

Serier: en ændring eller sletning af en forekomst gælder enten kun den
(kalender.KUN_DENNE), den og de fremtidige (FREMTIDIGE – serien afkortes, og en
ny serie starter ved forekomsten) eller hele serien (HELE_SERIEN). Seriens
øvrige data hentes fra de begivenheder, der sidst blev hentet med forekomster().

Påmindelser: tjek() kaldes hvert minut (i baggrunden) og returnerer de
forekomster i brugerens EGNE kalendere, hvis påmindelse er nået. Hvilke der er
vist, gemmes i Lokal/kalender_alarmer.json, så en genstart ikke giver gentagelser.

Hvilke kalendere der er slået fra, huskes pr. bruger på pc'en
(Lokal/kalender_visning.json).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from app.domain import adgang
from app.domain import kalender as kl
from app.domain.bruger import normaliser_brugernavn
from app.domain.kalender import Begivenhed, Forekomst, Kalender
from app.repositories.base import KalenderRepository
from app.repositories.fejl import KonfliktFejl, ValideringsFejl
from app.repositories.json.opsaetning_repository import JsonLokalFil
from app.services.kalender_import import ImportKilde, er_for_gammel

log = logging.getLogger(__name__)

ALARM_SENEST = timedelta(minutes=5)     # efter start vises en påmindelse ikke længere
_ALARM_VINDUE = timedelta(minutes=kl.MAKS_PAAMINDELSE + 24 * 60)


@dataclass
class ImportResultat:
    importeret: int = 0
    dubletter: int = 0
    sprunget_over: int = 0          # aflyste, ulæselige eller for gamle
    nye_kalendere: int = 0


def normaliser(b: Begivenhed) -> Begivenhed:
    """Heldag: fra kl. 00:00 første dag til kl. 00:00 dagen efter sidste dag."""
    if not b.heldag:
        return b
    start = kl.dagens_start(b.start.date())
    slut = kl.dagens_start(b.slut.date())
    if b.slut.time() != datetime.min.time() or slut <= start:
        slut += timedelta(days=1)
    return b.kopi(start=start, slut=max(slut, start + timedelta(days=1)))


def valider(b: Begivenhed) -> None:
    """Regler for en (ny eller ændret) begivenhed. ValideringsFejl ved brud."""
    if not b.kalender_id:
        raise ValideringsFejl("Vælg en kalender.")
    if not b.titel.strip():
        raise ValideringsFejl("Skriv en titel.")
    if len(b.titel) > kl.MAKS_TITEL:
        raise ValideringsFejl(f"Titlen må højst være {kl.MAKS_TITEL} tegn.")
    if len(b.sted) > kl.MAKS_STED:
        raise ValideringsFejl(f"Sted må højst være {kl.MAKS_STED} tegn.")
    if len(b.beskrivelse) > kl.MAKS_TEKST:
        raise ValideringsFejl(f"Beskrivelsen må højst være {kl.MAKS_TEKST:,} tegn."
                              .replace(",", "."))
    if b.slut < b.start or (b.heldag and b.slut == b.start):
        raise ValideringsFejl("Slut skal ligge efter start.")
    if b.paamindelse is not None and not 0 <= b.paamindelse <= kl.MAKS_PAAMINDELSE:
        raise ValideringsFejl("Påmindelsen skal være mellem 0 minutter og 4 uger før.")
    if b.gentages:
        try:
            kl.serie_slut(b)
        except (ValueError, TypeError) as fejl:
            raise ValideringsFejl("Gentagelsen kan ikke forstås.") from fejl


def valider_kalender(kalender: Kalender) -> None:
    if not kalender.navn.strip():
        raise ValideringsFejl("Giv kalenderen et navn.")
    if len(kalender.navn.strip()) > kl.MAKS_KALENDERNAVN:
        raise ValideringsFejl(f"Navnet må højst være {kl.MAKS_KALENDERNAVN} tegn.")
    farve = kalender.farve or ""
    if len(farve) != 7 or not farve.startswith("#") \
            or any(c not in "0123456789abcdefABCDEF" for c in farve[1:]):
        raise ValideringsFejl("Vælg en farve.")


class KalenderService:
    def __init__(self, repo: KalenderRepository, alarmlog: JsonLokalFil,
                 aktuel_bruger: Callable[[], Optional[dict]] = lambda: None,
                 visning: Optional[JsonLokalFil] = None):
        self.repo = repo
        self.alarmlog = alarmlog
        self.visning = visning          # fravalgte kalendere pr. bruger
        self._aktuel_bruger = aktuel_bruger
        self._kendte: dict = {}         # id -> Begivenhed fra seneste forekomster()
        self._alarm_cache = None        # (signatur, dato, begivenheder, egne kalender-id'er)

    def har_adgang(self) -> bool:
        return adgang.har_adgang(self._aktuel_bruger(), adgang.KALENDER)

    def _brugernavn(self) -> str:
        return normaliser_brugernavn((self._aktuel_bruger() or {}).get("brugernavn"))

    def er_administrator(self) -> bool:
        return (self._aktuel_bruger() or {}).get("rolle") == "Administrator"

    def kan_administrere(self, kalender: Kalender) -> bool:
        """Slette kalendere og begivenheder: ejeren og administratorer (moderation)."""
        return kalender.er_egen or self.er_administrator()

    ### ----- kalendere ------------------------------------------------------

    def kalendre(self) -> list[Kalender]:
        """Egne og kollegers kalendere. Første gang oprettes "Min kalender" – i en farve,
        ingen anden kalender har."""
        kalendre = self.repo.kalendre()
        if not any(k.er_egen for k in kalendre) and self.har_adgang():
            farve = kl.ledig_farve(k.farve for k in kalendre)
            kalendre = [self.repo.opret_kalender(Kalender(kl.STANDARD_KALENDER, farve)), *kalendre]
        return kalendre

    def gem_kalender(self, kalender: Kalender) -> Kalender:
        kalender = Kalender(kalender.navn.strip(), kalender.farve, kalender.ejer, kalender.id,
                            kalender.version)
        valider_kalender(kalender)
        if not kalender.version:
            return self.repo.opret_kalender(kalender)
        return self.repo.opdater_kalender(kalender.id, kalender.version,
                                          {"navn": kalender.navn, "farve": kalender.farve})

    def slet_kalender(self, kalender: Kalender) -> None:
        if not self.kan_administrere(kalender):
            raise ValideringsFejl("Kun ejeren eller en administrator kan slette kalenderen.")
        self.repo.slet_kalender(kalender.id)

    ### ----- fravalgte kalendere (pr. bruger på denne pc) -------------------

    def skjulte(self) -> set[str]:
        """Id'erne på de kalendere, brugeren har slået fra (alle er slået til fra start)."""
        if self.visning is None:
            return set()
        return set(self.visning.hent().get(self._brugernavn(), {}).get("skjulte", []))

    def gem_skjulte(self, skjulte: set[str]) -> None:
        if self.visning is None or not self._brugernavn():
            return
        data = self.visning.hent()
        data[self._brugernavn()] = {"skjulte": sorted(skjulte)}
        self.visning.gem(data)

    ### ----- begivenheder ---------------------------------------------------

    def forekomster(self, fra: datetime, til: datetime) -> list[Forekomst]:
        begivenheder = self.repo.begivenheder(fra, til)
        self._kendte = {b.id: b for b in begivenheder}
        return kl.forekomster(begivenheder, fra, til)

    def serie_for(self, forekomst: Forekomst) -> Begivenhed:
        """Serien, en forekomst hører til (en enkelt begivenhed er sin egen)."""
        if not forekomst.begivenhed.gentagelse_af:
            return forekomst.begivenhed
        serie = self._kendte.get(forekomst.serie_id)
        if serie is None:
            raise KonfliktFejl("Serien er ændret et andet sted. Kalenderen hentes igen.")
        return serie

    def _rettede(self, serie: Begivenhed, fra: Optional[datetime] = None) -> list[Begivenhed]:
        return [b for b in self._kendte.values() if b.gentagelse_af == serie.id
                and (fra is None or b.oprindelig_start >= fra)]

    def gem(self, begivenhed: Begivenhed) -> Begivenhed:
        """Ny begivenhed eller en ændring af en hel begivenhed/serie (id og version)."""
        begivenhed = normaliser(begivenhed)
        valider(begivenhed)
        if not begivenhed.version:
            return self.repo.opret(begivenhed)
        return self.repo.opdater(begivenhed)

    def gem_forekomst(self, forekomst: Forekomst, ny: Begivenhed, omfang: str) -> None:
        """ny: forekomstens nye data (fra dialogen). omfang bruges kun for serier."""
        ny = normaliser(ny)
        valider(ny)
        if not forekomst.i_serie:
            self.repo.opdater(ny)
            return
        serie = self.serie_for(forekomst)
        if omfang == kl.KUN_DENNE:
            if forekomst.begivenhed.gentagelse_af:      # allerede rettet – ret den igen
                self.repo.opdater(ny.kopi(gentagelse="", undtagelser=[]))
            else:
                self.repo.opret(ny.kopi(id="", version=0, gentagelse="", undtagelser=[],
                                        kalender_id=serie.kalender_id, gentagelse_af=serie.id,
                                        oprindelig_start=forekomst.oprindelig_start, ical_uid=""))
            return
        if omfang == kl.FREMTIDIGE and forekomst.oprindelig_start > serie.start:
            self._del_serie(serie, forekomst, ny)
            return
        # Hele serien: forskydningen (fra forekomstens plads i serien) flytter alle forekomster.
        forskydning = ny.start - forekomst.oprindelig_start
        if forskydning:
            for rettet in self._rettede(serie):     # passer ikke længere ind i serien
                self.repo.slet(rettet.id)
        gentagelse = ny.gentagelse if ny.gentagelse != serie.gentagelse \
            else kl.normaliser_rrule(serie.gentagelse)
        self.repo.opdater(ny.kopi(
            id=serie.id, version=serie.version, kalender_id=serie.kalender_id,
            start=serie.start + forskydning, slut=serie.start + forskydning + ny.varighed,
            gentagelse=gentagelse,
            undtagelser=[t + forskydning for t in serie.undtagelser] if gentagelse else []))

    def _del_serie(self, serie: Begivenhed, forekomst: Forekomst, ny: Begivenhed) -> None:
        """Denne og fremtidige: serien slutter før forekomsten; en ny serie starter ved den."""
        skillelinje = forekomst.oprindelig_start
        gentagelse = kl.resterende_rrule(serie, skillelinje) \
            if ny.gentagelse in (serie.gentagelse, kl.normaliser_rrule(serie.gentagelse)) \
            else ny.gentagelse
        self._afkort(serie, skillelinje)
        forskydning = ny.start - skillelinje
        self.repo.opret(ny.kopi(
            id="", version=0, gentagelse=gentagelse, gentagelse_af="", oprindelig_start=None,
            ical_uid="", undtagelser=[t + forskydning for t in serie.undtagelser if t >= skillelinje]
            if gentagelse else []))

    def _afkort(self, serie: Begivenhed, skillelinje: datetime) -> None:
        for rettet in self._rettede(serie, skillelinje):
            self.repo.slet(rettet.id)
        self.repo.opdater(serie.kopi(
            gentagelse=kl.afkort_serie(serie, skillelinje),
            undtagelser=[t for t in serie.undtagelser if t < skillelinje]))

    def slet_forekomst(self, forekomst: Forekomst, omfang: str) -> None:
        if not forekomst.i_serie:
            self.repo.slet(forekomst.begivenhed.id)
            return
        serie = self.serie_for(forekomst)
        if omfang == kl.FREMTIDIGE and forekomst.oprindelig_start <= serie.start:
            omfang = kl.HELE_SERIEN
        if omfang == kl.HELE_SERIEN:
            self.repo.slet(serie.id)            # rettede forekomster slettes med serien
        elif omfang == kl.FREMTIDIGE:
            self._afkort(serie, forekomst.oprindelig_start)
        else:
            if forekomst.begivenhed.gentagelse_af:
                self.repo.slet(forekomst.begivenhed.id)
            self.repo.opdater(serie.kopi(
                undtagelser=sorted({*serie.undtagelser, forekomst.oprindelig_start})))

    ### ----- import ---------------------------------------------------------

    def importer(self, valg: list[tuple[ImportKilde, str]],
                 graense: Optional[datetime] = None) -> ImportResultat:
        """valg: [(kilde, kalender_id)] – kalender_id "" opretter en kalender med kildens navn.
        graense: begivenheder, der sluttede før, springes over (None = alle)."""
        resultat = ImportResultat()
        farver = len(self.repo.kalendre())
        for kilde, kalender_id in valg:
            if not kalender_id:
                ny = self.repo.opret_kalender(
                    Kalender(kilde.navn.strip()[:kl.MAKS_KALENDERNAVN] or "Importeret",
                             kl.FARVER[farver % len(kl.FARVER)]))
                kalender_id, farver = ny.id, farver + 1
                resultat.nye_kalendere += 1
            begivenheder = [normaliser(b.kopi(kalender_id=kalender_id)) for b in kilde.begivenheder
                            if not er_for_gammel(b, graense)]
            resultat.sprunget_over += kilde.sprunget_over + len(kilde.begivenheder) \
                - len(begivenheder)
            oprettet = self.repo.importer(kalender_id, begivenheder)
            resultat.importeret += oprettet
            resultat.dubletter += len(begivenheder) - oprettet
        log.info("Kalenderimport: %s", resultat)
        return resultat

    ### ----- påmindelser (minut-tjekket) -------------------------------------

    def tjek(self, nu: datetime, signatur: tuple | None = None) -> tuple[tuple, list[Forekomst]]:
        """(signatur, påmindelser der skal vises nu). Kører i baggrunden hvert minut;
        henter kun igen, når signaturen eller datoen har ændret sig. Påmindelser gælder
        kun egne kalendere (ikke kollegers). signatur: allerede kendt (minut-tjekket
        får den med i ét samlet kald) – ellers hentes den."""
        if signatur is None:
            signatur = self.repo.signatur()
        cache = self._alarm_cache
        if cache is None or cache[0] != signatur or cache[1] != nu.date():
            fra = kl.dagens_start(nu.date())
            cache = (signatur, nu.date(),
                     self.repo.begivenheder(fra - timedelta(days=1), fra + _ALARM_VINDUE),
                     {k.id for k in self.repo.kalendre() if k.er_egen})
            self._alarm_cache = cache
        fra = kl.dagens_start(nu.date())
        aktuelle = [f for f in kl.forekomster(cache[2], fra - timedelta(days=1), fra + _ALARM_VINDUE)
                    if f.begivenhed.kalender_id in cache[3]
                    and f.begivenhed.paamindelse is not None
                    and f.start - timedelta(minutes=f.begivenhed.paamindelse) <= nu
                    < f.start + ALARM_SENEST]
        return signatur, self._ikke_vist(aktuelle, nu)

    def _ikke_vist(self, forekomster: list[Forekomst], nu: datetime) -> list[Forekomst]:
        bruger = (self._aktuel_bruger() or {}).get("brugernavn", "")
        if not forekomster or not bruger:
            return []
        data = self.alarmlog.hent()
        vist = {noegle: tid for noegle, tid in data.get(bruger, {}).items()
                if tid >= (nu - timedelta(days=2)).isoformat()}
        nye = [f for f in forekomster if f.noegle not in vist]
        if nye:
            vist.update({f.noegle: nu.isoformat(timespec="seconds") for f in nye})
            data[bruger] = vist
            self.alarmlog.gem(data)
        return nye

    def glem_cache(self) -> None:
        """Efter log ud: intet fra den forrige bruger må hænge ved."""
        self._kendte = {}
        self._alarm_cache = None
