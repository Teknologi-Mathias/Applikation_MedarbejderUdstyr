"""Forbindelsen til Supabase – oprettes HER og kun her.

opret_klient() bygger én supabase-klient ud fra den centrale konfiguration
(config.py) og genbruger den resten af kørslen. Klienten holder brugerens
session (adgangstoken) i hukommelsen – den skrives ikke til disk – og
fornyer selv tokenet. Repositories i app/repositories/supabase/ får klienten
via bootstrap og opretter aldrig selv en forbindelse.
"""
import logging
import threading

from app.infrastructure.database.config import DatabaseKonfiguration, hent_konfiguration

log = logging.getLogger(__name__)

# Netværkstimeout for PostgREST/Edge Functions (sekunder).
TIMEOUT = 20
# Storage (upload af installeren, tools/udgiv_version.py) må tage længere tid.
TIMEOUT_FIL = 300

_laas = threading.Lock()
_klient = None
_klient_konfig: DatabaseKonfiguration | None = None


class DatabaseIkkeTilgaengelig(Exception):
    """Supabase er ikke konfigureret, eller klienten kan ikke oprettes."""


def opret_klient(konfig: DatabaseKonfiguration | None = None):
    """Den fælles Supabase-klient (oprettes ved første kald)."""
    global _klient, _klient_konfig
    konfig = konfig or hent_konfiguration()
    if not konfig.er_konfigureret:
        raise DatabaseIkkeTilgaengelig(
            "Supabase er ikke konfigureret (INBASE_SUPABASE_URL / INBASE_SUPABASE_ANON_KEY)."
        )
    with _laas:
        if _klient is not None and _klient_konfig == konfig:
            return _klient
        try:
            from supabase import ClientOptions, create_client
            _klient = create_client(
                konfig.url,
                konfig.anon_noegle,
                options=ClientOptions(
                    schema=konfig.skema,
                    auto_refresh_token=True,
                    persist_session=False,
                    postgrest_client_timeout=TIMEOUT,
                    function_client_timeout=TIMEOUT,
                    storage_client_timeout=TIMEOUT_FIL,
                ),
            )
        except Exception as fejl:   # ugyldig URL/nøgle eller manglende pakke
            log.exception("Supabase-klienten kunne ikke oprettes")
            raise DatabaseIkkeTilgaengelig(f"Forbindelsen til Supabase kunne ikke oprettes ({fejl}).") from fejl
        _klient_konfig = konfig
        log.info("Supabase-klient oprettet for %s", konfig.url)
        return _klient


def nulstil_klient() -> None:
    """Glemmer klienten (bruges af tests og ved programafslutning)."""
    global _klient, _klient_konfig
    with _laas:
        _klient, _klient_konfig = None, None
