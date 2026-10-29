"""IN-BASE – interne processer, samlet ét sted."""
import re

# DEN ENESTE kilde til versionsnummeret (semantisk: MAJOR.MINOR.PATCH).
# Ændres manuelt, når en ny version frigives (se docs/RELEASE.md). Bruges af
# programmet, .exe-filens versionsinfo (MedarbejderUdstyr.spec), installeren
# (installer/IN-BASE.iss via scripts/build_windows.ps1) og buildrapporten.
### Skriv: ( .\scripts\build_windows.ps1  )

__version__ = "0.9.4"

VERSION = f"V{__version__}"   # visning i programmet, fx "V0.7.1"

# Den databaseskemaversion, klienten kræver (schema_migrations, migrering 019).
# Hæves, når klienten afhænger af en ny migrering – ellers forsvinder nye felter
# lydløst i en ældre database. Se docs/RELEASE.md.
KRAEVET_SKEMA = 19

APP_NAVN = "IN-BASE"
APP_SLOGAN = "Administrationsværktøj, prototype."
APP_BESKRIVELSE = (
    "Et fælles sted til onboarding og offboarding "
    "Skaber sammenhæng mellem "
)

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_tupel(version: str = __version__) -> tuple[int, int, int]:
    """"0.7.1" -> (0, 7, 1). ValueError, hvis versionen ikke er MAJOR.MINOR.PATCH."""
    match = _SEMVER.match(str(version).strip())
    if not match:
        raise ValueError(f"Ugyldigt versionsnummer '{version}' – brug fx 1.0.0.")
    return tuple(int(del_) for del_ in match.groups())
