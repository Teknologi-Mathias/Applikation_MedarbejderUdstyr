"""Hvad kræver handling? Logikken bag Action Center, Dagsoversigt og notifikationer.

Alt her er ren logik uden brugerflade, så reglerne er samlet ét sted.
"""
from dataclasses import dataclass

from app.medarbejder import Medarbejder
from app.opgave import Opgave, laes_iso_dato

# Regler – juster her.
NAERMER_SIG_DAGE = 7          # "Fratrædelse nærmer sig" vises så mange dage før
INGEN_OPGAVER_EFTER_DAGE = 0  # sag uden opgaver markeres fra fratrædelsesdagen

KRITISK = "kritisk"
ADVARSEL = "advarsel"
PLANLAGT = "planlagt"
_NIVEAU_ORDEN = {KRITISK: 0, ADVARSEL: 1, PLANLAGT: 2}


@dataclass
class Alarm:
    niveau: str
    titel: str
    undertitel: str
    badge: str
    loennr: str
    opgave_id: str = None
    sortering: int = 0      # højere = vigtigere inden for samme niveau


def _aktive_sager(medarbejdere):
    """Medarbejdere hvis sag ikke er afviklet (heller ikke manuelt)."""
    return [m for m in medarbejdere if m.status != Medarbejder.STATUS_AFVIKLET]


def action_center(medarbejdere, i_dag):
    """Alle alarmer, vigtigste først: forsinket > afventer/mangler > planlagt."""
    alarmer = []
    for m in _aktive_sager(medarbejdere):
        for o in m.aabne_opgaver():
            dage_over = o.dage_over_frist(i_dag)
            ansvarlig = o.ansvarlig or "ingen angivet"
            if dage_over is not None and dage_over > 0:
                alarmer.append(Alarm(
                    KRITISK,
                    o.navn,
                    f"{m.navn} · Ansvarlig: {ansvarlig} · "
                    f"{dage_over} {'dag' if dage_over == 1 else 'dage'} over frist",
                    "Forsinket",
                    m.loennr,
                    o.id,
                    dage_over,
                ))
            elif o.status == Opgave.AFVENTER:
                naeste = o.naeste_handling or "næste handling ikke angivet"
                alarmer.append(Alarm(
                    ADVARSEL,
                    o.navn,
                    f"{m.navn} · Ansvarlig: {ansvarlig} · {naeste}",
                    "Afventer",
                    m.loennr,
                    o.id,
                ))

        fratraedelse = laes_iso_dato(m.fratraedelsesdato)
        if fratraedelse is None:
            continue
        dage_til = (fratraedelse - i_dag).days

        if not m.opgaver and -dage_til >= INGEN_OPGAVER_EFTER_DAGE:
            alarmer.append(Alarm(
                ADVARSEL,
                "Sagen har ingen opgaver",
                f"{m.navn} · Åbn sagen og tilføj opgaver",
                "Mangler",
                m.loennr,
            ))

        if 0 <= dage_til <= NAERMER_SIG_DAGE:
            aabne = len(m.aabne_opgaver())
            badge = {0: "I dag", 1: "I morgen"}.get(dage_til, f"{dage_til} dage")
            alarmer.append(Alarm(
                PLANLAGT,
                "Sidste arbejdsdag i dag" if dage_til == 0 else "Fratrædelse nærmer sig",
                f"{m.navn} · {aabne} {'åben opgave' if aabne == 1 else 'åbne opgaver'} "
                "inden sidste arbejdsdag",
                badge,
                m.loennr,
                sortering=-dage_til,
            ))

    alarmer.sort(key=lambda a: (_NIVEAU_ORDEN[a.niveau], -a.sortering, a.titel))
    return alarmer


def dagsoversigt(medarbejdere, i_dag):
    """Åbne opgaver med frist i dag: [(medarbejder, opgave)], sorteret efter navn."""
    resultat = [
        (m, o)
        for m in _aktive_sager(medarbejdere)
        for o in m.aabne_opgaver()
        if o.dage_over_frist(i_dag) == 0
    ]
    resultat.sort(key=lambda par: (par[1].ansvarlig, par[0].navn, par[1].navn))
    return resultat


def forsinkede(medarbejdere, i_dag):
    """Alle forsinkede opgaver: [(medarbejder, opgave)] – bruges til notifikationer."""
    return [
        (m, o)
        for m in _aktive_sager(medarbejdere)
        for o in m.forsinkede_opgaver(i_dag)
    ]
