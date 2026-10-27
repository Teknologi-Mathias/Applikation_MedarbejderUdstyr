"""Arbejdsbakker og teamoverblik: hvem skal gøre hvad – på tværs af sagerne.

Ren logik uden brugerflade, bygget på app/domain/arbejdsspor.py, så
Teamoverblikket, arbejdsbakkerne og nøgletallene bruger samme statusser,
afhængigheder og klarhedsvurdering. Intet gemmes – alt beregnes ud fra
sagernes aktuelle tilstand.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from app.domain import arbejdsspor as sp
from app.domain.opgave import Opgave, laes_iso_dato

# ----- arbejdsbakkens visninger (opgaver) -----------------------------------

MINE = "mine"
MIN_AFDELING = "afdeling"
IKKE_TILDELT = "ikke_tildelt"
AFVENTER_ANDRE = "afventer"
FORSINKEDE = "forsinkede"
NYLIGT_AFSLUTTET = "afsluttet"
VISNINGER = (
    (MINE, "Mine opgaver"),
    (MIN_AFDELING, "Min afdeling"),
    (IKKE_TILDELT, "Ikke tildelte"),
    (AFVENTER_ANDRE, "Afventer andre"),
    (FORSINKEDE, "Forsinkede"),
    (NYLIGT_AFSLUTTET, "Nyligt afsluttet"),
)
NYLIG_DAGE = 14


@dataclass
class Post:
    sag: object
    opgave: Opgave
    status: str          # visningsstatus (arbejdsspor)
    aarsag: str          # blokeringsårsag (tom, hvis opgaven kan udføres)

    @property
    def blokeret(self) -> bool:
        return self.status == sp.BLOKERET


def _min(opgave: Opgave, brugernavn: str) -> bool:
    return bool(brugernavn) and opgave.ansvarlig.lower() == brugernavn.lower()


def _afsluttet_for(opgave: Opgave, i_dag: date) -> int | None:
    try:
        return (i_dag - datetime.fromisoformat(opgave.afsluttet_tid).date()).days
    except ValueError:
        return None


def poster(sager: Iterable, visning: str, i_dag: date, brugernavn: str = "",
           afdelinger: Iterable[str] = ()) -> list[Post]:
    """Opgaverne i én visning. Blokerede opgaver er med (adskilles i brugerfladen)."""
    afdelinger = set(afdelinger)
    resultat = []
    for sag in sager:
        if sag.arkiveret:
            continue
        for o in sag.opgaver:
            status = sp.visningsstatus(sag, o, i_dag)
            if visning == NYLIGT_AFSLUTTET:
                dage = _afsluttet_for(o, i_dag) if o.status == Opgave.UDFOERT else None
                med = dage is not None and dage <= NYLIG_DAGE
            elif o.afsluttet:
                med = False
            elif visning == MINE:
                med = _min(o, brugernavn)
            elif visning == MIN_AFDELING:
                med = o.afdeling in afdelinger
            elif visning == IKKE_TILDELT:
                med = not o.ansvarlig
            elif visning == AFVENTER_ANDRE:
                med = o.status == Opgave.AFVENTER
            elif visning == FORSINKEDE:
                # Også blokerede: blokeringen fjerner ikke tidsrisikoen.
                med = o.er_forsinket(i_dag)
            else:
                med = True
            if med:
                resultat.append(Post(sag, o, status, sag.blokeringsaarsag(o)))
    if visning == NYLIGT_AFSLUTTET:
        resultat.sort(key=lambda p: p.opgave.afsluttet_tid, reverse=True)
    else:
        resultat.sort(key=lambda p: (p.blokeret, p.opgave.frist or "9999", p.sag.navn))
    return resultat


# ----- teamoverblik (sager) ---------------------------------------------------

ALLE = "alle"
SAG_MIN_AFDELING = "min_afdeling"
SAG_MINE = "mine"
UDEN_ANSVARLIG = "uden_ansvarlig"
SAG_FORSINKEDE = "forsinkede"
BLOKEREDE = "blokerede"
RISIKO = "risiko"
KOMMENDE = "kommende"
MANGLER_BEKRAEFTELSE = "mangler_bekraeftelse"
KLAR_TIL_AFSLUTNING = "klar_til_afslutning"
TEAM_FILTRE = (
    (ALLE, "Alle aktive forløb"),
    (SAG_MIN_AFDELING, "Min afdeling"),
    (SAG_MINE, "Mine opgaver"),
    (UDEN_ANSVARLIG, "Opgaver uden ansvarlig"),
    (SAG_FORSINKEDE, "Forsinkede opgaver"),
    (BLOKEREDE, "Blokerede forløb"),
    (RISIKO, "Opstart i risiko"),
    (KOMMENDE, "Kommende arbejdsstarter"),
    (MANGLER_BEKRAEFTELSE, "Mangler bekræftelse"),
    (KLAR_TIL_AFSLUTNING, "Klar til afslutning"),
)


def _aabne(sag) -> list:
    return [o for o in sag.opgaver if not o.afsluttet]


def sag_matcher(sag, filter_: str, i_dag: date, brugernavn: str = "",
                afdelinger: Iterable[str] = (), risiko_dage: int = 7) -> bool:
    """Hører sagen med i teamoverblikkets filter?"""
    if sag.arkiveret:
        return False
    afsluttet = sag.er_afsluttet()
    if filter_ == KLAR_TIL_AFSLUTNING:
        return afsluttet
    if afsluttet:
        return filter_ == ALLE
    aabne = _aabne(sag)
    if filter_ == SAG_MIN_AFDELING:
        return any(o.afdeling in set(afdelinger) for o in aabne)
    if filter_ == SAG_MINE:
        return any(_min(o, brugernavn) for o in aabne)
    if filter_ == UDEN_ANSVARLIG:
        return any(not o.ansvarlig and not sag.er_blokeret(o) for o in aabne)
    if filter_ == SAG_FORSINKEDE:
        return any(o.er_forsinket(i_dag) for o in aabne)
    if filter_ == MANGLER_BEKRAEFTELSE:
        return any(o.status == Opgave.AFVENTER for o in aabne)
    if filter_ in (BLOKEREDE, RISIKO):
        niveau = sp.klarhed(sag, i_dag, risiko_dage).niveau
        return niveau == sp.OPSTART_BLOKERET if filter_ == BLOKEREDE else \
            niveau in (sp.RISIKO, sp.OPSTART_BLOKERET)
    if filter_ == KOMMENDE:
        start = laes_iso_dato(sag.maaldato())
        return start is not None and i_dag <= start <= i_dag + timedelta(days=risiko_dage)
    return True


@dataclass
class Noegletal:
    navn: str
    antal: int
    filter: str          # teamfilteret, der viser sagerne bag tallet
    forklaring: str


def noegletal(sager: Iterable, i_dag: date, risiko_dage: int = 7) -> list[Noegletal]:
    """Nøgletal til teamoverblikket – beregnet ud fra de aktuelle data."""
    sager = [s for s in sager if not s.arkiveret]
    aktive = [s for s in sager if not s.er_afsluttet()]
    opgaver = [(s, o) for s in aktive for o in _aabne(s)]

    def antal_sager(filter_):
        return sum(sag_matcher(s, filter_, i_dag, risiko_dage=risiko_dage) for s in sager)

    return [
        Noegletal("Aktive forløb", len(aktive), ALLE, "Forløb, der ikke er afsluttet"),
        Noegletal("Starter snart", antal_sager(KOMMENDE), KOMMENDE,
                  f"Første arbejdsdag inden for {risiko_dage} dage"),
        Noegletal("Opstart i risiko", antal_sager(RISIKO), RISIKO,
                  "Forsinkede opgaver eller tæt på start med åbne opgaver"),
        Noegletal("Forsinkede opgaver", sum(o.er_forsinket(i_dag) for _, o in opgaver),
                  SAG_FORSINKEDE, "Opgaver over fristen – også dem, der er blokerede"),
        Noegletal("Uden ansvarlig",
                  sum(not o.ansvarlig and not s.er_blokeret(o) for s, o in opgaver),
                  UDEN_ANSVARLIG, "Opgaver, der kan udføres, men ikke er tildelt en person"),
        Noegletal("Afventer andre", sum(o.status == Opgave.AFVENTER for _, o in opgaver),
                  MANGLER_BEKRAEFTELSE, "Opgaver, der afventer en ekstern part"),
        Noegletal("Klar til afslutning", antal_sager(KLAR_TIL_AFSLUTNING), KLAR_TIL_AFSLUTNING,
                  "Alle obligatoriske opgaver er lukket – mangler kontrol og arkivering"),
    ]


def naeste_handling(sag, i_dag: date):
    """Det mest presserende spor (SporStatus) i sagen, eller None."""
    rang = {sp.FORSINKET: 0, sp.KLAR: 1, sp.I_GANG: 2, sp.AFVENTER: 3, sp.BLOKERET: 4}
    spor = [s for s in sp.alle_spor(sag, i_dag) if s.status in rang]
    return min(spor, key=lambda s: rang[s.status]) if spor else None
