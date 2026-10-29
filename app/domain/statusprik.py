"""Statusprikker: forløbets vigtigste skridt som én farve pr. kolonne i tabellen.

Prikken er en genvej – den samler opgaverne til grøn/gul/rød, så man ikke skal
åbne forløbet for at se, hvor det står. Tonen er et navn fra temaet (groen, gul,
roed, intet); teksten står altid ved siden af farven.

    Onboarding   Kontrakt   grøn = underskrevet retur        rød = ellers
                 Udstyr     grøn = alt sendt   gul = delvist   rød = intet sendt
                 Oplæring   grøn = booket og bekræftet       rød = ellers
    Offboarding  NAV        grøn = lukket i NAV              rød = ellers
                 Udstyr     grøn = alt retur   gul = delvist   rød = intet retur
"""
from dataclasses import dataclass

from app.domain.opgave import Opgave

GROEN, GUL, ROED, INTET = "groen", "gul", "roed", "intet"

# Opgavenøgler fra standardskabelonerne (app/domain/skabelon.py).
KONTRAKT = "kontrakt"
UDSTYR = "udstyr"
OPLAERING = "oplaering_booket"
NAV = "nav"


@dataclass(frozen=True)
class Prik:
    tone: str
    tekst: str
    tooltip: str = ""
    sortering: int = 0                  # rød < gul < grøn < ikke relevant


_SORTERING = {ROED: 0, GUL: 1, GROEN: 2, INTET: 3}


def _prik(tone, tekst, tooltip=""):
    return Prik(tone, tekst, tooltip, _SORTERING[tone])


IKKE_RELEVANT = Prik(INTET, "–", "Ikke relevant for forløbet", _SORTERING[INTET])


def _opgave(sag, noegle) -> Opgave | None:
    return next((o for o in sag.opgaver if o.noegle == noegle), None)


### ----- onboarding ----------------------------------------------------------

def kontrakt(sag) -> Prik:
    opgave = _opgave(sag, KONTRAKT)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Underskrevet", "Kontrakten er modtaget retur underskrevet")
    if opgave.status == Opgave.AFVENTER:
        return _prik(ROED, "Sendt", "Sendt til medarbejderen – afventer underskrift")
    return _prik(ROED, "Ikke sendt", "Kontrakten er ikke sendt endnu")


def udstyr(sag) -> Prik:
    """Ud fra de sendte poster i behovet; en udført opgave er altid grøn."""
    opgave = _opgave(sag, UDSTYR)
    poster = sag.behov.udstyrsposter()
    if opgave is None or opgave.status == Opgave.UNDTAGET or not poster:
        return IKKE_RELEVANT
    sendt = set(sag.behov.sendte_poster())
    linjer = [f"{'✓' if n in sendt else '○'}  {tekst}" for n, tekst in poster]
    tip = "\n".join(linjer)
    if opgave.status == Opgave.UDFOERT or len(sendt) == len(poster):
        return _prik(GROEN, "Sendt", tip)
    if sendt:
        return _prik(GUL, f"{len(sendt)}/{len(poster)} sendt", tip)
    return _prik(ROED, "Ikke sendt", tip)


def oplaering(sag) -> Prik:
    opgave = _opgave(sag, OPLAERING)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    tidspunkt = opgave.planlagt.replace("T", " ")[:16] if opgave.planlagt else ""
    tip = f"Oplæringsdag: {tidspunkt or 'ikke aftalt'} · {opgave.status}"
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Fastlagt", tip)
    if opgave.status == Opgave.AFVENTER:
        return _prik(ROED, "Afventer", tip)
    return _prik(ROED, "Ikke fastlagt", tip)


### ----- offboarding ---------------------------------------------------------

def nav_opgave(sag) -> Opgave | None:
    """Standardskabelonens "Er lukket i NAV?" (nøgle eller navn – ældre skabeloner
    har ingen nøgle)."""
    return _opgave(sag, NAV) or next((o for o in sag.opgaver if "NAV" in o.navn), None)


def nav(sag) -> Prik:
    opgave = nav_opgave(sag)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Lukket", "Medarbejderen er lukket i NAV")
    return _prik(ROED, "Åben", "Medarbejderen er ikke lukket i NAV endnu")


def udstyrsopgaver(sag) -> list[Opgave]:
    """Afleveringsopgaverne: dem med udstyr (tankkort, telefon, tøj …)."""
    return [o for o in sag.opgaver if o.udstyr and o.status != Opgave.UNDTAGET]


def udstyr_retur(sag) -> Prik:
    opgaver = udstyrsopgaver(sag)
    if not opgaver:
        return IKKE_RELEVANT
    afleveret = [o for o in opgaver if o.status == Opgave.UDFOERT]
    tip = "\n".join(f"{'✓' if o.status == Opgave.UDFOERT else '○'}  {o.udstyr}"
                    for o in opgaver)
    if len(afleveret) == len(opgaver):
        return _prik(GROEN, "Retur", tip)
    if afleveret:
        return _prik(GUL, f"{len(afleveret)}/{len(opgaver)} retur", tip)
    return _prik(ROED, "Ikke retur", tip)
