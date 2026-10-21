"""Brugerkartotek: brugere, roller og log på (Data/brugere.json).

BETA: Adgangskoderne gemmes som saltede hashes (PBKDF2), men filen ligger
frit i datamappen og kan redigeres af alle med adgang til den. Det er derfor
ikke en sikker løsning – brug ikke private adgangskoder.

Findes der ingen brugere, oprettes standardbrugeren admin / admin.
"""
import hashlib
import hmac
import secrets
from datetime import datetime

from app.data_manager import gem_json, hent_json
from app.stier import BRUGER_FIL

ROLLE_ADMIN = "Administrator"
ROLLE_BRUGER = "Bruger"
ROLLER = (ROLLE_ADMIN, ROLLE_BRUGER)

STANDARD_BRUGERNAVN = "admin"
STANDARD_KODE = "admin"

_ITERATIONER = 200_000


class BrugerFejl(Exception):
    """En handling på brugerkartoteket er ikke tilladt (vises for brugeren)."""


def _hash(kode, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", kode.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONER
    ).hex()


def _ny_bruger(brugernavn, navn, rolle, kode):
    salt = secrets.token_hex(16)
    return {
        "brugernavn": brugernavn,
        "navn": navn,
        "rolle": rolle,
        "salt": salt,
        "hash": _hash(kode, salt),
        "oprettet": datetime.now().isoformat(timespec="seconds"),
    }


### ----- indlæsning ---------------------------------------------------------

def hent():
    """Alle brugere. Opretter admin/admin, hvis kartoteket er tomt."""
    brugere = [b for b in hent_json(BRUGER_FIL) if isinstance(b, dict) and b.get("brugernavn")]
    if not brugere:
        brugere = [_ny_bruger(STANDARD_BRUGERNAVN, "Administrator", ROLLE_ADMIN, STANDARD_KODE)]
        gem_json(brugere, BRUGER_FIL)
    return brugere


def _find(brugere, brugernavn):
    for bruger in brugere:
        if bruger["brugernavn"].lower() == str(brugernavn).strip().lower():
            return bruger
    return None


def offentlig(bruger):
    """Brugeren uden salt og hash (det, resten af programmet må se)."""
    return {k: v for k, v in bruger.items() if k not in ("salt", "hash")}


### ----- log på -------------------------------------------------------------

def log_ind(brugernavn, kode):
    """Returnerer brugeren ved korrekt brugernavn og kode, ellers None."""
    bruger = _find(hent(), brugernavn)
    if bruger is None or not bruger.get("salt"):
        return None
    if not hmac.compare_digest(_hash(kode, bruger["salt"]), bruger.get("hash", "")):
        return None
    return offentlig(bruger)


def bruger_standardkode():
    """True, hvis standardbrugeren admin stadig har koden admin."""
    bruger = _find(hent(), STANDARD_BRUGERNAVN)
    return bool(bruger and bruger.get("salt")) and hmac.compare_digest(
        _hash(STANDARD_KODE, bruger["salt"]), bruger.get("hash", "")
    )


### ----- administration -----------------------------------------------------

def opret(brugernavn, navn, rolle, kode):
    brugernavn = brugernavn.strip()
    if not brugernavn or " " in brugernavn:
        raise BrugerFejl("Brugernavnet skal udfyldes og må ikke indeholde mellemrum.")
    if rolle not in ROLLER:
        raise BrugerFejl("Ukendt rolle.")
    if len(kode) < 4:
        raise BrugerFejl("Adgangskoden skal være mindst 4 tegn.")
    brugere = hent()
    if _find(brugere, brugernavn):
        raise BrugerFejl(f"Brugernavnet '{brugernavn}' findes allerede.")
    brugere.append(_ny_bruger(brugernavn, navn.strip() or brugernavn, rolle, kode))
    gem_json(brugere, BRUGER_FIL)


def slet(brugernavn, aktuel_brugernavn):
    brugere = hent()
    bruger = _find(brugere, brugernavn)
    if bruger is None:
        raise BrugerFejl("Brugeren findes ikke længere.")
    if bruger["brugernavn"].lower() == str(aktuel_brugernavn).lower():
        raise BrugerFejl("Du kan ikke slette den bruger, du er logget ind med.")
    if bruger["rolle"] == ROLLE_ADMIN and sum(b["rolle"] == ROLLE_ADMIN for b in brugere) <= 1:
        raise BrugerFejl("Der skal altid være mindst én administrator.")
    brugere.remove(bruger)
    gem_json(brugere, BRUGER_FIL)


def skift_kode(brugernavn, kode):
    if len(kode) < 4:
        raise BrugerFejl("Adgangskoden skal være mindst 4 tegn.")
    brugere = hent()
    bruger = _find(brugere, brugernavn)
    if bruger is None:
        raise BrugerFejl("Brugeren findes ikke længere.")
    bruger["salt"] = secrets.token_hex(16)
    bruger["hash"] = _hash(kode, bruger["salt"])
    gem_json(brugere, BRUGER_FIL)
