"""Fælles kald til Supabase: fejloversættelse og sideinddeling.

Alle Supabase-repositories kalder databasen gennem kald() og hent_alle(), så
netværks-, rettigheds- og konfliktfejl bliver til de samme typede fejl som
JSON-lagringen (app/repositories/fejl.py). Der forsøges aldrig automatisk
igen på en skrivning – en gentaget oprettelse kunne ellers give dubletter.
"""
import logging
from contextlib import contextmanager

import httpx

from app.repositories.fejl import (
    DataFejl,
    KonfliktFejl,
    OfflineFejl,
    SessionUdloebetFejl,
    ValideringsFejl,
)

log = logging.getLogger(__name__)

# PostgREST returnerer højst så mange raekker pr. kald (Supabase: "Max rows").
SIDESTOERRELSE = 500

_INGEN_FORBINDELSE = (
    "Der er ingen forbindelse til databasen (Supabase). Tjek internetforbindelsen "
    "og prøv igen. Intet er gemt lokalt – IN-BASE kræver forbindelse."
)
_SESSION_UDLOEBET = "Din session er udløbet. Log på igen for at fortsætte."


def _er_sessionsfejl(fejl) -> bool:
    """Auth-fejl, der betyder, at sessionen ikke (længere) kan bruges."""
    tekst = f"{type(fejl).__name__} {getattr(fejl, 'message', '')}".lower()
    return getattr(fejl, "status", None) in (401, 403) or "session" in tekst \
        or "refresh" in tekst or "jwt" in tekst


def oversaet(fejl: Exception, handling: str) -> Exception:
    """Oversætter en fejl fra supabase-py/httpx til en typet fejl."""
    from postgrest.exceptions import APIError
    from supabase_auth.errors import AuthError
    from supabase_functions.errors import FunctionsError

    if isinstance(fejl, (httpx.TransportError, httpx.TimeoutException)):
        return OfflineFejl(_INGEN_FORBINDELSE)
    if isinstance(fejl, APIError):
        kode, besked = str(fejl.code or ""), fejl.message or str(fejl)
        if kode == "IB409":
            return KonfliktFejl(besked)
        if kode == "IB422":
            return ValideringsFejl(besked)
        if kode == "IB403":
            return DataFejl(besked)
        if kode == "42501":
            return DataFejl(f"Du har ikke rettighed til at {handling}.")
        if kode in ("PGRST301", "PGRST302", "PGRST303") or "JWT" in besked:
            return SessionUdloebetFejl(_SESSION_UDLOEBET)
        if kode == "23505":
            return ValideringsFejl(f"Findes allerede ({besked}).")
        if kode.startswith("23"):
            return DataFejl(f"Databasen afviste ændringen ({besked}).")
        return DataFejl(f"Databasefejl ved {handling}: {besked}")
    if isinstance(fejl, FunctionsError):
        status = getattr(fejl, "status", None)
        if status in (400, 404, 409, 422):
            return ValideringsFejl(fejl.message)
        if status == 401:
            return SessionUdloebetFejl(_SESSION_UDLOEBET)
        if status == 403:
            return DataFejl(f"Ingen adgang: {fejl.message}")
        return DataFejl(f"{handling.capitalize()} mislykkedes: {fejl.message}")
    if isinstance(fejl, AuthError):
        if _er_sessionsfejl(fejl):
            return SessionUdloebetFejl(_SESSION_UDLOEBET)
        return DataFejl(f"Login-fejl ved {handling}: {fejl.message}")
    return DataFejl(f"Uventet fejl ved {handling}: {fejl}")


@contextmanager
def kald(handling: str):
    """with kald("gemme sagen"): ... – oversætter fejl og logger dem."""
    try:
        yield
    except (DataFejl, ValideringsFejl):
        raise
    except Exception as fejl:
        typet = oversaet(fejl, handling)
        niveau = logging.WARNING if isinstance(typet, (KonfliktFejl, ValideringsFejl)) \
            else logging.ERROR
        log.log(niveau, "Supabase-fejl ved %s: %r", handling, fejl)
        raise typet from fejl


def hent_alle(forespoergsel, handling: str) -> list[dict]:
    """Henter alle raekker i sider. forespoergsel: () -> ny query (med .order())."""
    raekker, start = [], 0
    with kald(handling):
        while True:
            svar = forespoergsel().range(start, start + SIDESTOERRELSE - 1).execute()
            side = svar.data or []
            raekker.extend(side)
            if len(side) < SIDESTOERRELSE:
                return raekker
            start += SIDESTOERRELSE
