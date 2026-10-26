"""Adgang pr. modul: hvilke dele af IN-BASE en bruger må se.

Administratorer har altid adgang til alt. For andre brugere gemmes en liste
af moduler på profilen ("moduler"); None betyder standarden (som før
moduladgang fandtes: alt undtagen Telefoner). Dashboard og Indstillinger kan
alle altid se.

Låsen gælder i programmet (menu, sider og hvilke data der hentes). Kun
Telefoner er også låst i databasen (migrering 010), fordi tabellen kun var
åben for administratorer.

Modulnavnene svarer til check-betingelsen i migrering 010.
"""
from typing import Optional

ONBOARDING = "onboarding"
OFFBOARDING = "offboarding"
OENSKER = "oensker"
TELEFONER = "telefoner"

# Modul -> navn (som i menuen).
MODULER = {
    ONBOARDING: "Onboarding - MERCH",
    OFFBOARDING: "Offboarding - HAFRA",
    OENSKER: "Ønsker & Udvikling",
    TELEFONER: "Telefoner (MDM)",
}
STANDARD = (ONBOARDING, OFFBOARDING, OENSKER)


def modul_for_side(noegle: str) -> Optional[str]:
    """Menupunktets nøgle ("on_aktive", "telefoner_arkiv" …) -> modul, eller None (altid åben)."""
    if noegle.startswith("on_"):
        return ONBOARDING
    if noegle.startswith("off_"):
        return OFFBOARDING
    if noegle.startswith("telefoner_"):
        return TELEFONER
    return noegle if noegle in MODULER else None


def moduler_for(bruger: Optional[dict]) -> tuple:
    """De moduler, brugeren har adgang til."""
    if not bruger:
        return ()
    if bruger.get("rolle") == "Administrator":
        return tuple(MODULER)
    valgte = bruger.get("moduler")
    return STANDARD if valgte is None else tuple(m for m in MODULER if m in valgte)


def har_adgang(bruger: Optional[dict], modul: Optional[str]) -> bool:
    return modul is None or modul in moduler_for(bruger)


def normaliser(moduler) -> list[str]:
    """Kendte moduler i fast rækkefølge (ukendte ignoreres)."""
    return [m for m in MODULER if m in set(moduler or ())]
