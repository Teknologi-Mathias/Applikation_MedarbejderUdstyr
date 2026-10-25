"""Applikationens opsætning (composition root).

Her – og kun her – vælges konkrete implementeringer: hvilke repositories
services skal bruge. Brugerfladen får et færdigt Tjenester-objekt og kender
aldrig til JSON-filer eller databaser.

- byg_fra_konfiguration(): det programmet bruger. Supabase er standard; JSON
  kun ved INBASE_BACKEND=json. Mangler Supabase-konfigurationen, kastes en
  KonfigurationsFejl – der skiftes ALDRIG stiltiende til (gamle) JSON-data.
- byg_supabase_tjenester(): services oven på app/repositories/supabase/.
- byg_tjenester(): services oven på app/repositories/json/ (tests og udvikling).
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app import session
from app.domain import historik
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.infrastructure import stier
from app.infrastructure.database.config import (
    BACKEND_JSON,
    BACKEND_SUPABASE,
    DatabaseKonfiguration,
    KonfigurationsFejl,
    hent_konfiguration,
    mangler_tekst,
)
from app.repositories.fejl import DataFejl
from app.repositories.json.bruger_repository import JsonBrugerRepository
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import tjek_skriveadgang
from app.repositories.json.opsaetning_repository import (
    JsonIndstillingRepository,
    JsonLokalFil,
    JsonPraeferenceRepository,
    JsonSkabelonRepository,
)
from app.repositories.json.sag_repository import JsonSagRepository
from app.services.auth_service import AuthService, SupabaseAuthService
from app.services.backup_service import BackupService
from app.services.indstillinger_service import IndstillingerService
from app.services.lagring_service import LagringService, OnlineLagring
from app.services.offboarding_service import OffboardingService
from app.services.onboarding_service import OnboardingService
from app.services.paamindelser import PaamindelsesService
from app.services.rapport_service import RapportService
from app.services.skabelon_service import SkabelonService

log = logging.getLogger(__name__)

SAGSTYPER = {
    Medarbejder.PROCES: (Medarbejder, stier.OFFBOARDING_AKTIVE, stier.OFFBOARDING_ARKIV),
    OnboardingForloeb.PROCES: (OnboardingForloeb, stier.ONBOARDING_AKTIVE, stier.ONBOARDING_ARKIV),
}


@dataclass
class Tjenester:
    backend: str                          # "supabase" eller "json"
    datakilde: Optional[Datakilde]        # kun JSON
    lagring: "LagringService | OnlineLagring"
    auth: "AuthService | SupabaseAuthService"
    indstillinger: IndstillingerService
    skabeloner: SkabelonService
    offboarding: OffboardingService
    onboarding: OnboardingService
    backup: Optional[BackupService]       # kun JSON (Supabase tager selv backup)
    paamindelser: PaamindelsesService
    rapporter: RapportService

    def modul(self, proces: str):
        return self.onboarding if proces == OnboardingForloeb.PROCES else self.offboarding


def byg_fra_konfiguration(konfig: DatabaseKonfiguration | None = None) -> Tjenester:
    """Vælger backend ud fra konfigurationen (app/infrastructure/database/config.py)."""
    konfig = konfig or hent_konfiguration()
    if konfig.backend == BACKEND_JSON:
        log.warning("JSON-tilstand valgt (INBASE_BACKEND=json) – lokal datamappe, ikke Supabase")
        return byg_tjenester()
    if not konfig.er_konfigureret:
        raise KonfigurationsFejl(mangler_tekst(konfig))
    from app.infrastructure.database.connection import opret_klient
    return byg_supabase_tjenester(opret_klient(konfig), stier.LOKAL_MAPPE,
                                  f"Supabase ({konfig.url.removeprefix('https://')})")


def byg_supabase_tjenester(klient, lokal_mappe: Path, kilde: str = "Supabase") -> Tjenester:
    """Services oven på Supabase. klient: supabase-klienten (eller en testklient)."""
    from app.repositories.supabase.konto_repository import SupabaseKontoRepository
    from app.repositories.supabase.opsaetning_repository import (
        SupabaseIndstillingRepository,
        SupabasePraeferenceRepository,
        SupabaseSkabelonRepository,
    )
    from app.repositories.supabase.sag_repository import SupabaseSagRepository

    historik.saet_brugerkilde(session.brugernavn)
    return Tjenester(
        backend=BACKEND_SUPABASE,
        datakilde=None,
        lagring=OnlineLagring(kilde),
        auth=SupabaseAuthService(SupabaseKontoRepository(klient)),
        indstillinger=IndstillingerService(SupabaseIndstillingRepository(klient),
                                           SupabasePraeferenceRepository(klient)),
        skabeloner=SkabelonService(SupabaseSkabelonRepository(klient)),
        offboarding=OffboardingService(SupabaseSagRepository(klient, Medarbejder)),
        onboarding=OnboardingService(SupabaseSagRepository(klient, OnboardingForloeb)),
        backup=None,
        paamindelser=PaamindelsesService(
            JsonLokalFil(lokal_mappe / stier.NOTIFIKATIONSLOG_FIL.name)
        ),
        rapporter=RapportService(),
    )


def byg_tjenester(central_mappe: Path = stier.CENTRAL_DATA_MAPPE,
                  lokal_mappe: Path = stier.LOKAL_MAPPE) -> Tjenester:
    """JSON-tilstanden. Mapperne kan angives (bruges af tests)."""
    historik.saet_brugerkilde(session.brugernavn)
    konfig = JsonLokalFil(lokal_mappe / stier.LAGRING_FIL.name)
    datakilde = Datakilde(central_mappe, lokal_mappe / stier.OFFLINE_MAPPE.name,
                          offline=bool(konfig.hent().get("offline")))
    sag_repos = {
        proces: JsonSagRepository(datakilde, sagstype, aktiv, arkiv)
        for proces, (sagstype, aktiv, arkiv) in SAGSTYPER.items()
    }
    indstillinger = IndstillingerService(
        JsonIndstillingRepository(datakilde),
        JsonPraeferenceRepository(lokal_mappe / stier.PRAEFERENCE_FIL.name),
    )
    return Tjenester(
        backend=BACKEND_JSON,
        datakilde=datakilde,
        lagring=LagringService(datakilde, konfig, SAGSTYPER),
        auth=AuthService(JsonBrugerRepository(datakilde)),
        indstillinger=indstillinger,
        skabeloner=SkabelonService(JsonSkabelonRepository(datakilde)),
        offboarding=OffboardingService(sag_repos[Medarbejder.PROCES]),
        onboarding=OnboardingService(sag_repos[OnboardingForloeb.PROCES]),
        backup=BackupService(datakilde, indstillinger),
        paamindelser=PaamindelsesService(
            JsonLokalFil(lokal_mappe / stier.NOTIFIKATIONSLOG_FIL.name)
        ),
        rapporter=RapportService(),
    )


def klargoer(tjenester: Tjenester) -> None:
    """Kaldes én gang ved opstart (før log på). Kaster DataFejl ved problemer.

    Supabase: intet – skemaet ændres aldrig af programmet, og intet importeres.
    JSON: tjekker skriveadgang og opdaterer ældre JSON-format i datamappen
    (efter en backup). Der importeres aldrig data fra andre steder.
    """
    if tjenester.backend == BACKEND_SUPABASE:
        return
    datakilde = tjenester.datakilde
    if datakilde.offline:
        if not tjenester.lagring.offline_kopi_findes():
            raise DataFejl("Offline-tilstand er valgt, men der findes ingen lokal kopi.")
        log.info("Starter offline på %s", datakilde.offline_mappe)
        return
    try:
        tjek_skriveadgang(datakilde.central_mappe)
    except OSError as fejl:
        raise DataFejl(
            f"Programmet kan ikke skrive i datamappen:\n{datakilde.central_mappe}\n\n"
            f"({fejl})\n\n"
            "Ligger programmet i C:\\Program Files, kræver det "
            "administratorrettigheder. Flyt i stedet programmet til en mappe "
            "som C:\\IN-BASE. Ligger data på et netværksdrev, så tjek forbindelsen."
        ) from fejl
    _migrer(tjenester)
    tjenester.auth.klargoer()


def _migrer(tjenester: Tjenester) -> None:
    repos = [tjenester.offboarding.repo, tjenester.onboarding.repo]
    if not any(repo.kraever_migrering() for repo in repos):
        return
    # Sikkerhedskopi FØR ældre data skrives i det nye format.
    info = tjenester.backup.tag_backup("foer-migrering")
    log.info("Backup før migrering: %s", info.sti)
    for repo in repos:
        repo.migrer()
