"""Kontrolrum: dashboardets overblikskort, arbejdskøer og "Haster nu".

Ren logik uden brugerflade. Alt bygger på de fælles beregninger, så dashboard,
arbejdsbakke og Teamoverblik altid er enige:

- app/domain/arbejdsspor.py: arbejdstilstand, tidsrisiko, ansvar og klarhed.
- app/services/arbejdsbakke.py: visninger og teamfiltre (kortenes klik åbner
  netop de lister, tallene er talt ud fra).
- app/services/action_center.py: regler (Indstillinger) og Alarm-modellen, så
  køerne vises med Action Centerets liste og hurtige handlinger.

Betingede behov (tøj, mobil …) giver kun køelementer, når HR har registreret
behovet. Intet gemmes – alt beregnes ud fra sagernes aktuelle tilstand.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from app.domain import arbejdsspor as sp
from app.domain.behov import BEKLAEDNING
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


def _vis_dato(iso: str) -> str:
    dato = laes_iso_dato(str(iso)[:10])
    return dato.strftime("%d-%m-%Y") if dato else ""


def _vis_tid(iso: str) -> str:
    """"2026-12-01T08:00:00" -> "01-12-2026 08:00"."""
    return f"{_vis_dato(iso)} {str(iso)[11:16]}".strip() if iso else ""


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
UDEN_ANSVARLIG = "uden_ansvarlig"
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

    uden = [p for p in ab.poster(sager, ab.IKKE_TILDELT, i_dag) if not p.blokeret]
    return [
        Overblik(FORSINKEDE, "Forsinkede opgaver", len(ab.poster(sager, ab.FORSINKEDE, i_dag)),
                 "opgaver", "Åbne opgaver over fristen – også dem, der venter på en forudsætning",
                 (ARBEJDSBAKKE, ab.FORSINKEDE)),
        Overblik(STARTER_SNART, "Starter snart", team(ab.KOMMENDE), "medarbejdere",
                 f"Første arbejdsdag inden for {_dage(dage)} (Indstillinger → Nærmer sig)",
                 (TEAM, ab.KOMMENDE)),
        Overblik(UDEN_ANSVARLIG, "Opgaver uden ansvarlig", len(uden), "opgaver",
                 "Opgaver, der kan udføres nu, men ikke er tildelt en person",
                 (ARBEJDSBAKKE, ab.IKKE_TILDELT)),
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
    poster: list              # [Alarm] – én pr. opgave (eller pr. sag, se enhed)
    enhed: str = "opgaver"    # "opgaver" eller "sager"/"medarbejdere"

    @property
    def antal_sager(self) -> int:
        return len({a.sag_id for a in self.poster})


def _opgave_post(sag, o: Opgave, i_dag: date, regler: Regler, tilstandstekst: str,
                 ekstra: str = "") -> Alarm:
    """Én opgave i en kø. Arbejdstilstand, tidsrisiko og ansvar vises hver for sig:
    en blokeret opgave over fristen er både "Forsinket" og viser, hvad den venter på."""
    tilstand = sp.arbejdstilstand(sag, o)
    tid = sp.tidsrisiko(o, i_dag, regler.naermer_sig_dage)
    dage_over = o.dage_over_frist(i_dag) or 0
    if tilstand == sp.BLOKERET:
        tilstandstekst = sag.blokeringsaarsag(o)
    dele = [tilstandstekst]
    if ekstra:
        dele.append(ekstra)
    if tid == sp.FORSINKET:
        dele.append(f"{_dage(dage_over)} over frist")
    elif o.frist:
        dele.append(f"Frist {_vis_dato(o.frist)}")
    dele.append(f"Ansvarlig: {sp.ejer(o)}")
    if tid == sp.FORSINKET:
        niveau, badge = KRITISK, "Forsinket"
    elif tilstand in (sp.BLOKERET, sp.AFVENTER):
        niveau, badge = ADVARSEL, tilstand
    else:
        niveau, badge = PLANLAGT, tilstand
    return Alarm(niveau, f"{sag.navn} · {o.navn}", " · ".join(d for d in dele if d), badge,
                 sag.PROCES, sag.id, o.id, dage_over)


def _sorter(poster: list) -> list:
    orden = {KRITISK: 0, ADVARSEL: 1, PLANLAGT: 2}
    return sorted(poster, key=lambda a: (orden[a.niveau], -a.sortering, a.titel))


def _aabne_i_spor(sag, spor: tuple) -> list:
    return [o for o in sag.opgaver if not o.afsluttet and sp.spor_for(o) in spor]


# Kontraktopgaven (standardskabelonen): Afventer = sendt, Udført = modtaget retur.
_KONTRAKT_TEKST = {
    Opgave.IKKE_STARTET: "Afventer udarbejdelse og afsendelse",
    Opgave.I_GANG: "Under udarbejdelse – ikke sendt",
    Opgave.AFVENTER: "Sendt – afventer underskrift retur",
}
_GENEREL_TEKST = {
    Opgave.IKKE_STARTET: "Ikke registreret som udført",
    Opgave.I_GANG: "I gang",
    Opgave.AFVENTER: "Afventer anden part",
}


def _kontrakt_koe(sager, i_dag, regler) -> list:
    poster = []
    for sag in sager:
        for o in _aabne_i_spor(sag, ("kontrakt",)):
            tekster = _KONTRAKT_TEKST if o.noegle == "kontrakt" else _GENEREL_TEKST
            poster.append(_opgave_post(sag, o, i_dag, regler, tekster[o.status]))
    return poster


# Spor -> behov, når opgaven ikke selv har en betingelse.
_SPOR_BEHOV = {"telefon": "mobil", "toej": "toej"}
_UDSTYR_TEKST = {
    Opgave.IKKE_STARTET: "Ikke klargjort eller sendt",
    Opgave.I_GANG: "Under klargøring",
    Opgave.AFVENTER: "Afventer levering eller anden part",
}


def _behov_tekst(behov, noegle: str) -> str:
    if noegle == "mobil":
        return f"Mobil · {behov.abonnement or 'abonnement ikke valgt'}"
    valgte = [n for n in BEKLAEDNING if behov.toej(n).valgt] if noegle == "toej" else [noegle]
    return ", ".join(f"{BEKLAEDNING[n]} {behov.toej(n).stoerrelse} × {behov.toej(n).antal}"
                     for n in valgte if n in BEKLAEDNING)


def _udstyr_koe(sager, i_dag, regler) -> list:
    """Telefon og tøj som hver sin opgave – kun når HR har registreret behovet."""
    poster = []
    for sag in sager:
        behov = getattr(sag, "behov", None)
        if behov is None:
            continue
        for o in _aabne_i_spor(sag, ("telefon", "toej")):
            noegle = o.betingelse or _SPOR_BEHOV[sp.spor_for(o)]
            if not behov.betingelse_opfyldt(noegle):
                continue
            poster.append(_opgave_post(sag, o, i_dag, regler, _UDSTYR_TEKST[o.status],
                                       _behov_tekst(behov, noegle)))
    return poster


def _oplaering_tekst(sag, o: Opgave) -> str:
    """Et registreret tidspunkt betyder ikke, at oplæringen er booket eller gennemført."""
    if o.status == Opgave.AFVENTER:
        return "Afventer bekræftelse" + (f" ({_vis_tid(o.planlagt)})" if o.planlagt else "")
    if o.planlagt:
        return f"Tidspunkt registreret {_vis_tid(o.planlagt)} – ikke bekræftet"
    if o.noegle.endswith("booket"):
        return "Intet tidspunkt registreret"
    booket = next((x for x in sag.opgaver if x.noegle in o.afhaenger_af
                   and x.status == Opgave.UDFOERT and sp.spor_for(x) == "oplaering"), None)
    if booket:
        tid = f" {_vis_tid(booket.planlagt)}" if booket.planlagt else ""
        return f"Booket{tid} – ikke registreret som gennemført"
    return _GENEREL_TEKST[o.status]


def _oplaering_koe(sager, i_dag, regler) -> list:
    return [_opgave_post(sag, o, i_dag, regler, _oplaering_tekst(sag, o))
            for sag in sager for o in _aabne_i_spor(sag, ("oplaering", "opstart"))]


def _afventer_koe(sager, i_dag, regler) -> list:
    """Hvad afventes, hvem skal handle, hvornår blev der sidst fulgt op, og hvornår
    bør der følges op igen (sidst + grænsen for stillestående sager)."""
    poster = []
    for sag in sager:
        for o in sag.opgaver:
            if o.afsluttet or o.status != Opgave.AFVENTER:
                continue
            sidst = sidst_aendret(sag, o)
            opfoelgning = ""
            if sidst:
                igen = sidst.date() + timedelta(days=regler.stillestaaende_dage)
                opfoelgning = (f"Sidst fulgt op {_vis_dato(sidst.date().isoformat())} · "
                               + ("Følg op nu" if igen <= i_dag
                                  else f"Følg op {_vis_dato(igen.isoformat())}"))
            poster.append(_opgave_post(sag, o, i_dag, regler,
                                       f"Afventer: {o.naeste_handling or o.navn}", opfoelgning))
    return poster


_RETUR_TEKST = {Opgave.IKKE_STARTET: "ikke modtaget", Opgave.I_GANG: "under behandling",
                Opgave.AFVENTER: "afventer medarbejderen"}


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
        sendte = sum(r.sendt for r in m.rykkere)
        dele = [", ".join(f"{o.udstyr}: {_RETUR_TEKST[o.status]}" for o in mangler),
                "Returlabel sendt" if m.tracking_link else "Ingen returlabel registreret",
                f"{sendte} {'rykker' if sendte == 1 else 'rykkere'} sendt"]
        if over > 0:
            dele.append(f"{_dage(over)} over frist")
        poster.append(Alarm(
            KRITISK if over > 0 else ADVARSEL,
            f"{m.navn} · Mangler {len(mangler)} {'del' if len(mangler) == 1 else 'dele'}",
            " · ".join(dele), "Forsinket" if over > 0 else "Mangler", m.PROCES, m.id,
            mangler[0].id if len(mangler) == 1 else None, over,
        ))
    return poster


def _afslutning_koe(sager, i_dag) -> list:
    """Samme regel som Action Center og Teamoverblikket: arbejdet er gjort, men sagen
    er ikke kontrolleret og arkiveret."""
    poster = []
    for sag in sager:
        if not ab.sag_matcher(sag, ab.KLAR_TIL_AFSLUTNING, i_dag):
            continue
        valgfrie = sum(not o.afsluttet for o in sag.opgaver)
        poster.append(Alarm(
            PLANLAGT, f"{sag.navn} · Kontrollér og arkivér",
            f"Status: {sag.status} · alle obligatoriske opgaver er lukket"
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
            _sorter(_kontrakt_koe(onboarding, i_dag, regler))),
        Koe(UDSTYR, "Telefon og arbejdstøj", "udstyr",
            "Registrerede behov, der endnu ikke er klargjort eller sendt",
            _sorter(_udstyr_koe(onboarding, i_dag, regler))),
        Koe(OPLAERING, "Afventer oplæring eller jobs", "oplaering",
            "Planlægning, bekræftelse og gennemførelse af oplæring og første jobs",
            _sorter(_oplaering_koe(onboarding, i_dag, regler))),
        Koe(AFVENTER, "Afventer andre", "afventer",
            "Opgaver, der venter på svar, godkendelse eller levering fra en anden part",
            _sorter(_afventer_koe(aktive, i_dag, regler))),
        Koe(RETUR, "Offboarding: udstyr mangler", "retur",
            "Fratrådte medarbejdere med udstyr, der ikke er modtaget",
            _sorter(_retur_koe(aktive, i_dag)), "medarbejdere"),
        Koe(AFSLUTNING, "Klar til afslutning", "afslut",
            "Obligatoriske opgaver er lukket – mangler afsluttende kontrol og arkivering",
            _afslutning_koe(alle, i_dag), "sager"),
    ]


### ----- haster nu ------------------------------------------------------------

# Hvorfor en opgave er på listen (vigtigst først).
KRITISK_FORSINKELSE = "Forsinket"
TRUER_OPSTART = "Truer opstart"
INGEN_ANSVARLIG = "Ingen ansvarlig"
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
    3. Opgaver, der kan udføres, men ingen ejer har (ingen afdeling), eller hvor
       en afdelingskø ikke har fordelt en opgave med nær frist.
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
        elif sp.ansvar(o) != sp.BRUGER:
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

    for sag, o in aabne:
        if sag.er_blokeret(o) or o.ansvarlig:
            continue
        if sp.ansvar(o) == sp.IKKE_TILDELT:
            tilfoej(INGEN_ANSVARLIG, "Hverken person eller afdeling", sag, o)
        elif sp.tidsrisiko(o, i_dag, regler.naermer_sig_dage) == sp.NAERMER_SIG:
            tilfoej(INGEN_ANSVARLIG, f"{o.afdeling}: ikke fordelt, frist nærmer sig", sag, o)

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
