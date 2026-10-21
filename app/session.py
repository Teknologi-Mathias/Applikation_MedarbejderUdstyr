"""Den bruger, der er logget ind i denne kørsel af programmet."""

_aktiv = None


def log_ind(bruger):
    global _aktiv
    _aktiv = dict(bruger)


def log_ud():
    global _aktiv
    _aktiv = None


def bruger():
    return _aktiv


def er_admin():
    from app.brugere import ROLLE_ADMIN
    return bool(_aktiv) and _aktiv.get("rolle") == ROLLE_ADMIN


def brugernavn():
    return _aktiv["brugernavn"] if _aktiv else None
