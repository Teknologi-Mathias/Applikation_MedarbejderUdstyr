"""Kalender: kalendere, begivenheder, gentagelser og forekomster.

Tider er lokal dansk tid uden tidszone (datetime uden tzinfo), som i resten
af IN-BASE. Gentagelser udfoldes i lokal tid, så et ugentligt møde kl. 9
bliver liggende kl. 9 hen over skiftet til og fra sommertid.

En begivenhed gemmes én gang; en gentaget begivenhed (serie) har en RRULE
(RFC 5545, uden "RRULE:") og evt. undtagelser (slettede forekomster). En
rettet enkelt forekomst er en selvstændig begivenhed med gentagelse_af (seriens
id) og oprindelig_start (den forekomst, den erstatter).

Heldagsbegivenheder starter kl. 00:00 og slutter kl. 00:00 dagen efter sidste
dag (eksklusiv slutdato som i iCalendar).

Deling (migrering 021): en kalender deles med personer på et af tre niveauer
(NIVEAUER). Brugerens adgang til en kalender er EJER, SKRIVE, ADMIN_ADGANG
(administratorer ser alt), LAESE eller FREEBUSY. Ved FREEBUSY og ved private
begivenheder i andres kalendere sender lagringen kun "Optaget" (maskeret=True).
Rettighederne håndhæves af databasen.
"""
import re
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

TIDSZONE = ZoneInfo("Europe/Copenhagen")

MAKS_TITEL = 200
MAKS_STED = 500
MAKS_TEKST = 10_000
MAKS_KALENDERNAVN = 80
MAKS_PAAMINDELSE = 28 * 24 * 60     # minutter (4 uger)
STANDARD_KALENDER = "Min kalender"

# Kalenderfarver (gemmes som hex; ens i begge temaer).
FARVER = ("#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#8B5CF6",
          "#64748B")

# Påmindelse -> tekst (None = ingen).
PAAMINDELSER = (
    (None, "Ingen påmindelse"), (0, "Når den starter"), (5, "5 minutter før"),
    (15, "15 minutter før"), (30, "30 minutter før"), (60, "1 time før"),
    (24 * 60, "1 dag før"),
)

# Adgang til en kalender (som i databasen, migrering 021).
EJER, SKRIVE, ADMIN_ADGANG, LAESE, FREEBUSY = "owner", "write", "admin", "read", "freebusy"
# Delingsniveauer -> tekst (i stigende rækkefølge).
NIVEAUER = ((FREEBUSY, "Kun ledig/optaget"), (LAESE, "Se alle detaljer"), (SKRIVE, "Redigere"))
MASKERET_TITEL = "Optaget"

# Omfang ved ændring/sletning af en forekomst i en serie.
KUN_DENNE = "kun_denne"
FREMTIDIGE = "fremtidige"
HELE_SERIEN = "hele_serien"

# Gentagelsesvalg i brugerfladen.
INGEN, DAGLIG, HVERDAGE, UGENTLIG, MAANEDLIG, AARLIG = (
    "", "DAILY", "HVERDAGE", "WEEKLY", "MONTHLY", "YEARLY")
FREKVENSER = (
    (INGEN, "Gentages ikke"), (DAGLIG, "Dagligt"), (HVERDAGE, "Alle hverdage"),
    (UGENTLIG, "Ugentligt"), (MAANEDLIG, "Månedligt"), (AARLIG, "Årligt"),
)
UGEDAGE_RRULE = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_UGEDAGE_TEKST = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
_ENHED = {DAGLIG: ("dag", "dage"), UGENTLIG: ("uge", "uger"),
          MAANEDLIG: ("måned", "måneder"), AARLIG: ("år", "år")}


@dataclass
class Deling:
    brugernavn: str
    navn: str
    niveau: str                     # FREEBUSY, LAESE eller SKRIVE


@dataclass
class Kalender:
    navn: str
    farve: str = FARVER[0]
    ejer: str = ""                  # brugernavn – sættes af lagringen ud fra login
    id: str = ""
    version: int = 0
    adgang: str = EJER              # den aktuelle brugers adgang (fra lagringen)
    ejer_navn: str = ""
    delinger: list = field(default_factory=list)   # kun for ejer og administratorer

    @property
    def er_egen(self) -> bool:
        return self.adgang == EJER

    @property
    def kan_skrive(self) -> bool:
        return self.adgang in (EJER, SKRIVE)

    @property
    def er_delt_med_mig(self) -> bool:
        return self.adgang in (SKRIVE, LAESE, FREEBUSY)


@dataclass
class Begivenhed:
    kalender_id: str
    titel: str
    start: datetime
    slut: datetime
    heldag: bool = False
    sted: str = ""
    beskrivelse: str = ""
    privat: bool = False
    paamindelse: Optional[int] = None   # minutter før start
    gentagelse: str = ""                # RRULE, fx "FREQ=WEEKLY;BYDAY=MO"
    undtagelser: list = field(default_factory=list)   # slettede forekomsters start
    gentagelse_af: str = ""             # seriens id (rettet forekomst)
    oprindelig_start: Optional[datetime] = None
    ical_uid: str = ""                  # fra import (undgår dubletter)
    oprettet_af: str = ""
    id: str = ""
    version: int = 0
    maskeret: bool = False              # kun "Optaget" (sat af lagringen)

    @property
    def varighed(self) -> timedelta:
        return self.slut - self.start

    @property
    def gentages(self) -> bool:
        return bool(self.gentagelse)

    def kopi(self, **aendringer) -> "Begivenhed":
        aendringer.setdefault("undtagelser", list(self.undtagelser))
        return replace(self, **aendringer)

    def til_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class Forekomst:
    """Én gang, en begivenhed finder sted (en serie har mange)."""
    begivenhed: Begivenhed
    start: datetime
    slut: datetime

    @property
    def heldag(self) -> bool:
        return self.begivenhed.heldag

    @property
    def titel(self) -> str:
        return self.begivenhed.titel

    @property
    def serie_id(self) -> str:
        return self.begivenhed.gentagelse_af or self.begivenhed.id

    @property
    def i_serie(self) -> bool:
        return self.begivenhed.gentages or bool(self.begivenhed.gentagelse_af)

    @property
    def oprindelig_start(self) -> datetime:
        """Forekomstens plads i serien (til undtagelser og rettede forekomster)."""
        return self.begivenhed.oprindelig_start or self.start

    @property
    def noegle(self) -> str:
        """Entydig pr. forekomst (bruges til ikke at give samme påmindelse to gange)."""
        return f"{self.begivenhed.id}@{self.start.isoformat(timespec='minutes')}"


def skal_maskeres(begivenhed: Begivenhed, adgang: str) -> bool:
    """Ledig/optaget – eller en privat begivenhed i en andens kalender."""
    return adgang == FREEBUSY or (begivenhed.privat and adgang != EJER)


def masker(begivenhed: Begivenhed) -> Begivenhed:
    """Kun tidspunktet: titlen er "Optaget", detaljerne fjernes."""
    return begivenhed.kopi(titel=MASKERET_TITEL, sted="", beskrivelse="", paamindelse=None,
                           ical_uid="", oprettet_af="", maskeret=True)


### ----- tid --------------------------------------------------------------

def lokal(tid: datetime) -> datetime:
    """Tid med tidszone -> lokal dansk tid uden tidszone (uden tidszone: uændret)."""
    if tid.tzinfo is None:
        return tid
    return tid.astimezone(TIDSZONE).replace(tzinfo=None)


def dagens_start(dag: date) -> datetime:
    return datetime.combine(dag, time())


def uge_start(dag: date) -> date:
    return dag - timedelta(days=dag.weekday())


### ----- gentagelser ------------------------------------------------------

_UNTIL = re.compile(r"UNTIL=([0-9T]+Z?)", re.IGNORECASE)


def normaliser_rrule(rrule: str) -> str:
    """RRULE med UNTIL i UTC ("…Z") -> UNTIL i lokal tid uden tidszone.

    dateutil kræver, at UNTIL og seriens start begge har (eller ikke har) tidszone;
    domænet bruger lokal tid uden tidszone."""
    tekst = (rrule or "").strip().removeprefix("RRULE:")

    def lokal_until(fund: re.Match) -> str:
        vaerdi = fund.group(1).upper()
        if not vaerdi.endswith("Z"):
            return f"UNTIL={vaerdi}"
        utc = datetime.strptime(vaerdi, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
        return f"UNTIL={lokal(utc).strftime('%Y%m%dT%H%M%S')}"

    return _UNTIL.sub(lokal_until, tekst)


def _regel(begivenhed: Begivenhed):
    return rrulestr(normaliser_rrule(begivenhed.gentagelse), dtstart=begivenhed.start)


def serie_slut(begivenhed: Begivenhed) -> Optional[datetime]:
    """Hvornår den sidste forekomst slutter (None = gentages uendeligt)."""
    if not begivenhed.gentages:
        return begivenhed.slut
    regel = _regel(begivenhed)
    if regel._until is None and regel._count is None:   # dateutil har ingen offentlig getter
        return None
    sidste = None
    for sidste in regel:
        pass
    return (sidste or begivenhed.start) + begivenhed.varighed


def forekomster(begivenheder: list, fra: datetime, til: datetime) -> list:
    """Alle forekomster, der overlapper [fra, til), sorteret efter start.

    Serier udfoldes; undtagelser og forekomster, der er rettet (en begivenhed med
    gentagelse_af), springes over i serien – den rettede vises i stedet."""
    rettede = {(b.gentagelse_af, b.oprindelig_start) for b in begivenheder if b.gentagelse_af}
    resultat = []
    for b in begivenheder:
        if not b.gentages:
            if _overlapper(b.start, b.slut, fra, til):
                resultat.append(Forekomst(b, b.start, b.slut))
            continue
        varighed = b.varighed
        undtagne = set(b.undtagelser)
        for start in _regel(b).between(fra - varighed, til, inc=True):
            if start in undtagne or (b.id, start) in rettede:
                continue
            if _overlapper(start, start + varighed, fra, til):
                resultat.append(Forekomst(b, start, start + varighed))
    return sorted(resultat, key=lambda f: (f.start, f.slut - f.start, f.titel))


def _overlapper(start, slut, fra, til) -> bool:
    return start < til and (slut > fra or (slut == start and start >= fra))


def afkort_serie(serie: Begivenhed, foer: datetime) -> str:
    """Seriens RRULE, så den slutter dagen før forekomsten 'foer' ("denne og fremtidige").

    UNTIL sættes til kl. 23:59:59 dagen før, så valget "slut på dato" i dialogen viser og
    gemmer præcis samme regel (serierne har højst én forekomst pr. dag)."""
    dele = [d for d in normaliser_rrule(serie.gentagelse).split(";")
            if d and not d.upper().startswith(("UNTIL=", "COUNT="))]
    until = dagens_start(foer.date()) - timedelta(seconds=1)
    return ";".join(dele + [f"UNTIL={until.strftime('%Y%m%dT%H%M%S')}"])


def resterende_rrule(serie: Begivenhed, fra: datetime) -> str:
    """RRULE til den nye serie fra forekomsten 'fra': et COUNT tælles ned."""
    regel = _regel(serie)
    if regel._count is None:
        return normaliser_rrule(serie.gentagelse)
    foer = sum(1 for start in regel if start < fra)
    dele = [d for d in normaliser_rrule(serie.gentagelse).split(";")
            if d and not d.upper().startswith("COUNT=")]
    return ";".join(dele + [f"COUNT={max(1, regel._count - foer)}"])


@dataclass
class Gentagelse:
    """Gentagelsesvalget i brugerfladen <-> RRULE. raa: en RRULE, valgene ikke kan vise
    (fx fra en import) – den bevares uændret."""
    frekvens: str = INGEN
    interval: int = 1
    ugedage: tuple = ()             # 0 = mandag (kun ugentligt)
    antal: Optional[int] = None     # slut efter N gange
    til: Optional[date] = None      # slut på dato (inklusiv)
    raa: str = ""

    def til_rrule(self) -> str:
        if self.raa:
            return self.raa
        if self.frekvens == INGEN:
            return ""
        if self.frekvens == HVERDAGE:
            dele = ["FREQ=WEEKLY", "BYDAY=MO,TU,WE,TH,FR"]
        else:
            dele = [f"FREQ={self.frekvens}"]
            if self.interval > 1:
                dele.append(f"INTERVAL={self.interval}")
            if self.frekvens == UGENTLIG and self.ugedage:
                dele.append("BYDAY=" + ",".join(UGEDAGE_RRULE[d] for d in sorted(self.ugedage)))
        if self.antal:
            dele.append(f"COUNT={self.antal}")
        elif self.til:
            dele.append(f"UNTIL={self.til.strftime('%Y%m%d')}T235959")
        return ";".join(dele)


def fra_rrule(rrule: str) -> Gentagelse:
    """RRULE -> valgene i brugerfladen (raa, hvis den ikke kan vises med valgene)."""
    tekst = normaliser_rrule(rrule)
    if not tekst:
        return Gentagelse()
    dele = dict(d.split("=", 1) for d in tekst.upper().split(";") if "=" in d)
    kendte = {"FREQ", "INTERVAL", "BYDAY", "COUNT", "UNTIL", "WKST"}
    frekvens = dele.get("FREQ", "")
    ugedage = tuple(UGEDAGE_RRULE.index(d) for d in dele.get("BYDAY", "").split(",")
                    if d in UGEDAGE_RRULE)
    if set(dele) - kendte or frekvens not in (DAGLIG, UGENTLIG, MAANEDLIG, AARLIG) \
            or ("BYDAY" in dele and (frekvens != UGENTLIG
                                     or len(ugedage) != len(dele["BYDAY"].split(",")))):
        return Gentagelse(raa=tekst)
    try:
        interval = int(dele.get("INTERVAL", "1"))
        antal = int(dele["COUNT"]) if "COUNT" in dele else None
        til = datetime.strptime(dele["UNTIL"][:8], "%Y%m%d").date() if "UNTIL" in dele else None
    except ValueError:
        return Gentagelse(raa=tekst)
    if frekvens == UGENTLIG and interval == 1 and ugedage == (0, 1, 2, 3, 4):
        return Gentagelse(HVERDAGE, antal=antal, til=til)
    return Gentagelse(frekvens, interval, ugedage, antal, til)


def beskriv_gentagelse(rrule: str, start: datetime) -> str:
    """Dansk tekst, fx "Hver 2. uge mandag og onsdag, 10 gange"."""
    valg = fra_rrule(rrule)
    if valg.raa:
        return "Gentages (tilpasset)"
    if valg.frekvens == INGEN:
        return ""
    if valg.frekvens == HVERDAGE:
        tekst = "Alle hverdage"
    else:
        ental, flertal = _ENHED[valg.frekvens]
        tekst = {DAGLIG: "Dagligt", UGENTLIG: "Ugentligt", MAANEDLIG: "Månedligt",
                 AARLIG: "Årligt"}[valg.frekvens] if valg.interval == 1 \
            else f"Hver {valg.interval}. {ental if valg.frekvens != AARLIG else flertal}"
        if valg.frekvens == UGENTLIG:
            dage = valg.ugedage or (start.weekday(),)
            navne = [_UGEDAGE_TEKST[d] for d in sorted(dage)]
            tekst += " " + (" og ".join(navne) if len(navne) <= 2
                            else ", ".join(navne[:-1]) + " og " + navne[-1])
        elif valg.frekvens == MAANEDLIG:
            tekst += f" den {start.day}."
    if valg.antal:
        tekst += f", {valg.antal} gange"
    elif valg.til:
        tekst += f", til {valg.til.strftime('%d-%m-%Y')}"
    return tekst


### ----- visning ----------------------------------------------------------

def placer_i_kolonner(forekomster_paa_dagen: list) -> list:
    """Overlappende forekomster side om side: [(forekomst, kolonne, antal_kolonner)].

    Forekomster, der hænger sammen gennem overlap, deler bredden ligeligt; hver lægges i
    den første kolonne, der er ledig ved dens start."""
    resultat, gruppe, kolonner, gruppe_slut = [], [], [], None

    def afslut_gruppe():
        resultat.extend((f, k, len(kolonner)) for f, k in gruppe)

    for f in sorted(forekomster_paa_dagen, key=lambda f: (f.start, -(f.slut - f.start).total_seconds())):
        slut = max(f.slut, f.start + timedelta(minutes=15))   # korte begivenheder fylder lidt
        if gruppe_slut is not None and f.start >= gruppe_slut:
            afslut_gruppe()
            gruppe, kolonner, gruppe_slut = [], [], None
        kolonne = next((i for i, ledig_fra in enumerate(kolonner) if ledig_fra <= f.start), None)
        if kolonne is None:
            kolonner.append(slut)
            kolonne = len(kolonner) - 1
        else:
            kolonner[kolonne] = slut
        gruppe.append((f, kolonne))
        gruppe_slut = slut if gruppe_slut is None else max(gruppe_slut, slut)
    afslut_gruppe()
    return resultat
