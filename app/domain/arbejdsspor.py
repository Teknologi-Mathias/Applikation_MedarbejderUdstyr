"""Arbejdsspor: én sag, flere parallelle spor (HR, kontrakt, tøj, telefon …).

Ren beregning ud fra sagens opgaver – intet gemmes. Teamoverblik,
arbejdsbakker, Action Center og rapporter bruger de samme funktioner, så en
status aldrig beregnes forskelligt to steder.

- visningsstatus(): én opgaves status som brugeren ser den (Klar, Blokeret …).
- spor_status():    sammenfatning af et spor med næste handling og ejer.
- klarhed():        er medarbejderen klar til sin første arbejdsdag? Giver kun
                    advarsler – processen stoppes aldrig af en vurdering.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.domain.opgave import Opgave, laes_iso_dato

# Afdelinger, der kan eje opgaver. Brugere kan være medlem af flere (roller).
HR = "HR"
ADMINISTRATION = "Administration"
MERCH = "Merch"
AFDELINGER = (HR, ADMINISTRATION, MERCH)

# Spor i fast visningsrækkefølge: (nøgle, navn). Opgaver uden spor er "oevrigt".
OEVRIGT = "oevrigt"
SPOR = (
    ("hr", "HR"),
    ("kontrakt", "Kontrakt"),
    ("toej", "Arbejdstøj"),
    ("telefon", "Telefon"),
    ("email", "E-mail"),
    ("firmabil", "Firmabil"),
    ("oplaering", "Oplæring"),
    ("opstart", "Opstart"),
    ("opfoelgning", "Opfølgning"),
    (OEVRIGT, "Øvrigt"),
)
SPOR_NAVNE = dict(SPOR)

# Visningsstatus for opgaver og spor.
KLAR = "Klar"
I_GANG = "I gang"
AFVENTER = "Afventer"
BLOKERET = "Blokeret"
FORSINKET = "Forsinket"
FAERDIG = "Færdig"
IKKE_RELEVANT = "Ikke relevant"

FORKLARING = {
    KLAR: "Kan udføres nu",
    I_GANG: "Arbejdet er i gang",
    AFVENTER: "Afventer en ekstern part eller anden handling",
    BLOKERET: "Venter på en forudsætning",
    FORSINKET: "Over fristen",
    FAERDIG: "Udført",
    IKKE_RELEVANT: "Ikke relevant for denne medarbejder",
}

# Klarhed til opstart.
KLAR_TIL_OPSTART = "Klar til opstart"
PAA_PLAN = "På plan"
RISIKO = "Opstart i risiko"
OPSTART_BLOKERET = "Opstart blokeret"
AFSLUTTET = "Afsluttet"


def spor_for(opgave: Opgave) -> str:
    return opgave.spor if opgave.spor in SPOR_NAVNE else OEVRIGT


def ejer(opgave: Opgave) -> str:
    """Den konkrete ansvarlige, ellers afdelingen (ikke tildelt)."""
    if opgave.ansvarlig:
        return opgave.ansvarlig
    return f"{opgave.afdeling} (ikke tildelt)" if opgave.afdeling else "Ikke tildelt"


def visningsstatus(sag, opgave: Opgave, i_dag: date) -> str:
    if opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return FAERDIG
    if sag.er_blokeret(opgave):
        return BLOKERET
    if opgave.er_forsinket(i_dag):
        return FORSINKET
    return {Opgave.I_GANG: I_GANG, Opgave.AFVENTER: AFVENTER}.get(opgave.status, KLAR)


@dataclass
class SporStatus:
    spor: str
    navn: str
    status: str
    naeste: Optional[Opgave]      # den opgave, der bør handles på nu (eller den blokerede)
    tekst: str                    # næste handling eller blokeringsårsag
    ejer: str
    afsluttede: int
    total: int


# Hvilken opgavestatus der bestemmer sporets status (først = vigtigst).
_SPOR_PRIORITET = (FORSINKET, I_GANG, AFVENTER, KLAR, BLOKERET)


def spor_status(sag, spor: str, i_dag: date) -> Optional[SporStatus]:
    """Sammenfatning af ét spor, eller None hvis sagen ikke har opgaver i sporet."""
    opgaver = [o for o in sag.opgaver if spor_for(o) == spor]
    if not opgaver:
        return None
    navn = SPOR_NAVNE.get(spor, spor)
    afsluttede = sum(o.afsluttet for o in opgaver)
    relevante = [o for o in opgaver if o.status != Opgave.UNDTAGET]
    if not relevante:
        return SporStatus(spor, navn, IKKE_RELEVANT, None, "", "", afsluttede, len(opgaver))
    aabne = [o for o in relevante if not o.afsluttet]
    if not aabne:
        return SporStatus(spor, navn, FAERDIG, None, "", "", afsluttede, len(opgaver))
    statusser = {o.id: visningsstatus(sag, o, i_dag) for o in aabne}
    status = next(s for s in _SPOR_PRIORITET if s in statusser.values())
    naeste = next(o for o in aabne if statusser[o.id] == status)
    if status == BLOKERET:
        tekst = sag.blokeringsaarsag(naeste)
    else:
        tekst = naeste.naeste_handling or naeste.navn
    return SporStatus(spor, navn, status, naeste, tekst, ejer(naeste),
                      afsluttede, len(opgaver))


def alle_spor(sag, i_dag: date) -> list[SporStatus]:
    """Sagens spor i fast rækkefølge (kun spor med opgaver)."""
    return [s for s in (spor_status(sag, noegle, i_dag) for noegle, _ in SPOR) if s]


@dataclass
class Klarhed:
    niveau: str
    aarsager: list = field(default_factory=list)
    dage_til_start: Optional[int] = None


def klarhed(sag, i_dag: date, risiko_dage: int = 7) -> Klarhed:
    """Vurdering af opstarten ud fra de relevante, obligatoriske opgaver.

    - Klar til opstart: alle relevante obligatoriske opgaver er udført.
    - Opstart blokeret: starten er inden for risiko_dage, og opgaver venter
      stadig på en forudsætning (typisk kontrakten).
    - Opstart i risiko: forsinkede opgaver, eller starten er inden for
      risiko_dage med åbne opgaver.
    - På plan: ellers.
    Undtagne (ikke relevante) opgaver og opgaver med frist efter startdagen
    (fx opfølgningssamtalen) tæller ikke med.
    """
    start = laes_iso_dato(sag.maaldato())
    dage = (start - i_dag).days if start else None
    if sag.er_afsluttet() and (dage is None or dage < 0 or sag.status_manuel):
        return Klarhed(AFSLUTTET, dage_til_start=dage)
    aabne = [o for o in sag.opgaver if o.obligatorisk and not o.afsluttet
             and not (start and o.frist_dato() and o.frist_dato() > start)]
    if not aabne:
        return Klarhed(KLAR_TIL_OPSTART, dage_til_start=dage)

    blokerede = [o for o in aabne if sag.er_blokeret(o)]
    forsinkede = [o for o in aabne if not sag.er_blokeret(o) and o.er_forsinket(i_dag)]
    taet_paa = dage is not None and dage <= risiko_dage
    aarsager = []
    if forsinkede:
        aarsager.append(f"{len(forsinkede)} forsinket" + ("e opgaver" if len(forsinkede) > 1
                                                            else " opgave"))
    if blokerede and taet_paa:
        aarsager.append(f"{len(blokerede)} venter på en forudsætning")
    if taet_paa:
        aarsager.append(("Starter i dag" if dage == 0 else
                         f"Startede for {-dage} dage siden" if dage < 0 else
                         f"Starter om {dage} {'dag' if dage == 1 else 'dage'}")
                        + f" med {len(aabne)} åbne opgaver")
    if blokerede and taet_paa:
        niveau = OPSTART_BLOKERET
    elif forsinkede or taet_paa:
        niveau = RISIKO
    else:
        niveau = PAA_PLAN
    return Klarhed(niveau, aarsager, dage)
