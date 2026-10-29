"""Den bruger, der er logget ind i denne kørsel af programmet."""
from typing import Optional

from app.domain import adgang
from app.services.auth_service import ROLLE_ADMIN

_aktiv: Optional[dict] = None


def log_ind(bruger: dict) -> None:
    global _aktiv
    _aktiv = dict(bruger)


def log_ud() -> None:
    global _aktiv
    _aktiv = None


def bruger() -> Optional[dict]:
    return _aktiv


def er_admin() -> bool:
    return bool(_aktiv) and _aktiv.get("rolle") == ROLLE_ADMIN


def har_adgang(modul: Optional[str]) -> bool:
    """Må den aktuelle bruger se modulet (app/domain/adgang.py)? None = altid åbent."""
    return adgang.har_adgang(_aktiv, modul)


def afdelinger() -> tuple:
    """Den aktuelle brugers afdelinger (til "Min afdeling" i Teamoverblikket)."""
    return adgang.afdelinger_for(_aktiv)


def brugernavn() -> Optional[str]:
    return _aktiv["brugernavn"] if _aktiv else None
