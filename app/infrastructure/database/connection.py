"""Forbindelse til Supabase/PostgreSQL – IKKE IMPLEMENTERET ENDNU.

Denne fil er det ene sted, hvor en databaseforbindelse skal oprettes.
Den er bevidst ikke implementeret: programmet bruger i dag JSON-lagringen
(app/repositories/json/). Der findes ingen "halv" forbindelse, der ser
aktiv ud – opret_klient() fejler tydeligt, indtil integrationen er bygget
og testet.

Plan (se README.md i denne mappe):
  1. Tilføj afhængigheden `supabase` (supabase-py) til requirements.txt.
  2. Implementér opret_klient(): create_client(konfig.url, konfig.anon_noegle).
  3. Log brugeren ind via Supabase Auth (AuthService får en SupabaseAuth).
  4. Implementér repositories i app/repositories/supabase/ med samme
     grænseflader som app/repositories/base.py.
  5. Vælg de nye repositories i app/bootstrap.py.
"""
from app.infrastructure.database.config import DatabaseKonfiguration, hent_konfiguration


class DatabaseIkkeTilgaengelig(Exception):
    """Databasen er ikke konfigureret eller integrationen er ikke implementeret."""


def opret_klient(konfig: DatabaseKonfiguration | None = None):
    konfig = konfig or hent_konfiguration()
    if not konfig.er_konfigureret:
        raise DatabaseIkkeTilgaengelig(
            "Supabase er ikke konfigureret (INBASE_SUPABASE_URL / INBASE_SUPABASE_ANON_KEY)."
        )
    raise DatabaseIkkeTilgaengelig(
        "Supabase-integrationen er endnu ikke implementeret. Programmet bruger den "
        "lokale JSON-lagring. Se app/infrastructure/database/README.md."
    )
