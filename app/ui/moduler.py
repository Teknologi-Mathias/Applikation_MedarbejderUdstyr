"""Hvordan onboarding og offboarding vises: kolonner, filtre, titler og datoer.

Siderne (SagListeSide, ModulOversigtSide, OpgaveOversigtSide) og controlleren
er fælles; et modul er blot en konfiguration af dem.
"""
from dataclasses import dataclass
from datetime import date
from typing import Callable

from app.domain import statusprik as prik
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import laes_iso_dato
from app.ui.hjaelpere import vis_dato
from app.ui.sag_liste_side import Filtervalg, Kolonne
from app.ui.theme import opgaver_stil, prik_stil


def _opgaver_tooltip(sag) -> str:
    i_dag = date.today()
    linjer = []
    for o in sag.opgaver:
        if o.afsluttet:
            tegn = "✓"
        elif sag.er_blokeret(o):
            tegn = "🔒"
        else:
            tegn = "!" if o.er_forsinket(i_dag) else "○"
        linje = f"{tegn}  {o.navn} – {o.status}"
        if o.ansvarlig:
            linje += f" ({o.ansvarlig})"
        if not o.afsluttet and o.frist:
            linje += f" · frist {vis_dato(o.frist)}"
        linjer.append(linje)
    return "\n".join(linjer)


def _opgave_kolonne(bredde: int = 0) -> Kolonne:
    """Opgaver-kolonnen (bredde 0 = strækkes til resten af pladsen)."""
    def sortering(sag):
        afsluttede, total = sag.opgave_optaelling()
        return (0, afsluttede / total) if total else (1, 0.0)

    def stil(sag):
        afsluttede, total = sag.opgave_optaelling()
        return opgaver_stil(afsluttede, total, bool(sag.forsinkede_opgaver(date.today())))

    return Kolonne("Opgaver", bredde, lambda s: s.opgave_tekst(), sortering, stil, _opgaver_tooltip)


def _prik_kolonne(titel, prik_for: Callable, klik: str, bredde: int = 150) -> Kolonne:
    """Statusfelt (app/domain/statusprik.py), der ændres med en drop down-menu i tabellen."""
    return Kolonne(titel, bredde, lambda s: prik_for(s).tekst, lambda s: prik_for(s).sortering,
                   lambda s: prik_stil(prik_for(s).tone),
                   lambda s: prik_for(s).tooltip, klik)


def _dato_kolonne(titel, felt) -> Kolonne:
    return Kolonne(titel, 150, lambda s: vis_dato(felt(s)) if felt(s) else "–",
                   lambda s: felt(s) or "9999")


def _loennr_noegle(loennr):
    return (0, int(loennr), "") if str(loennr).isdigit() else (1, 0, str(loennr).lower())


@dataclass
class Modul:
    proces: str
    navn: str                      # "Offboarding"
    flertal: str                   # "afviklingssager"
    statusser: tuple
    kolonner: list
    filtre: list
    datofelt: Callable             # sag -> ISO-dato til oversigtens diagram
    datotitel: str                 # "Fratrædelser de næste 14 dage"
    opret_tekst: str


def offboarding_modul() -> Modul:
    return Modul(
        proces=Medarbejder.PROCES,
        navn="Offboarding",
        flertal="afviklingssager",
        statusser=Medarbejder.STATUSER,
        kolonner=[
            Kolonne("Lønnr.", 90, lambda s: s.loennr, lambda s: _loennr_noegle(s.loennr)),
            Kolonne("Medarbejdernavn", 200, lambda s: s.navn),
            _dato_kolonne("Sidste arbejdsdag", lambda s: s.fratraedelsesdato),
            _prik_kolonne("Tankkort spærret", prik.tankkort, prik.TANKKORT),
            _prik_kolonne("Tøj og udstyr", prik.toej, prik.TOEJ, 165),
            _prik_kolonne("Telefon & SIM-kort", prik.telefon, prik.TELEFON),
            _prik_kolonne("Lukket i NAV?", prik.nav, prik.NAV, 120),
            _opgave_kolonne(),
        ],
        filtre=[],
        datofelt=lambda s: s.fratraedelsesdato,
        datotitel="Fratrædelser de næste 14 dage",
        opret_tekst="+ Opret fratrædelse",
    )


def onboarding_modul(omraader: Callable) -> Modul:
    return Modul(
        proces=OB.PROCES,
        navn="Onboarding",
        flertal="onboardingforløb",
        statusser=OB.STATUSER,
        kolonner=[
            Kolonne("Medarbejdernavn", 200, lambda s: s.navn),
            Kolonne("Lønnr.", 90, lambda s: s.loennr or "–", lambda s: _loennr_noegle(s.loennr)),
            Kolonne("Stilling", 80, lambda s: s.stilling),
            Kolonne("Område", 130, lambda s: s.omraade or "–"),
            _dato_kolonne("Første arbejdsdag", lambda s: s.foerste_dag()),
            _prik_kolonne("Kontrakt", prik.kontrakt, prik.KONTRAKT),
            _prik_kolonne("Udstyr", prik.udstyr, prik.UDSTYR, 165),
            _prik_kolonne("Opfølgning", prik.opfoelgning, prik.OPFOELGNING, 0),
        ],
        filtre=[
            Filtervalg("Stilling", lambda: list(OB.STILLINGER), lambda s: s.stilling),
            Filtervalg("Område", omraader, lambda s: s.omraade),
        ],
        datofelt=lambda s: s.foerste_dag(),
        datotitel="Første arbejdsdage de næste 14 dage",
        opret_tekst="+ Opret kandidat",
    )


def dage_til(iso: str):
    dato = laes_iso_dato(iso)
    return None if dato is None else (dato - date.today()).days
