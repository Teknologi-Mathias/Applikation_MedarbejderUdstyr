"""Opretter den FØRSTE administrator i JSON-tilstanden (kun udvikling/test).

    python tools/opret_json_administrator.py MASAN "Mathias Sander"

Adgangskoden spørges der om (vises ikke og gemmes kun som saltet hash).
Virker kun, når der endnu ingen brugere er i datamappen – herefter oprettes
brugere fra IN-BASE. I Supabase-tilstand bruges i stedet
inbase_bootstrap_first_admin() (docs/SUPABASE_OPSAETNING.md).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap import byg_tjenester  # noqa: E402
from app.repositories.fejl import DataFejl, ValideringsFejl  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    brugernavn, navn = argv[0], (argv[1] if len(argv) > 1 else "")
    kode = getpass.getpass("Adgangskode: ")
    if kode != getpass.getpass("Gentag adgangskode: "):
        print("De to adgangskoder er ikke ens.")
        return 1
    try:
        byg_tjenester().auth.opret_foerste_administrator(brugernavn, navn, kode)
    except (ValideringsFejl, DataFejl) as fejl:
        print(f"Ikke oprettet: {fejl}")
        return 1
    print("Første administrator er oprettet. Log på IN-BASE med brugernavnet.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
