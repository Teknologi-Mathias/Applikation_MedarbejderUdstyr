"""Central konfiguration af datakilden (Supabase eller lokal JSON).

Alle databaseindstillinger læses HER og kun her. Kilder, i prioriteret orden:

1. Rigtige miljøvariabler (fx sat i Windows).
2. %APPDATA%\\IN-BASE\\.env – den færdige Windows-app (filen indlejres ALDRIG
   i .exe-filen; den ligger hos brugeren og kan udskiftes).
3. .env i projektmappen – kun når programmet køres fra kildekoden.

Nøgler:
  INBASE_BACKEND           supabase | json   (tom = supabase, hvis URL+nøgle er sat)
  INBASE_SUPABASE_URL      https://<projekt>.supabase.co
  INBASE_SUPABASE_ANON_KEY projektets offentlige publishable/anon-nøgle
  INBASE_SUPABASE_SCHEMA   public (standard)

Sikkerhed:
- Desktopklienten må KUN kende projektets URL og den offentlige nøgle.
  Adgang til data styres af brugerens login (Supabase Auth) og RLS.
- service_role/secret-nøgler og databaseadgangskoder afvises – også hvis de
  ved en fejl er indsat som INBASE_SUPABASE_ANON_KEY.
- Der skiftes aldrig stiltiende til JSON: JSON kræver INBASE_BACKEND=json.
"""
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure import stier

BACKEND_SUPABASE = "supabase"
BACKEND_JSON = "json"

_FORBUDTE = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_SECRET_KEY",
             "INBASE_SUPABASE_SERVICE_KEY", "DATABASE_PASSWORD", "POSTGRES_PASSWORD",
             "SUPABASE_DB_PASSWORD")


class KonfigurationsFejl(Exception):
    pass


@dataclass(frozen=True)
class DatabaseKonfiguration:
    url: str
    anon_noegle: str
    skema: str = "public"
    backend: str = BACKEND_SUPABASE
    kilder: tuple = ()          # hvilke .env-filer der blev læst (til fejlbeskeder)

    @property
    def er_konfigureret(self) -> bool:
        return bool(self.url and self.anon_noegle)


def env_filer() -> list[Path]:
    """De .env-filer, der læses (vigtigste først)."""
    filer = [stier.KONFIG_FIL]
    if not stier.ER_FROSSET:
        filer.append(stier.PROGRAM_MAPPE / ".env")
    return filer


def _laes_env_fil(fil: Path) -> dict:
    from dotenv import dotenv_values
    # utf-8-sig: filen må gerne være gemt med BOM (fx "UTF-8 med BOM" i Notesblok).
    return {k: v for k, v in dotenv_values(fil, encoding="utf-8-sig").items() if v is not None}


def indlaes_miljoe(miljoe=None, filer=None) -> tuple[dict, tuple]:
    """Fletter .env-filer og miljøvariabler (miljøet vinder). Returnerer (værdier, læste filer)."""
    samlet, laest = {}, []
    for fil in reversed(list(env_filer() if filer is None else filer)):
        if Path(fil).is_file():
            samlet.update(_laes_env_fil(Path(fil)))
            laest.append(str(fil))
    samlet.update(os.environ if miljoe is None else miljoe)
    return samlet, tuple(reversed(laest))


def _jwt_rolle(noegle: str) -> str:
    """Rollen i en (legacy) JWT-nøgle, fx "anon" eller "service_role"."""
    try:
        payload = noegle.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("role", ""))
    except (IndexError, ValueError):
        return ""


def tjek_offentlig_noegle(noegle: str) -> None:
    if noegle.startswith("sb_secret_") or (
        noegle.startswith("eyJ") and _jwt_rolle(noegle) not in ("", "anon")
    ):
        raise KonfigurationsFejl(
            "INBASE_SUPABASE_ANON_KEY er en privilegeret (secret/service_role) nøgle. "
            "Desktopprogrammet må kun bruge projektets publishable/anon-nøgle."
        )


def hent_konfiguration(miljoe=None, filer=None) -> DatabaseKonfiguration:
    """Læser og validerer konfigurationen.

    miljoe: dict i stedet for os.environ (tests). filer: liste af .env-filer
    (tests; [] = ingen filer).
    """
    vaerdier, laest = indlaes_miljoe(miljoe, filer)
    forbudte = [navn for navn in _FORBUDTE if vaerdier.get(navn)]
    if forbudte:
        raise KonfigurationsFejl(
            f"{', '.join(forbudte)} må ikke være sat for desktopklienten. Privilegerede "
            "nøgler hører kun hjemme på en server – brug den offentlige anon-nøgle og RLS."
        )
    url = vaerdier.get("INBASE_SUPABASE_URL", "").strip().rstrip("/")
    noegle = vaerdier.get("INBASE_SUPABASE_ANON_KEY", "").strip()
    if noegle:
        tjek_offentlig_noegle(noegle)
    backend = vaerdier.get("INBASE_BACKEND", "").strip().lower()
    if backend not in ("", BACKEND_SUPABASE, BACKEND_JSON):
        raise KonfigurationsFejl(f"INBASE_BACKEND skal være 'supabase' eller 'json' (ikke '{backend}').")
    if url and not url.startswith("https://") and not url.startswith("http://localhost") \
            and not url.startswith("http://127.0.0.1"):
        raise KonfigurationsFejl("INBASE_SUPABASE_URL skal starte med https://.")
    return DatabaseKonfiguration(
        url=url,
        anon_noegle=noegle,
        skema=vaerdier.get("INBASE_SUPABASE_SCHEMA", "public").strip() or "public",
        backend=backend or BACKEND_SUPABASE,
        kilder=laest,
    )


def mangler_tekst(konfig: DatabaseKonfiguration) -> str:
    """Forklaring til brugeren, når Supabase ikke er konfigureret."""
    return (
        "IN-BASE er ikke forbundet til databasen.\n\n"
        f"Opret filen\n{stier.KONFIG_FIL}\nmed indholdet:\n\n"
        "INBASE_SUPABASE_URL=https://<projekt>.supabase.co\n"
        "INBASE_SUPABASE_ANON_KEY=<offentlig publishable-nøgle>\n\n"
        "Få værdierne af din administrator. Brug aldrig en secret/service_role-nøgle."
    )
