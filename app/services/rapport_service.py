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

from app.domain import arbejdsspor as sp
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave, laes_iso_dato
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


def _udfoert_tid(sag: Sag, noegle: str) -> Optional[datetime]:
    """Hvornår opgaven med nøglen blev udført (None: ikke udført / ukendt tidspunkt)."""
    o = next((o for o in sag.opgaver if o.noegle == noegle), None)
    return _tid(o.afsluttet_tid) if o is not None and o.status == Opgave.UDFOERT else None


def _mellem_opgaver(sag: Sag, fra: Optional[str], til: tuple) -> Optional[float]:
    """Dage fra opgaven fra blev udført (fra=None: fra oprettelsen), til alle relevante
    til-opgaver var udført."""
    relevante = [o for o in sag.opgaver if o.noegle in til and o.status != Opgave.UNDTAGET]
    if not relevante:
        return None
    slut = [_udfoert_tid(sag, o.noegle) for o in relevante]
    if any(t is None for t in slut):
        return None
    return _dage(_tid(sag.oprettet) if fra is None else _udfoert_tid(sag, fra), max(slut))


def _tidspunkt_til_booket(sag: Sag) -> Optional[float]:
    booket = next((o for o in sag.opgaver if o.noegle == "oplaering_booket"), None)
    if booket is None or booket.status != Opgave.UDFOERT:
        return None
    registreret = next((
        _tid(h.get("tid")) for h in sag.historik.haendelser()
        if h.get("reference") == booket.id and "planlagt tidspunkt" in h.get("kommentar", "")
    ), None)
    if registreret is None and booket.planlagt:
        registreret = _tid(sag.oprettet)    # tidspunktet blev registreret ved oprettelsen
    return _dage(registreret, _tid(booket.afsluttet_tid))


def _klar_paa_dagen(sag, i_dag: date) -> Optional[bool]:
    """Var forløbet klar på første arbejdsdag? None: dagen er ikke passeret / ukendt."""
    start = laes_iso_dato(sag.maaldato())
    if start is None or start >= i_dag or sag.status == OB.STATUS_ANNULLERET:
        return None
    for o in sag.opgaver:
        if not o.obligatorisk or o.status == Opgave.UNDTAGET:
            continue
        if o.frist_dato() and o.frist_dato() > start:
            continue
        udfoert = _tid(o.afsluttet_tid) if o.status == Opgave.UDFOERT else None
        if udfoert is None or udfoert.date() > start:
            return False
    return True


def _blev_forsinket(sag: Sag, o: Opgave, i_dag: date) -> bool:
    frist = o.frist_dato()
    if frist is None or o.status == Opgave.UNDTAGET:
        return False
    if o.afsluttet:
        afsluttet = _tid(o.afsluttet_tid)
        return afsluttet is not None and afsluttet.date() > frist
    return not sag.er_blokeret(o) and frist < i_dag


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

        # --- arbejdsspor: tid mellem opgaver (ud fra opgavernes afslutningstidspunkter) ---
        for navn, fra, til in (
            ("Oprettet → kontrakt retur", None, ("kontrakt",)),
            ("Kontrakt retur → udstyr sendt", "kontrakt", ("udstyr",)),
            ("Kontrakt retur → firmabil bestilt", "kontrakt", ("firmabil",)),
        ):
            vaerdier = [v for v in (_mellem_opgaver(s, fra, til) for s in onboarding)
                        if v is not None]
            maal.append(Maaling(navn, _gns_median(vaerdier), len(vaerdier), "Gennemsnit / median",
                                "Kun forløb, hvor begge opgaver er udført med registreret "
                                "tidspunkt."))
        vaerdier = [v for v in (_tidspunkt_til_booket(s) for s in onboarding) if v is not None]
        maal.append(Maaling("Oplæringstidspunkt → booking bekræftet", _gns_median(vaerdier),
                            len(vaerdier), "Gennemsnit / median",
                            "Fra tidspunktet første gang blev registreret til bookingen blev "
                            "markeret som bekræftet (tidslinjen)."))
        klar = [k for k in (_klar_paa_dagen(s, i_dag) for s in onboarding) if k is not None]
        maal.append(Maaling("Klar på første arbejdsdag", f"{sum(klar) / len(klar):.0%}"
                            if klar else None, len(klar), "Andel",
                            "Forløb med passeret første arbejdsdag, hvor alle relevante "
                            "obligatoriske opgaver med frist senest den dag var udført."))

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
                elif not sag.er_blokeret(o):
                    total += 1
                    over += frist < i_dag
        maal.append(Maaling(
            "Opgaver over frist", f"{over / total:.0%}" if total else None, total, "Andel",
            "Afsluttede opgaver udført efter fristen + åbne opgaver over frist.",
        ))

        # --- ufordelte opgaver og spor, der gentagne gange forsinker ---
        # Afdelingen ejer opgaven – kun opgaver uden både afdeling og person er ufordelte.
        ufordelte = sum(sp.ansvar(o) == sp.IKKE_TILDELT for s in aabne for o in s.aabne_opgaver())
        maal.append(Maaling("Opgaver uden ejer", str(ufordelte), ufordelte, "Antal",
                            "Åbne opgaver, der kan udføres nu, uden både afdeling og person."))
        pr_spor = defaultdict(int)
        for sag in sager:
            for o in sag.opgaver:
                if o.spor and _blev_forsinket(sag, o, i_dag):
                    pr_spor[sp.SPOR_NAVNE.get(o.spor, o.spor)] += 1
        top = sorted(pr_spor.items(), key=lambda r: -r[1])[:3]
        maal.append(Maaling("Spor med flest forsinkelser",
                            ", ".join(f"{n} ({a})" for n, a in top) or None,
                            sum(pr_spor.values()), "Antal",
                            "Opgaver udført efter fristen eller åbne over fristen, pr. spor."))

        # --- arbejdsfordeling (åbne opgaver pr. person, der har taget dem, og pr. afdeling) ---
        fordeling = defaultdict(lambda: [0, 0])
        for sag in aabne:
            for o in sag.aabne_opgaver():
                if not o.ansvarlig:
                    continue
                navn = o.ansvarlig
                fordeling[navn][0] += 1
                fordeling[navn][1] += o.er_forsinket(i_dag)
        rapport.arbejdsfordeling = sorted(
            ((navn, a, f_) for navn, (a, f_) in fordeling.items()), key=lambda r: -r[1]
        )
        # Samme tal pr. ansvarlig afdeling.
        afdelinger = defaultdict(lambda: [0, 0])
        for sag in aabne:
            for o in sag.aabne_opgaver():
                if o.afdeling:
                    afdelinger[o.afdeling][0] += 1
                    afdelinger[o.afdeling][1] += o.er_forsinket(i_dag)
        rapport.arbejdsfordeling += sorted(
            ((f"Afdeling: {navn}", a, f_) for navn, (a, f_) in afdelinger.items()),
            key=lambda r: -r[1])

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
