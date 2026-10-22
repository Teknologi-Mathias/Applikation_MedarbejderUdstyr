"""Central konfiguration af den kommende Supabase/PostgreSQL-database.

Alle databaseindstillinger læses HER og kun her – fra miljøvariabler (se
.env.example i projektroden). Ingen URL'er eller nøgler andre steder i koden.

Sikkerhed:
- Desktopklienten må KUN kende projektets URL og den offentlige
  "anon"/"publishable" nøgle. Adgang til data styres af brugerens login
  (Supabase Auth) og Row Level Security-politikker i databasen.
- En service_role-nøgle, databaseadgangskode eller anden privilegeret
  hemmelighed må aldrig ligge i Windows-programmet. Config afviser derfor
  miljøvariabler, der ligner sådanne hemmeligheder.
"""
import os
from dataclasses import dataclass

_FORBUDTE = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "DATABASE_PASSWORD",
             "POSTGRES_PASSWORD")


class KonfigurationsFejl(Exception):
    pass


@dataclass(frozen=True)
class DatabaseKonfiguration:
    url: str
    anon_noegle: str
    skema: str = "public"

    @property
    def er_konfigureret(self) -> bool:
        return bool(self.url and self.anon_noegle)


def hent_konfiguration(miljoe=None) -> DatabaseKonfiguration:
    """Læser konfigurationen fra miljøet (eller den givne dict, til test)."""
    miljoe = os.environ if miljoe is None else miljoe
    forbudte = [navn for navn in _FORBUDTE if miljoe.get(navn)]
    if forbudte:
        raise KonfigurationsFejl(
            f"{', '.join(forbudte)} må ikke være sat for desktopklienten. Privilegerede "
            "nøgler hører kun hjemme på en server – brug den offentlige anon-nøgle og RLS."
        )
    return DatabaseKonfiguration(
        url=miljoe.get("INBASE_SUPABASE_URL", "").strip(),
        anon_noegle=miljoe.get("INBASE_SUPABASE_ANON_KEY", "").strip(),
        skema=miljoe.get("INBASE_SUPABASE_SCHEMA", "public").strip() or "public",
    )
