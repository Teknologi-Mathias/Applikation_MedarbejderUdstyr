"""Import af .ics-filer (fx Google Kalender-eksporten) til Kalender.

Google Takeout giver en .zip med én .ics-fil pr. kalender; begge dele kan
læses. Hver fil bliver en ImportKilde med kalenderens navn (X-WR-CALNAME eller
filnavnet) og dens begivenheder som domæneobjekter (uden kalender_id – det
vælges ved importen).

Tidspunkter med tidszone omregnes til lokal dansk tid; datoer (uden klokkeslæt)
bliver heldagsbegivenheder. Aflyste begivenheder (STATUS:CANCELLED) springes
over. Selve gemningen (dubletkontrol via UID) sker i KalenderService/lagringen.
"""
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from app.domain import kalender as kl
from app.domain.kalender import Begivenhed
from app.repositories.fejl import ValideringsFejl

log = logging.getLogger(__name__)

MAKS_FILSTOERRELSE = 50 * 1024 * 1024


@dataclass
class ImportKilde:
    navn: str
    begivenheder: list = field(default_factory=list)
    sprunget_over: int = 0          # aflyste eller ulæselige begivenheder


def laes_filer(stier: list) -> list[ImportKilde]:
    """.ics- og .zip-filer -> én ImportKilde pr. kalender. ValideringsFejl ved ugyldige filer."""
    kilder = []
    for sti in map(Path, stier):
        try:
            if sti.stat().st_size > MAKS_FILSTOERRELSE:
                raise ValideringsFejl(f"{sti.name} er for stor (over 50 MB).")
            if sti.suffix.lower() == ".zip":
                with zipfile.ZipFile(sti) as arkiv:
                    for navn in sorted(n for n in arkiv.namelist() if n.lower().endswith(".ics")):
                        kilder.append(laes_ics(arkiv.read(navn), Path(navn).stem))
            else:
                kilder.append(laes_ics(sti.read_bytes(), sti.stem))
        except (OSError, zipfile.BadZipFile) as fejl:
            raise ValideringsFejl(f"{sti.name} kunne ikke læses ({fejl}).") from fejl
    if not kilder:
        raise ValideringsFejl("Der er ingen kalendere (.ics) i de valgte filer.")
    return kilder


def laes_ics(indhold: bytes, standardnavn: str) -> ImportKilde:
    from icalendar import Calendar

    try:
        kalender = Calendar.from_ical(indhold)
    except ValueError as fejl:
        raise ValideringsFejl(f"{standardnavn} er ikke en gyldig .ics-fil ({fejl}).") from fejl
    kilde = ImportKilde(str(kalender.get("X-WR-CALNAME") or standardnavn).strip()
                        [:kl.MAKS_KALENDERNAVN] or standardnavn)
    for komponent in kalender.walk("VEVENT"):
        try:
            begivenhed = _begivenhed(komponent)
            if begivenhed is not None:
                kl.serie_slut(begivenhed)       # afviser en ugyldig RRULE her
        except (ValueError, TypeError, KeyError) as fejl:
            log.warning("Begivenhed i %s kunne ikke læses: %s", standardnavn, fejl)
            begivenhed = None
        if begivenhed is None:
            kilde.sprunget_over += 1
        else:
            kilde.begivenheder.append(begivenhed)
    return kilde


def _tid(vaerdi) -> tuple[datetime, bool]:
    """DTSTART/DTEND -> (lokal tid, er en dato)."""
    if isinstance(vaerdi, datetime):
        return kl.lokal(vaerdi), False
    if isinstance(vaerdi, date):
        return kl.dagens_start(vaerdi), True
    raise ValueError(f"ukendt tidspunkt: {vaerdi!r}")


def _begivenhed(komponent) -> Begivenhed | None:
    if str(komponent.get("STATUS", "")).upper() == "CANCELLED" or "DTSTART" not in komponent:
        return None
    start, heldag = _tid(komponent.decoded("DTSTART"))
    if "DTEND" in komponent:
        slut, _ = _tid(komponent.decoded("DTEND"))
    elif "DURATION" in komponent:
        slut = start + komponent.decoded("DURATION")
    else:
        slut = start + (timedelta(days=1) if heldag else timedelta())
    slut = max(slut, start)
    if heldag and slut == start:
        slut = start + timedelta(days=1)

    gentagelse = ""
    if "RRULE" in komponent:
        gentagelse = kl.normaliser_rrule(komponent["RRULE"].to_ical().decode())
    undtagelser = []
    exdate = komponent.get("EXDATE")
    for liste in (exdate if isinstance(exdate, list) else [exdate] if exdate else []):
        undtagelser.extend(_tid(d.dt)[0] for d in liste.dts)
    oprindelig = None
    if "RECURRENCE-ID" in komponent:
        oprindelig = _tid(komponent.decoded("RECURRENCE-ID"))[0]
        gentagelse, undtagelser = "", []

    return Begivenhed(
        kalender_id="",
        titel=(str(komponent.get("SUMMARY", "")).strip() or "(uden titel)")[:kl.MAKS_TITEL],
        start=start, slut=slut, heldag=heldag,
        sted=str(komponent.get("LOCATION", "")).strip()[:kl.MAKS_STED],
        beskrivelse=str(komponent.get("DESCRIPTION", "")).strip()[:kl.MAKS_TEKST],
        privat=str(komponent.get("CLASS", "")).upper() in ("PRIVATE", "CONFIDENTIAL"),
        paamindelse=_paamindelse(komponent),
        gentagelse=gentagelse, undtagelser=undtagelser, oprindelig_start=oprindelig,
        ical_uid=str(komponent.get("UID", "")).strip()[:500],
    )


def _paamindelse(komponent) -> int | None:
    """Første VALARM med en relativ TRIGGER før start -> minutter (ellers None)."""
    for alarm in komponent.walk("VALARM"):
        try:
            trigger = alarm.decoded("TRIGGER")
        except (KeyError, ValueError):
            continue
        if isinstance(trigger, timedelta) and trigger <= timedelta():
            return min(int(-trigger.total_seconds() // 60), kl.MAKS_PAAMINDELSE)
    return None


def er_for_gammel(begivenhed: Begivenhed, graense: datetime | None) -> bool:
    """Sluttede begivenheden (eller seriens sidste forekomst) før grænsen?"""
    if graense is None:
        return False
    slut = kl.serie_slut(begivenhed)
    return slut is not None and slut < graense
