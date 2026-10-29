"""Statusfelter: forløbets vigtigste skridt som én farve pr. kolonne i "Aktive forløb".

Feltet er en genvej – det samler opgaverne til grøn/gul/rød/grå, så man ikke skal
åbne forløbet for at se, hvor det står. Det ændres med en drop down-menu direkte i
tabellen (app/ui/modul_controller.py). Tonen er et navn fra temaet (groen, gul,
roed, intet = grå); teksten står altid ved siden af farven.

    Onboarding   Kontrakt            rød = ikke sendt / sendt     grøn = modtaget retur
                 Udstyr              rød = intet sendt   gul = delvist   grøn = alt sendt
                 Opfølgning          rød = ikke afholdt           grøn = afholdt
    Offboarding  Tankkort spærret    grå = ikke relevant  rød = ikke behandlet  grøn = behandlet
                 Tøj og udstyr       rød = intet afleveret  gul = delvist  grøn = alt afleveret
                 Telefon & SIM-kort  rød = intet afleveret        grøn = alt afleveret
                 Lukket i NAV?       rød = nej                    grøn = ja

Onboardingens opgaver findes på nøgle (standardskabelonen, migrering 018).
Offboardingens skabeloner har ingen nøgler – opgaverne findes på udstyrsfeltet
(Tankkort, Telefon og SIM-kort, Tøj …) og NAV-opgaven på navnet. Mangler en
opgave i forløbet (fx en egen skabelon), vises feltet som "–".
"""
from dataclasses import dataclass

from app.domain.opgave import Opgave

GROEN, GUL, ROED, INTET = "groen", "gul", "roed", "intet"

# Kolonnernes nøgler (klik-handling i tabellen).
KONTRAKT = "kontrakt"            # = opgavenøglen i standardskabelonen
UDSTYR = "udstyr"                # = opgavenøglen i standardskabelonen
OPFOELGNING = "opfoelgning"      # = opgavenøglen i standardskabelonen
TANKKORT = "tankkort"
TOEJ = "toej"
TELEFON = "telefon"
NAV = "nav"

# Begrundelse, når tankkortet markeres "Ikke relevant" fra tabellen.
IKKE_RELEVANT_BEGRUNDELSE = "Ikke relevant – valgt i tabellen"


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


def _liste(opgaver, tekst) -> str:
    return "\n".join(f"{'✓' if o.status == Opgave.UDFOERT else '○'}  {tekst(o)}" for o in opgaver)


### ----- onboarding ----------------------------------------------------------

def kontrakt(sag) -> Prik:
    opgave = _opgave(sag, KONTRAKT)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Modtaget retur", "Kontrakten er modtaget retur underskrevet")
    if opgave.status == Opgave.AFVENTER:
        return _prik(ROED, "Sendt", "Sendt til medarbejderen – afventer underskrift")
    return _prik(ROED, "Ikke sendt", "Kontrakten er ikke sendt endnu")


def udstyr(sag) -> Prik:
    """Ud fra de sendte poster i behovet (tøj, telefon, mail); en udført opgave er grøn."""
    opgave = _opgave(sag, UDSTYR)
    poster = sag.behov.udstyrsposter()
    if opgave is None or opgave.status == Opgave.UNDTAGET or not poster:
        return IKKE_RELEVANT
    sendt = set(sag.behov.sendte_poster())
    tip = "\n".join(f"{'✓' if n in sendt else '○'}  {tekst}" for n, tekst in poster)
    if opgave.status == Opgave.UDFOERT or len(sendt) == len(poster):
        return _prik(GROEN, "Alt udstyr sendt", tip)
    if sendt:
        return _prik(GUL, "Delvist sendt", tip)
    return _prik(ROED, "Intet udstyr sendt", tip)


def opfoelgning(sag) -> Prik:
    opgave = _opgave(sag, OPFOELGNING)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Afholdt", "Opfølgningssamtalen er afholdt (Merch)")
    return _prik(ROED, "Ikke afholdt", "Opfølgningssamtalen er ikke afholdt endnu (Merch)")


### ----- offboarding ---------------------------------------------------------

def _er_tankkort(o: Opgave) -> bool:
    return "tankkort" in o.udstyr.lower()


def _er_telefon(o: Opgave) -> bool:
    navn = o.udstyr.lower()
    return "telefon" in navn or "sim" in navn


def tankkort_opgaver(sag) -> list[Opgave]:
    """Også undtagne – så "Ikke relevant" kan vises og fortrydes."""
    return [o for o in sag.opgaver if o.udstyr and _er_tankkort(o)]


def telefon_opgaver(sag) -> list[Opgave]:
    return [o for o in sag.opgaver
            if o.udstyr and _er_telefon(o) and o.status != Opgave.UNDTAGET]


def toej_opgaver(sag) -> list[Opgave]:
    """Tøj og øvrigt udstyr: alt med udstyr, der ikke er tankkort eller telefon."""
    return [o for o in sag.opgaver if o.udstyr and o.status != Opgave.UNDTAGET
            and not _er_tankkort(o) and not _er_telefon(o)]


def nav_opgave(sag) -> Opgave | None:
    """Standardskabelonens "Er lukket i NAV?" (nøgle eller navn – ældre skabeloner
    har ingen nøgle)."""
    return _opgave(sag, NAV) or next((o for o in sag.opgaver if "NAV" in o.navn), None)


def tankkort(sag) -> Prik:
    opgaver = tankkort_opgaver(sag)
    relevante = [o for o in opgaver if o.status != Opgave.UNDTAGET]
    if not relevante:
        return (_prik(INTET, "Ikke relevant", "Medarbejderen har ikke haft tankkort")
                if opgaver else IKKE_RELEVANT)
    tip = _liste(relevante, lambda o: o.navn)
    if all(o.status == Opgave.UDFOERT for o in relevante):
        return _prik(GROEN, "Behandlet", tip)
    return _prik(ROED, "Ikke behandlet", tip)


def toej(sag) -> Prik:
    opgaver = toej_opgaver(sag)
    if not opgaver:
        return IKKE_RELEVANT
    afleveret = [o for o in opgaver if o.status == Opgave.UDFOERT]
    tip = _liste(opgaver, lambda o: o.udstyr)
    if len(afleveret) == len(opgaver):
        return _prik(GROEN, "Alt afleveret", tip)
    if afleveret:
        return _prik(GUL, "Delvist afleveret", tip)
    return _prik(ROED, "Intet afleveret", tip)


def telefon(sag) -> Prik:
    opgaver = telefon_opgaver(sag)
    if not opgaver:
        return IKKE_RELEVANT
    tip = _liste(opgaver, lambda o: o.udstyr)
    if all(o.status == Opgave.UDFOERT for o in opgaver):
        return _prik(GROEN, "Alt afleveret", tip)
    return _prik(ROED, "Intet afleveret", tip)


def nav(sag) -> Prik:
    opgave = nav_opgave(sag)
    if opgave is None or opgave.status == Opgave.UNDTAGET:
        return IKKE_RELEVANT
    if opgave.status == Opgave.UDFOERT:
        return _prik(GROEN, "Ja", "Medarbejderen er lukket i NAV")
    return _prik(ROED, "Nej", "Medarbejderen er ikke lukket i NAV endnu")
