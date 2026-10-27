"""Kontrolrum: dashboardets overblikskort, arbejdskøer og "Haster nu".

Ren logik uden brugerflade. Alt bygger på de fælles beregninger, så dashboard,
arbejdsbakke og Teamoverblik altid er enige:

- app/domain/arbejdsspor.py: arbejdstilstand, tidsrisiko, ansvar og klarhed.
- app/services/arbejdsbakke.py: visninger og teamfiltre (kortenes klik åbner
  netop de lister, tallene er talt ud fra).
- app/services/action_center.py: regler (Indstillinger) og Alarm-modellen, så
  køerne vises med Action Centerets liste og hurtige handlinger.

Køerne viser én række pr. medarbejder (navnet og antal åbne opgaver i køen); de
enkelte opgaver ses i sagen. Betingede behov (tøj, mobil …) giver kun
køelementer, når HR har registreret behovet. Intet gemmes – alt beregnes ud
fra sagernes aktuelle tilstand.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from app.domain import arbejdsspor as sp
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave, laes_iso_dato
from app.services import arbejdsbakke as ab
from app.services.action_center import ADVARSEL, KRITISK, PLANLAGT, Alarm, Regler

# Hvor et overblikskort fører hen.
ARBEJDSBAKKE = "arbejdsbakke"
TEAM = "team"


def _dage(antal: int) -> str:
    return f"{antal} {'dag' if antal == 1 else 'dage'}"


def sidst_aendret(sag, opgave: Opgave) -> Optional[datetime]:
    """Seneste hændelse i tidslinjen om opgaven (statusskift, ændring …)."""
    for h in reversed(sag.historik.haendelser()):
        if h.get("reference") == opgave.id:
            try:
                return datetime.fromisoformat(h["tid"])
            except (KeyError, ValueError):
                break
    try:
        return datetime.fromisoformat(sag.oprettet)
    except ValueError:
        return None


def _aktive(sager) -> list:
    return [s for s in sager if not s.arkiveret and not s.er_afsluttet()]


### ----- overblikskort --------------------------------------------------------

FORSINKEDE = "forsinkede"
STARTER_SNART = "starter_snart"
MANGLER_KONTRAKT = "mangler_kontrakt"
I_RISIKO = "i_risiko"


@dataclass
class Overblik:
    noegle: str
    navn: str
    antal: int
    enhed: str            # hvad tallet tæller: "opgaver" eller "medarbejdere"
    forklaring: str
    maal: tuple           # (ARBEJDSBAKKE, visning) eller (TEAM, teamfilter)


def overblik(sager: Iterable, i_dag: date, regler: Regler | None = None) -> list[Overblik]:
    """De fire kort øverst. Hvert tal er talt med samme funktion som listen,
    kortet åbner – så tal og liste altid stemmer."""
    regler = regler or Regler()
    sager = [s for s in sager if not s.arkiveret]
    onboarding = [s for s in sager if isinstance(s, OnboardingForloeb)]
    dage = regler.naermer_sig_dage

    def team(filter_):
        return sum(ab.sag_matcher(s, filter_, i_dag, risiko_dage=dage) for s in onboarding)

    return [
        Overblik(FORSINKEDE, "Forsinkede opgaver", len(ab.poster(sager, ab.FORSINKEDE, i_dag)),
                 "opgaver", "Åbne opgaver over fristen – også dem, der venter på en forudsætning",
                 (ARBEJDSBAKKE, ab.FORSINKEDE)),
        Overblik(STARTER_SNART, "Starter snart", team(ab.KOMMENDE), "medarbejdere",
                 f"Første arbejdsdag inden for {_dage(dage)} (Indstillinger → Nærmer sig)",
                 (TEAM, ab.KOMMENDE)),
        Overblik(MANGLER_KONTRAKT, "Mangler kontrakt", team(ab.MANGLER_KONTRAKT),
                 "medarbejdere", "Kontrakten er ikke sendt eller ikke modtaget retur endnu",
                 (TEAM, ab.MANGLER_KONTRAKT)),
        Overblik(I_RISIKO, "Opstart i risiko", team(ab.RISIKO), "medarbejdere",
                 "Forsinkede eller blokerede obligatoriske opgaver, eller tæt på start med "
                 "åbne opgaver", (TEAM, ab.RISIKO)),
    ]


### ----- arbejdskøer ----------------------------------------------------------

KONTRAKT = "kontrakt"
UDSTYR = "udstyr"
OPLAERING = "oplaering"
AFVENTER = "afventer"
RETUR = "retur"
AFSLUTNING = "afslutning"


@dataclass
class Koe:
    noegle: str
    navn: str
    ikon: str                 # navn i app/ui/ikoner.py
    forklaring: str
    poster: list              # [Alarm] – én pr. medarbejder (sag)
    enhed: str = "medarbejdere"

    @property
    def antal_sager(self) -> int:
        return len({a.sag_id for a in self.poster})


def _opgave_post(sag, o: Opgave, i_dag: date, regler: Regler) -> Alarm:
    """En opgaves plads i køen: hvor alvorlig den er. Tidsrisikoen vinder over
    blokeringen – en blokeret opgave over fristen er stadig "Forsinket"."""
    tilstand = sp.arbejdstilstand(sag, o)
    dage_over = o.dage_over_frist(i_dag) or 0
    if sp.tidsrisiko(o, i_dag, regler.naermer_sig_dage) == sp.FORSINKET:
        niveau, badge = KRITISK, "Forsinket"
    elif tilstand in (sp.BLOKERET, sp.AFVENTER):
        niveau, badge = ADVARSEL, tilstand
    else:
        niveau, badge = PLANLAGT, tilstand
    return Alarm(niveau, sag.navn, "", badge, sag.PROCES, sag.id, o.id, dage_over)


def _sorter(poster: list) -> list:
    orden = {KRITISK: 0, ADVARSEL: 1, PLANLAGT: 2}
    return sorted(poster, key=lambda a: (orden[a.niveau], -a.sortering, a.titel))


def _aabne_i_spor(sag, spor: tuple) -> list:
    return [o for o in sag.opgaver if not o.afsluttet and sp.spor_for(o) in spor]


def _spor_koe(sager, spor: tuple, i_dag, regler) -> list:
    """Åbne opgaver i sporene: kontrakt, oplæring og første jobs."""
    return [_opgave_post(sag, o, i_dag, regler)
            for sag in sager for o in _aabne_i_spor(sag, spor)]


# Spor -> behov, når opgaven ikke selv har en betingelse.
_SPOR_BEHOV = {"udstyr": "udstyr", "firmabil": "firmabil", "telefon": "mobil",
               "toej": "toej", "email": "email"}


def _udstyr_koe(sager, i_dag, regler) -> list:
    """Udstyr og firmabil (ældre forløb: tøj, telefon og e-mail hver for sig) – kun
    når HR har registreret behovet (et behov er ikke en bestilling, og uden behov
    mangler intet)."""
    poster = []
    for sag in sager:
        behov = getattr(sag, "behov", None)
        if behov is None:
            continue
        for o in _aabne_i_spor(sag, tuple(_SPOR_BEHOV)):
            if behov.betingelse_opfyldt(o.betingelse or _SPOR_BEHOV[sp.spor_for(o)]):
                poster.append(_opgave_post(sag, o, i_dag, regler))
    return poster


def _afventer_koe(sager, i_dag, regler) -> list:
    """Opgaver, der afventer en anden part (status Afventer)."""
    return [_opgave_post(sag, o, i_dag, regler)
            for sag in sager for o in sag.opgaver
            if not o.afsluttet and o.status == Opgave.AFVENTER]


def _retur_koe(sager, i_dag) -> list:
    """Fratrådte medarbejdere med udstyr, der endnu ikke er modtaget (én række pr. person)."""
    poster = []
    for m in sager:
        if not isinstance(m, Medarbejder):
            continue
        fratraadt = laes_iso_dato(m.fratraedelsesdato)
        if fratraadt is None or fratraadt > i_dag:
            continue
        mangler = [o for o in m.opgaver if not o.afsluttet and o.udstyr]
        if not mangler:
            continue
        over = max((o.dage_over_frist(i_dag) or 0 for o in mangler), default=0)
        poster.append(Alarm(
            KRITISK if over > 0 else ADVARSEL, m.navn,
            f"{len(mangler)} {'del' if len(mangler) == 1 else 'dele'} mangler",
            "Forsinket" if over > 0 else "Mangler", m.PROCES, m.id,
            mangler[0].id if len(mangler) == 1 else None, over,
        ))
    return poster


def _en_pr_sag(poster: list, sager) -> list:
    """Én række pr. medarbejder – kun navnet og antallet af åbne opgaver i køen.
    Den vigtigste opgave bestemmer mærket (fx Forsinket) og er den, sagen åbnes på;
    de enkelte opgaver ses i sagen."""
    navne = {s.id: s.navn for s in sager}
    grupper = {}
    for a in _sorter(poster):
        grupper.setdefault(a.sag_id, []).append(a)
    resultat = []
    for sag_id, gruppe in grupper.items():
        vigtigst, antal = gruppe[0], len(gruppe)
        resultat.append(Alarm(vigtigst.niveau, navne.get(sag_id, ""),
                              f"{antal} {'åben opgave' if antal == 1 else 'åbne opgaver'}",
                              vigtigst.badge, vigtigst.modul, sag_id, vigtigst.opgave_id,
                              vigtigst.sortering))
    return _sorter(resultat)


def _afslutning_koe(sager, i_dag) -> list:
    """Samme regel som Action Center og Teamoverblikket: arbejdet er gjort, men sagen
    er ikke kontrolleret og arkiveret."""
    poster = []
    for sag in sager:
        if not ab.sag_matcher(sag, ab.KLAR_TIL_AFSLUTNING, i_dag):
            continue
        valgfrie = sum(not o.afsluttet for o in sag.opgaver)
        poster.append(Alarm(
            PLANLAGT, sag.navn, "Kontrollér og arkivér"
            + (f" · åbne valgfrie opgaver: {valgfrie}" if valgfrie else ""),
            "Afslut", sag.PROCES, sag.id,
        ))
    return poster


def koeer(sager: Iterable, i_dag: date, regler: Regler | None = None) -> list[Koe]:
    regler = regler or Regler()
    alle = [s for s in sager if not s.arkiveret]
    aktive = _aktive(alle)
    onboarding = [s for s in aktive if isinstance(s, OnboardingForloeb)]
    return [
        Koe(KONTRAKT, "Mangler kontrakt", "kontrakt",
            "Kontrakter, der skal udarbejdes, sendes eller registreres retur",
            _en_pr_sag(_spor_koe(onboarding, ("kontrakt",), i_dag, regler), onboarding)),
        Koe(UDSTYR, "Udstyr og firmabil", "udstyr",
            "Valgt udstyr, der ikke er sendt, og firmabiler, der ikke er bestilt",
            _en_pr_sag(_udstyr_koe(onboarding, i_dag, regler), onboarding)),
        Koe(OPLAERING, "Oplæringsdag", "oplaering",
            "Oplæringsdage, der ikke er fastlagt og bekræftet endnu",
            _en_pr_sag(_spor_koe(onboarding, ("oplaering", "opstart"), i_dag, regler),
                       onboarding)),
        Koe(AFVENTER, "Afventer andre", "afventer",
            "Opgaver, der venter på svar, godkendelse eller levering fra en anden part",
            _en_pr_sag(_afventer_koe(aktive, i_dag, regler), aktive)),
        Koe(RETUR, "Offboarding: udstyr mangler", "retur",
            "Fratrådte medarbejdere med udstyr, der ikke er modtaget",
            _sorter(_retur_koe(aktive, i_dag))),
        Koe(AFSLUTNING, "Klar til afslutning", "afslut",
            "Obligatoriske opgaver er lukket – mangler afsluttende kontrol og arkivering",
            _afslutning_koe(alle, i_dag), "sager"),
    ]


### ----- haster nu ------------------------------------------------------------

# Hvorfor en opgave er på listen (vigtigst først).
KRITISK_FORSINKELSE = "Forsinket"
TRUER_OPSTART = "Truer opstart"
INGEN_ANSVARLIG = "Ingen ejer"
FOR_LAENGE = "Står stille"
FRIST_I_DAG = "Frist i dag"
GRUNDE = (KRITISK_FORSINKELSE, TRUER_OPSTART, INGEN_ANSVARLIG, FOR_LAENGE, FRIST_I_DAG)

# Den direkte handling i listen.
AABN = "aabn"
TILDEL = "tildel"
AABN_FORUDSAETNING = "forudsaetning"


@dataclass
class Haster:
    grund: str
    forklaring: str        # fx "3 dage over frist" eller "Starter om 2 dage"
    sag: object
    opgave: Opgave
    tilstand: str          # arbejdstilstand
    tidsrisiko: str
    aarsag: str            # blokeringsårsag (tom, hvis opgaven kan udføres)
    handling: str
    handling_opgave_id: str   # den opgave, handlingen åbner (forudsætningen ved blokering)

    @property
    def omraade(self) -> str:
        """Arbejdssporet; opgaver uden spor (offboarding) vises som udstyr eller tomt."""
        spor = sp.spor_for(self.opgave)
        if spor == sp.OEVRIGT:
            return "Udstyr" if self.opgave.udstyr else ""
        return sp.SPOR_NAVNE[spor]


def haster_nu(sager: Iterable, i_dag: date, regler: Regler | None = None) -> list[Haster]:
    """En kort, prioriteret handlingsliste – ikke alle åbne opgaver:

    1. Forsinkede opgaver (også blokerede), mest forsinkede først.
    2. Obligatoriske opgaver hos medarbejdere, hvis opstart er i risiko og nærmer sig.
    3. Opgaver, der kan udføres, men hverken har en afdeling eller en person.
    4. Opgaver, der har afventet andre længere end grænsen for stillestående
       sager, og blokerede opgaver, hvis frist nærmer sig.
    5. Øvrige opgaver med frist i dag.
    """
    regler = regler or Regler()
    aktive = _aktive(sager)
    set_ids, resultat = set(), []

    def tilfoej(grund, forklaring, sag, o):
        if o.id in set_ids:
            return
        set_ids.add(o.id)
        tilstand = sp.arbejdstilstand(sag, o)
        forudsaetninger = sag.forudsaetninger(o)
        if tilstand == sp.BLOKERET and forudsaetninger:
            handling, maal = AABN_FORUDSAETNING, forudsaetninger[0].id
        elif sp.ansvar(o) == sp.IKKE_TILDELT:
            handling, maal = TILDEL, o.id
        else:
            handling, maal = AABN, o.id
        resultat.append(Haster(grund, forklaring, sag, o, tilstand,
                               sp.tidsrisiko(o, i_dag, regler.naermer_sig_dage),
                               sag.blokeringsaarsag(o), handling, maal))

    aabne = [(s, o) for s in aktive for o in s.opgaver if not o.afsluttet]

    for sag, o in sorted(((s, o) for s, o in aabne if o.er_forsinket(i_dag)),
                         key=lambda p: -(p[1].dage_over_frist(i_dag) or 0)):
        tilfoej(KRITISK_FORSINKELSE, f"{_dage(o.dage_over_frist(i_dag))} over frist", sag, o)

    for sag in sorted((s for s in aktive if isinstance(s, OnboardingForloeb)),
                      key=lambda s: s.maaldato() or "9999"):
        klar = sp.klarhed(sag, i_dag, regler.naermer_sig_dage)
        dage = klar.dage_til_start
        if klar.niveau not in (sp.RISIKO, sp.OPSTART_BLOKERET) or dage is None \
                or not 0 <= dage <= regler.naermer_sig_dage:
            continue
        start = laes_iso_dato(sag.maaldato())
        tekst = "Starter i dag" if dage == 0 else f"Starter om {_dage(dage)}"
        for o in sag.opgaver:
            if o.obligatorisk and not o.afsluttet \
                    and not (o.frist_dato() and start and o.frist_dato() > start):
                tilfoej(TRUER_OPSTART, tekst, sag, o)

    # Afdelingen ejer opgaven – kun opgaver uden både person og afdeling mangler en ejer.
    for sag, o in aabne:
        if not sag.er_blokeret(o) and sp.ansvar(o) == sp.IKKE_TILDELT:
            tilfoej(INGEN_ANSVARLIG, "Hverken person eller afdeling", sag, o)

    for sag, o in aabne:
        if o.status == Opgave.AFVENTER:
            sidst = sidst_aendret(sag, o)
            dage = (i_dag - sidst.date()).days if sidst else 0
            if dage >= regler.stillestaaende_dage:
                tilfoej(FOR_LAENGE, f"Afventet i {_dage(dage)}", sag, o)
        elif sag.er_blokeret(o) and \
                sp.tidsrisiko(o, i_dag, regler.naermer_sig_dage) == sp.NAERMER_SIG:
            tilfoej(FOR_LAENGE, "Blokeret, frist nærmer sig", sag, o)

    for sag, o in aabne:
        if o.dage_over_frist(i_dag) == 0 and not sag.er_blokeret(o):
            tilfoej(FRIST_I_DAG, "Frist i dag", sag, o)
    return resultat
