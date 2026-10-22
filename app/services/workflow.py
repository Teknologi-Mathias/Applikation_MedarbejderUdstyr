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
    ("milepael", "milepæl"),
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
        )
        for post in skabelon.get("opgaver", [])
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
