"""Fælles for administratorværktøjerne i tools/: log på med IN-BASE-brugernavn og -kode.

Bruges af signeringsnoegle.py og udgiv_version.py. Forbindelsen er den samme
som programmets (%APPDATA%\\IN-BASE\\.env eller projektets .env) – kun med den
offentlige nøgle; rettighederne kommer fra administratorens login og RLS.
"""
import getpass
import sys
from pathlib import Path

ROD = Path(__file__).resolve().parents[1]
if str(ROD) not in sys.path:
    sys.path.insert(0, str(ROD))


class Stop(Exception):
    """Fejl, der vises for brugeren uden traceback."""


def log_ind(formaal: str):
    """Supabase-klient logget på som aktiv administrator. formaal: "bygge styrings-appen"."""
    from app.infrastructure.database.connection import opret_klient
    from app.repositories.fejl import ForkertLoginFejl
    from app.repositories.supabase.konto_repository import SupabaseKontoRepository

    klient = opret_klient()
    print("Log på med din IN-BASE-administratorkonto.")
    brugernavn = input("Brugernavn: ").strip()
    kode = getpass.getpass("Adgangskode: ")
    try:
        SupabaseKontoRepository(klient).log_ind(brugernavn, kode)
    except ForkertLoginFejl as fejl:
        raise Stop("Forkert brugernavn eller adgangskode.") from fejl
    if not klient.rpc("inbase_is_admin").execute().data:
        raise Stop(f"Kun administratorer kan {formaal}.")
    return klient
