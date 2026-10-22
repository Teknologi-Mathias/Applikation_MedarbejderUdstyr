"""Nøgletal for de administrative processer.

Tallene bygger på faktiske hændelser i sagernes tidslinje (strukturerede
statusskift) og opgavernes afslutningstidspunkter – ikke kun på den aktuelle
status. Hvert tal har et n (antal sager/opgaver bag). Uden datagrundlag
(n = 0) vises tallet ikke.

Begrænsning: sager fra før statusskift blev registreret, har ingen i
tidslinjen og indgår derfor kun i tal, der ikke kræver dem (åbne sager,
opgavefrister).
Filtre på stilling og område gælder kun onboarding (offboarding har ikke de
felter).
"""
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.sag import Sag


@dataclass
class Filter:
    fra: Optional[date] = None
    til: Optional[date] = None
    modul: str = ""          # "", "onboarding" eller "offboarding"
    stilling: str = ""
    omraade: str = ""
    ansvarlig: str = ""


@dataclass
class Maaling:
    navn: str
    vaerdi: Optional[str]    # None = ikke nok data
    n: int
    slags: str               # "Gennemsnit / median", "Antal", "Andel"
    forklaring: str = ""


@dataclass
class Rapport:
    maalinger: list = field(default_factory=list)
    arbejdsfordeling: list = field(default_factory=list)   # (ansvarlig, åbne, forsinkede)
    flaskehalse: list = field(default_factory=list)        # (gruppe, antal, gns. dage i status)


def _tid(tekst: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(tekst)
    except (TypeError, ValueError):
        return None


def _dage(fra: Optional[datetime], til: Optional[datetime]) -> Optional[float]:
    if fra is None or til is None or til < fra:
        return None
    return (til - fra).total_seconds() / 86400


def _gns_median(vaerdier: list) -> Optional[str]:
    if not vaerdier:
        return None
    return f"{statistics.mean(vaerdier):.1f} / {statistics.median(vaerdier):.1f} dage"


def foerste_tid_i(sag: Sag, statusser: set) -> Optional[datetime]:
    """Første tidspunkt sagen havde en af statusserne (ud fra tidslinjen)."""
    for h in sag.historik.haendelser():
        data = h.get("data") or {}
        if data.get("type") == "oprettet" and data.get("status") in statusser:
            return _tid(h.get("tid"))
        if data.get("type") == "status" and data.get("til") in statusser:
            return _tid(h.get("tid"))
    return None


def _fra_og_med(status: str) -> set:
    """OB-statusser fra og med status i forløbet (uden Annulleret)."""
    return set(OB.FREMDRIFT[OB.FREMDRIFT.index(status):])


class RapportService:

    def filtrer(self, sager: Iterable[Sag], f: Filter) -> list[Sag]:
        resultat = []
        for sag in sager:
            oprettet = _tid(sag.oprettet)
            if f.modul and sag.PROCES != f.modul:
                continue
            if f.fra and (oprettet is None or oprettet.date() < f.fra):
                continue
            if f.til and (oprettet is None or oprettet.date() > f.til):
                continue
            if (f.stilling or f.omraade) and not isinstance(sag, OB):
                continue
            if f.stilling and sag.stilling != f.stilling:
                continue
            if f.omraade and sag.omraade != f.omraade:
                continue
            if f.ansvarlig and sag.ansvarlig != f.ansvarlig and not any(
                o.ansvarlig == f.ansvarlig for o in sag.opgaver
            ):
                continue
            resultat.append(sag)
        return resultat

    def beregn(self, sager: Iterable[Sag], f: Filter, i_dag: date) -> Rapport:
        sager = self.filtrer(sager, f)
        rapport = Rapport()
        maal = rapport.maalinger

        # --- behandlingstid for afsluttede sager ---
        tider = []
        for sag in sager:
            slut_status = {Medarbejder.STATUS_AFVIKLET} if isinstance(sag, Medarbejder) \
                else {OB.STATUS_AKTIV}
            tider.append(_dage(_tid(sag.oprettet), foerste_tid_i(sag, slut_status)))
        tider = [t for t in tider if t is not None]
        maal.append(Maaling("Sagsbehandlingstid (afsluttede)", _gns_median(tider), len(tider),
                            "Gennemsnit / median",
                            "Fra oprettelse til Afviklet (offboarding) / Aktiv (onboarding)."))

        # --- onboardingens faser ---
        onboarding = [s for s in sager if isinstance(s, OB)]
        faser = (
            ("Kandidat → kontrakt bekræftet", None, OB.STATUS_OPLAERING),
            ("Kontrakt → første oplæring", OB.STATUS_OPLAERING, OB.STATUS_JOBS),
            ("Oplæring → første job", OB.STATUS_JOBS, OB.STATUS_AKTIV),
        )
        for navn, fra_status, til_status in faser:
            vaerdier = []
            for sag in onboarding:
                start = _tid(sag.oprettet) if fra_status is None \
                    else foerste_tid_i(sag, _fra_og_med(fra_status))
                varighed = _dage(start, foerste_tid_i(sag, _fra_og_med(til_status)))
                if varighed is not None:
                    vaerdier.append(varighed)
            maal.append(Maaling(navn, _gns_median(vaerdier), len(vaerdier), "Gennemsnit / median",
                                "Ud fra registrerede statusskift."))

        # --- åbne og forsinkede forløb ---
        aabne = [s for s in sager if not s.arkiveret and not s.er_afsluttet()]
        forsinkede = [s for s in aabne if s.forsinkede_opgaver(i_dag)]
        maal.append(Maaling("Åbne forløb", str(len(aabne)), len(aabne), "Antal"))
        maal.append(Maaling("Forsinkede forløb", str(len(forsinkede)), len(aabne), "Antal",
                            "Åbne forløb med mindst én opgave over frist."))

        # --- andel opgaver over frist ---
        over = total = 0
        for sag in sager:
            for o in sag.opgaver:
                if f.ansvarlig and o.ansvarlig != f.ansvarlig:
                    continue
                frist = o.frist_dato()
                if frist is None:
                    continue
                if o.afsluttet:
                    afsluttet = _tid(o.afsluttet_tid)
                    if afsluttet is None:
                        continue  # afsluttet før tidspunktet blev registreret
                    total += 1
                    over += afsluttet.date() > frist
                elif not sag.er_laast(o):
                    total += 1
                    over += frist < i_dag
        maal.append(Maaling(
            "Opgaver over frist", f"{over / total:.0%}" if total else None, total, "Andel",
            "Afsluttede opgaver udført efter fristen + åbne opgaver over frist.",
        ))

        # --- arbejdsfordeling (åbne opgaver pr. ansvarlig) ---
        fordeling = defaultdict(lambda: [0, 0])
        for sag in aabne:
            for o in sag.aabne_opgaver():
                navn = o.ansvarlig or "(ingen ansvarlig)"
                fordeling[navn][0] += 1
                fordeling[navn][1] += o.er_forsinket(i_dag)
        rapport.arbejdsfordeling = sorted(
            ((navn, a, f_) for navn, (a, f_) in fordeling.items()), key=lambda r: -r[1]
        )

        # --- flaskehalse: åbne onboardingforløb pr. stilling og område ---
        grupper = defaultdict(list)
        for sag in aabne:
            if not isinstance(sag, OB):
                continue
            siden = foerste_tid_i(sag, {sag.status}) or _tid(sag.oprettet)
            dage = _dage(siden, datetime.now())
            for gruppe in (f"Stilling: {sag.stilling or '–'}", f"Område: {sag.omraade or '–'}"):
                grupper[(gruppe, sag.status)].append(dage or 0)
        rapport.flaskehalse = sorted(
            ((f"{g} · {status}", len(d), statistics.mean(d)) for (g, status), d in grupper.items()),
            key=lambda r: -r[2],
        )
        return rapport

    @staticmethod
    def valgmuligheder(sager: Iterable[Sag]) -> dict:
        sager = list(sager)
        return {
            "stillinger": list(OB.STILLINGER),
            "omraader": sorted({s.omraade for s in sager if isinstance(s, OB) and s.omraade}),
            "ansvarlige": sorted({a for s in sager for a in
                                  [s.ansvarlig] + [o.ansvarlig for o in s.opgaver] if a}),
        }
