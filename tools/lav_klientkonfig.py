"""Laver den klientkonfiguration, installeren lægger i %APPDATA%\\IN-BASE\\.env.

    python tools/lav_klientkonfig.py <kilde.env> <mål.env>

Læser KUN INBASE_SUPABASE_URL og INBASE_SUPABASE_ANON_KEY fra kilden (fx
projektets .env) og skriver dem – og intet andet – til målfilen. Testlogin,
adgangskoder og andre nøgler kommer aldrig med. Valideringen er den samme som
programmets (app/infrastructure/database/config.py), så en secret- eller
service_role-nøgle afvises. Bruges af scripts/build_windows.ps1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.database.config import (  # noqa: E402
    BACKEND_SUPABASE,
    KonfigurationsFejl,
    hent_konfiguration,
)


def lav(kilde: Path, maal: Path) -> str:
    """Skriver målfilen og returnerer projektets URL. KonfigurationsFejl ved fejl."""
    if not kilde.is_file():
        raise KonfigurationsFejl(f"Konfigurationskilden findes ikke: {kilde}")
    konfig = hent_konfiguration(miljoe={}, filer=[kilde])   # kun filen – ikke pc'ens miljø
    if not konfig.er_konfigureret:
        raise KonfigurationsFejl(
            f"{kilde} mangler INBASE_SUPABASE_URL og/eller INBASE_SUPABASE_ANON_KEY.")
    if konfig.backend != BACKEND_SUPABASE:
        raise KonfigurationsFejl(f"{kilde} vælger INBASE_BACKEND={konfig.backend} – kræver supabase.")
    if not konfig.url.startswith("https://"):
        raise KonfigurationsFejl(f"INBASE_SUPABASE_URL i {kilde} skal starte med https://.")
    maal.parent.mkdir(parents=True, exist_ok=True)
    maal.write_text(
        "# IN-BASE – forbindelse til Supabase (lagt her af installeren).\n"
        "# Kun projektets URL og den OFFENTLIGE publishable-nøgle. Kan rettes efter behov;\n"
        "# installeren overskriver aldrig en eksisterende fil.\n"
        f"INBASE_SUPABASE_URL={konfig.url}\n"
        f"INBASE_SUPABASE_ANON_KEY={konfig.anon_noegle}\n",
        encoding="utf-8",
    )
    return konfig.url


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        print(lav(Path(sys.argv[1]), Path(sys.argv[2])))
    except KonfigurationsFejl as fejl:
        print(f"FEJL: {fejl}", file=sys.stderr)
        sys.exit(1)
