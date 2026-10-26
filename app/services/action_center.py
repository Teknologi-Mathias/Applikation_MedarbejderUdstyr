"""Action Center: hvad kræver handling – på tværs af onboarding og offboarding.

Ren logik uden brugerflade. Alarmer beregnes hver gang ud fra sagernes
aktuelle tilstand; de gemmes ikke, så den samme hændelse kan aldrig give
dublerede opgaver.

Prioritet: KRITISK (forsinket) > ADVARSEL (afventer, mangler, stillestående)
> PLANLAGT (nærmer sig, venter, klar til afslutning).
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from app.domain import arbejdsspor as sp
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave, laes_iso_dato
from app.domain.sag import Sag

KRITISK = "kritisk"
ADVARSEL = "advarsel"
PLANLAGT = "planlagt"
_NIVEAU_ORDEN = {KRITISK: 0, ADVARSEL: 1, PLANLAGT: 2}

MODUL_NAVN = {Medarbejder.PROCES: "Offboarding", OnboardingForloeb.PROCES: "Onboarding"}


@dataclass
class Regler:
    stillestaaende_dage: int = 14
    naermer_sig_dage: int = 7

    @classmethod
    def fra_indstillinger(cls, indstillinger: dict) -> "Regler":
        return cls(int(indstillinger.get("stillestaaende_dage", 14)),
                   int(indstillinger.get("naermer_sig_dage", 7)))


@dataclass
class Alarm:
    niveau: str
    titel: str
    undertitel: str
    badge: str
    modul: str
    sag_id: str
    opgave_id: Optional[str] = None
    sortering: int = 0      # højere = vigtigere inden for samme niveau


def _dage(antal: int) -> str:
    return f"{antal} {'dag' if antal == 1 else 'dage'}"


def _dage_siden(tid: Optional[datetime], i_dag: date) -> Optional[int]:
    return None if tid is None else (i_dag - tid.date()).days


def _status_siden(sag: Sag) -> Optional[datetime]:
    """Tidspunktet for sagens seneste statusskift (eller oprettelse)."""
    for h in reversed(sag.historik.haendelser()):
        if (h.get("data") or {}).get("type") in ("status", "oprettet"):
            try:
                return datetime.fromisoformat(h["tid"])
            except (KeyError, ValueError):
                break
    try:
        return datetime.fromisoformat(sag.oprettet)
    except ValueError:
        return None


def _opgave_alarmer(sag: Sag, i_dag: date) -> list[Alarm]:
    alarmer = []
    for o in sag.aabne_opgaver():
        dage_over = o.dage_over_frist(i_dag)
        ansvarlig = o.ansvarlig or "ingen angivet"
        if dage_over is not None and dage_over > 0:
            alarmer.append(Alarm(
                KRITISK, o.navn,
                f"{sag.navn} · Ansvarlig: {ansvarlig} · {_dage(dage_over)} over frist",
                "Forsinket", sag.PROCES, sag.id, o.id, dage_over,
            ))
        elif o.status == Opgave.AFVENTER:
            naeste = o.naeste_handling or "næste handling ikke angivet"
            alarmer.append(Alarm(
                ADVARSEL, o.navn, f"{sag.navn} · Ansvarlig: {ansvarlig} · {naeste}",
                "Afventer", sag.PROCES, sag.id, o.id,
            ))
        elif not o.ansvarlig:
            alarmer.append(Alarm(
                ADVARSEL, f"Ingen ansvarlig: {o.navn}", f"{sag.navn} · Tildel en ansvarlig",
                "Ansvarlig", sag.PROCES, sag.id, o.id,
            ))
    return alarmer


def _faelles_alarmer(sag: Sag, i_dag: date, regler: Regler) -> list[Alarm]:
    alarmer = []
    stille = _dage_siden(sag.sidste_aktivitet(), i_dag)
    if stille is not None and stille >= regler.stillestaaende_dage and not sag.er_afsluttet():
        alarmer.append(Alarm(
            ADVARSEL, "Ingen bevægelse i sagen",
            f"{sag.navn} · Status: {sag.status} · senest ændret for {_dage(stille)} siden",
            "Stillestående", sag.PROCES, sag.id, sortering=stille,
        ))
    if sag.er_afsluttet() and not sag.arkiveret:
        alarmer.append(Alarm(
            PLANLAGT, "Klar til afsluttende kontrol",
            f"{sag.navn} · {sag.status} – kontrollér og arkivér sagen",
            "Afslut", sag.PROCES, sag.id,
        ))
    return alarmer


def _offboarding_alarmer(m: Medarbejder, i_dag: date, regler: Regler) -> list[Alarm]:
    alarmer = []
    for r in m.usendte_rykkere():
        alarmer.append(Alarm(
            ADVARSEL, "Rykker ikke markeret som sendt",
            f"{m.navn} · {r.skabelon_navn} · kladde oprettet {r.oprettet[:10]} af {r.oprettet_af}",
            "Kladde", m.PROCES, m.id,
        ))
    fratraedelse = laes_iso_dato(m.fratraedelsesdato)
    if fratraedelse is None:
        return alarmer
    dage_til = (fratraedelse - i_dag).days
    if not m.opgaver and dage_til <= 0:
        alarmer.append(Alarm(
            ADVARSEL, "Sagen har ingen opgaver", f"{m.navn} · Åbn sagen og tilføj opgaver",
            "Mangler", m.PROCES, m.id,
        ))
    if 0 <= dage_til <= regler.naermer_sig_dage:
        aabne = len(m.aabne_opgaver())
        alarmer.append(Alarm(
            PLANLAGT,
            "Sidste arbejdsdag i dag" if dage_til == 0 else "Fratrædelse nærmer sig",
            f"{m.navn} · {aabne} {'åben opgave' if aabne == 1 else 'åbne opgaver'} "
            "inden sidste arbejdsdag",
            {0: "I dag", 1: "I morgen"}.get(dage_til, f"{dage_til} dage"),
            m.PROCES, m.id, sortering=-dage_til,
        ))
    return alarmer


def _onboarding_alarmer(f: OnboardingForloeb, i_dag: date, regler: Regler) -> list[Alarm]:
    alarmer = []
    if not f.ansvarlig:
        alarmer.append(Alarm(
            ADVARSEL, "Forløbet har ingen ansvarlig", f"{f.navn} · {f.stilling} · {f.omraade}",
            "Ansvarlig", f.PROCES, f.id,
        ))
    if f.status in (f.STATUS_KONTRAKT, f.STATUS_OPLAERING):
        venter = _dage_siden(_status_siden(f), i_dag) or 0
        alarmer.append(Alarm(
            PLANLAGT, f.status,
            f"{f.navn} · {f.stilling} · {f.omraade or 'intet område'} · venter {_dage(venter)}",
            "Venter", f.PROCES, f.id, sortering=venter,
        ))
    foerste = laes_iso_dato(f.foerste_dag())
    if foerste is not None and not f.er_afsluttet():
        dage_til = (foerste - i_dag).days
        if 0 <= dage_til <= regler.naermer_sig_dage:
            # Samme vurdering som Teamoverblikket (app/domain/arbejdsspor.py).
            klar = sp.klarhed(f, i_dag, regler.naermer_sig_dage)
            niveau = {sp.OPSTART_BLOKERET: KRITISK, sp.RISIKO: ADVARSEL}.get(klar.niveau, PLANLAGT)
            aarsager = "; ".join(klar.aarsager) or "alle obligatoriske opgaver er udført"
            alarmer.append(Alarm(
                niveau, f"{klar.niveau}: første arbejdsdag nærmer sig",
                f"{f.navn} · {aarsager}",
                {0: "I dag", 1: "I morgen"}.get(dage_til, f"{dage_til} dage"),
                f.PROCES, f.id, sortering=-dage_til,
            ))
    return alarmer


def action_center(sager: Iterable[Sag], i_dag: date, regler: Regler | None = None) -> list[Alarm]:
    """Alle alarmer for de givne (aktive) sager, vigtigste først."""
    regler = regler or Regler()
    alarmer = []
    for sag in sager:
        if sag.arkiveret:
            continue
        if not sag.er_afsluttet():
            alarmer += _opgave_alarmer(sag, i_dag)
        alarmer += _faelles_alarmer(sag, i_dag, regler)
        if isinstance(sag, Medarbejder):
            alarmer += _offboarding_alarmer(sag, i_dag, regler)
        elif isinstance(sag, OnboardingForloeb):
            alarmer += _onboarding_alarmer(sag, i_dag, regler)
    alarmer.sort(key=lambda a: (_NIVEAU_ORDEN[a.niveau], -a.sortering, a.titel))
    return alarmer


def dagsoversigt(sager: Iterable[Sag], i_dag: date) -> list:
    """Åbne opgaver med frist i dag: [(sag, opgave)], sorteret efter ansvarlig."""
    resultat = [
        (sag, o)
        for sag in sager if not sag.arkiveret and not sag.er_afsluttet()
        for o in sag.aabne_opgaver()
        if o.dage_over_frist(i_dag) == 0
    ]
    resultat.sort(key=lambda par: (par[1].ansvarlig, par[0].navn, par[1].navn))
    return resultat


def forsinkede(sager: Iterable[Sag], i_dag: date) -> list:
    """Alle forsinkede opgaver: [(sag, opgave)]."""
    return [
        (sag, o) for sag in sager if not sag.arkiveret and not sag.er_afsluttet()
        for o in sag.forsinkede_opgaver(i_dag)
    ]
