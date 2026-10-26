"""Fælles arbejdsgangsmotor for onboarding og offboarding.

- opret_opgaver(): laver en sags opgaver ud fra en (versioneret) skabelon.
  Opgaverne kopieres ind i sagen, så senere ændringer i skabelonen ikke
  påvirker igangværende forløb.
- registrer_aendringer(): sammenligner to udgaver af en sag og skriver
  forskellene i tidslinjen – inkl. strukturerede statusskift, som rapporterne
  bygger på.
"""
from datetime import timedelta

from app.domain.opgave import Opgave, laes_iso_dato
from app.domain.sag import Sag

# Stamdata der logges ved ændring: proces -> ((felt, label), ...)
_STAMDATA = {
    "offboarding": (
        ("navn", "Navn"), ("loennr", "Lønnr."), ("fratraedelsesdato", "Sidste arbejdsdag"),
        ("email", "E-mail"), ("tracking_link", "Tracking-link"), ("kommentar", "Kommentar"),
    ),
    "onboarding": (
        ("navn", "Navn"), ("loennr", "Lønnr."), ("stilling", "Stilling"),
        ("omraade", "Område"), ("ansaettelsesdato", "Ansættelsesdato"),
        ("foerste_arbejdsdag", "Første arbejdsdag"), ("email", "E-mail"),
        ("ansvarlig", "Ansvarlig"), ("kommentar", "Kommentar"),
    ),
}

_OPGAVEFELTER = (
    ("navn", "navn"), ("ansvarlig", "ansvarlig"), ("frist", "frist"),
    ("udstyr", "udstyr"), ("naeste_handling", "næste handling"),
    ("obligatorisk", "obligatorisk"), ("beskrivelse", "beskrivelse"),
    ("milepael", "milepæl"), ("afdeling", "afdeling"), ("spor", "spor"),
    ("afhaenger_af", "forudsætninger"), ("planlagt", "planlagt tidspunkt"),
)


def frist_fra_dage(startdato: str, dage) -> str:
    """Frist som ISO-dato: startdato + antal dage (tom ved ugyldig dato)."""
    dato = laes_iso_dato(startdato)
    return (dato + timedelta(days=int(dage or 0))).isoformat() if dato else ""


def skabelon_reference(skabelon: dict) -> dict:
    return {"id": skabelon.get("id", ""), "navn": skabelon.get("navn", ""),
            "version": skabelon.get("version", 1)}


def opret_opgaver(skabelon: dict, startdato: str) -> list[Opgave]:
    return [
        Opgave(
            post["navn"],
            post.get("ansvarlig", ""),
            frist_fra_dage(startdato, post.get("frist_dage", 0)),
            obligatorisk=post.get("obligatorisk", True),
            udstyr=post.get("udstyr", ""),
            beskrivelse=post.get("beskrivelse", ""),
            milepael=post.get("milepael", ""),
            noegle=post.get("noegle", ""),
            spor=post.get("spor", ""),
            afdeling=post.get("afdeling", ""),
            afhaenger_af=post.get("afhaenger_af") or (),
            betingelse=post.get("betingelse", ""),
        )
        for post in skabelon.get("opgaver", [])
    ]


# Begrundelse på opgaver, som er undtaget automatisk, fordi behovet ikke er valgt.
IKKE_VALGT = "Ikke relevant – behovet er ikke valgt af HR"


def synkroniser_betingelser(sag: Sag, behov) -> None:
    """Gør betingede opgaver (ir)relevante efter HR's behov.

    Kun opgaver, der ikke er påbegyndt, ændres automatisk: de undtages med
    IKKE_VALGT – og genåbnes, hvis behovet vælges igen. En opgave, der er i
    gang eller udført, ændres aldrig lydløst – se uoverensstemmelser().
    """
    for o in sag.opgaver:
        if not o.betingelse:
            continue
        relevant = behov.betingelse_opfyldt(o.betingelse)
        automatisk = o.status == Opgave.UNDTAGET and o.begrundelse == IKKE_VALGT
        if relevant and automatisk:
            o.saet_status(Opgave.IKKE_STARTET)
            o.begrundelse = ""
        elif not relevant and o.status == Opgave.IKKE_STARTET:
            o.saet_status(Opgave.UNDTAGET)
            o.begrundelse = IKKE_VALGT


def uoverensstemmelser(sag: Sag, behov) -> list[str]:
    """Påbegyndte/udførte opgaver, hvis behov senere er fravalgt (skal kontrolleres)."""
    return [
        f"'{o.navn}' er {o.status.lower()}, men behovet er fravalgt – kontrollér opgaven."
        for o in sag.opgaver
        if o.betingelse and o.status in (Opgave.I_GANG, Opgave.AFVENTER, Opgave.UDFOERT)
        and not behov.betingelse_opfyldt(o.betingelse)
    ]


def registrer_oprettelse(sag: Sag, skabelon: dict | None) -> None:
    sag.historik.tilfoej(
        "Sag oprettet",
        f"Skabelon: {skabelon['navn']} (version {skabelon.get('version', 1)})"
        if skabelon else "Uden skabelon",
        data={"type": "oprettet", "status": sag.status},
    )


def registrer_aendringer(gammel: Sag, ny: Sag) -> None:
    """Skriver forskellene mellem to udgaver af en sag i ny.historik."""
    aendret = [
        f"{label}: {getattr(gammel, felt, '') or '–'} → {getattr(ny, felt, '') or '–'}"
        for felt, label in _STAMDATA.get(ny.PROCES, ())
        if getattr(gammel, felt, None) != getattr(ny, felt, None)
    ]
    if aendret:
        ny.historik.tilfoej("Stamdata ændret", "; ".join(aendret))
    gammelt_behov, nyt_behov = getattr(gammel, "behov", None), getattr(ny, "behov", None)
    if nyt_behov is not None and gammelt_behov.til_dict() != nyt_behov.til_dict():
        ny.historik.tilfoej("Behov ændret", "; ".join(gammelt_behov.aendringer(nyt_behov)),
                            data={"type": "behov"})

    gamle = {o.id: o for o in gammel.opgaver}
    nye = {o.id: o for o in ny.opgaver}
    for opgave_id, opgave in nye.items():
        foer = gamle.get(opgave_id)
        if foer is None:
            ny.historik.tilfoej(f"Opgave tilføjet: {opgave.navn}", reference=opgave_id)
            continue
        if foer.status != opgave.status:
            if opgave.afsluttet and not opgave.afsluttet_tid:
                opgave.saet_status(opgave.status)  # sikrer tidsstempel
            kommentar = opgave.begrundelse if opgave.status == Opgave.UNDTAGET else ""
            ny.historik.tilfoej(
                f"{opgave.navn}: {foer.status} → {opgave.status}", kommentar, opgave_id,
                data={"type": "opgave_status", "fra": foer.status, "til": opgave.status},
            )
        andet = [label for felt, label in _OPGAVEFELTER
                 if getattr(foer, felt) != getattr(opgave, felt)]
        if andet:
            ny.historik.tilfoej(
                f"Opgave ændret: {opgave.navn}", "Ændret: " + ", ".join(andet), opgave_id
            )
    for opgave_id, opgave in gamle.items():
        if opgave_id not in nye:
            ny.historik.tilfoej(f"Opgave slettet: {opgave.navn}", reference=opgave_id)

    if (gammel.status_manuel, gammel.status_begrundelse) != (
        ny.status_manuel, ny.status_begrundelse
    ):
        if ny.status_manuel:
            ny.historik.tilfoej(
                f"Status låst manuelt: {ny.status_manuel}", ny.status_begrundelse,
                data={"type": "manuel_status", "status": ny.status_manuel},
            )
        else:
            ny.historik.tilfoej("Manuel status fjernet", "Status beregnes igen ud fra opgaverne")

    registrer_statusskift(gammel.status, ny)


def registrer_statusskift(fra: str, sag: Sag) -> None:
    """Logger et statusskift som struktureret hændelse (bruges af rapporterne)."""
    if fra != sag.status:
        sag.historik.tilfoej(
            f"Status: {fra} → {sag.status}",
            data={"type": "status", "fra": fra, "til": sag.status,
                  "manuel": sag.status_manuel is not None},
        )


### ----- samtidige ændringer -------------------------------------------------

# Sagens felter, der beregnes eller styres af lagringen – flettes ikke som felter.
_IKKE_FLETTET_SAG = ("opgaver", "rykkere", "historik", "version", "opdateret", "status")


def _flet_felter(basis: dict, min: dict, deres: dict, hvad: str, konflikter: list,
                 springes_over=()) -> dict:
    """deres + mine ændringer (felt for felt). Begge ændret forskelligt -> konflikt."""
    resultat = dict(deres)
    for noegle, vaerdi in min.items():
        if noegle in springes_over or basis.get(noegle) == vaerdi:
            continue
        if deres.get(noegle) not in (basis.get(noegle), vaerdi):
            konflikter.append(f"{hvad}: {noegle}")
            continue
        resultat[noegle] = vaerdi
    return resultat


def _flet_liste(basis: list, min: list, deres: list, hvad: str, konflikter: list) -> list:
    """Opgaver/rykkere (dicts med id): mine tilføjelser, sletninger og feltændringer."""
    b = {x["id"]: x for x in basis}
    m = {x["id"]: x for x in min}
    resultat = []
    for post in deres:
        pid = post["id"]
        if pid in b and pid not in m:                     # jeg har slettet den
            if post != b[pid]:
                konflikter.append(f"{hvad} '{post.get('navn') or post.get('emne', '')}' "
                                  "er slettet af dig, men ændret af en anden")
                resultat.append(post)
            continue
        if pid in m and pid in b and m[pid] != b[pid]:
            post = _flet_felter(b[pid], m[pid], post,
                                f"{hvad} '{post.get('navn') or post.get('emne', '')}'",
                                konflikter, springes_over=("afsluttet",))
            # Afslutningstidspunktet følger statussen (ingen konflikt på tidsstemplet).
            if "status" in post and m[pid].get("status") != b[pid].get("status") \
                    and post["status"] == m[pid]["status"]:
                if post["status"] not in Opgave.AFSLUTTEDE:
                    post["afsluttet"] = ""
                elif not post.get("afsluttet"):
                    post["afsluttet"] = m[pid].get("afsluttet", "")
        resultat.append(post)
    deres_ids = {x["id"] for x in deres}
    for pid, post in m.items():
        if pid not in b and pid not in deres_ids:          # ny hos mig
            resultat.append(post)
        elif pid in b and pid not in deres_ids and post != b[pid]:
            konflikter.append(f"{hvad} '{post.get('navn') or post.get('emne', '')}' "
                              "er ændret af dig, men slettet af en anden")
    return resultat


def flet(basis: Sag, min: Sag, deres: Sag) -> Sag:
    """Fletter mine ændringer (basis -> min) ind i den aktuelle udgave (deres).

    Ændringer af forskellige felter eller forskellige opgaver flettes uden
    konflikt. Har begge ændret samme felt forskelligt, kastes KonfliktFejl med
    en liste over felterne – intet gemmes lydløst over en kollegas ændring.
    Mine nye tidslinjehændelser lægges oven på den aktuelle tidslinje.
    """
    from app.repositories.fejl import KonfliktFejl

    b, m, d = basis.til_dict(), min.til_dict(), deres.til_dict()
    konflikter = []
    data = _flet_felter(b, m, d, "Sagen", konflikter, springes_over=_IKKE_FLETTET_SAG)
    data["opgaver"] = _flet_liste(b.get("opgaver", []), m.get("opgaver", []),
                                  d.get("opgaver", []), "Opgaven", konflikter)
    if "rykkere" in d:
        data["rykkere"] = _flet_liste(b.get("rykkere", []), m.get("rykkere", []),
                                      d.get("rykkere", []), "Rykkeren", konflikter)
    if konflikter:
        af = (deres.historik.haendelser() or [{}])[-1].get("bruger") or "en anden"
        raise KonfliktFejl(
            f"{deres.navn} er ændret af {af}, mens du arbejdede, og I har ændret det samme "
            f"({'; '.join(konflikter)}). Dine ændringer er ikke gemt – sagen er genindlæst, "
            "så du kan se den aktuelle udgave og gentage dine ændringer.")
    data["status"] = (m if b.get("status_manuel") != m.get("status_manuel")
                      or b.get("status_begrundelse") != m.get("status_begrundelse") else d)["status"]
    data["historik"] = d["historik"]
    data["version"] = deres.version
    flettet = type(deres).fra_dict(data)
    for h in min.historik.haendelser()[len(basis.historik):]:
        if (h.get("data") or {}).get("type") == "status":
            continue                                  # beregnes igen nedenfor
        flettet.historik.tilfoej(h["handling"], h.get("kommentar", ""), h.get("reference", ""),
                                 bruger=h.get("bruger"), tid=h.get("tid"), data=h.get("data"))
    registrer_statusskift(deres.status, flettet)
    return flettet
