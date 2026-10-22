"""Autentificering og brugeradministration.

AuthService er det eneste sted, der kender til adgangskoder. I dag bruges
LokalAuth (saltede PBKDF2-hashes i Data/brugere.json – BETA, filen er ikke
beskyttet). Når Supabase Auth tilsluttes, skal en SupabaseAuth implementere
samme metoder, så login, skift af kode og brugerkartotek virker uændret.
Adgangskoder gemmes aldrig i klartekst.
"""
import hashlib
import hmac
import logging
import secrets

from app.domain.historik import nu
from app.repositories.base import BrugerRepository
from app.repositories.fejl import ValideringsFejl

log = logging.getLogger(__name__)

ROLLE_ADMIN = "Administrator"
ROLLE_BRUGER = "Bruger"
ROLLER = (ROLLE_ADMIN, ROLLE_BRUGER)

STANDARD_BRUGERNAVN = "admin"
STANDARD_KODE = "admin"
MIN_KODE_LAENGDE = 6
_ITERATIONER = 200_000


def _hash(kode: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", kode.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONER
    ).hex()


def offentlig(bruger: dict) -> dict:
    """Brugeren uden salt og hash (det, resten af programmet må se)."""
    return {k: v for k, v in bruger.items() if k not in ("salt", "hash")}


class AuthService:
    def __init__(self, repo: BrugerRepository):
        self.repo = repo

    ### ----- hjælpere -------------------------------------------------------

    def _alle(self) -> list[dict]:
        brugere = self.repo.hent_alle()
        if not brugere:
            # Første opstart: opret standardadministratoren admin/admin.
            log.warning("Ingen brugere fundet – opretter standardbrugeren admin")
            brugere = [self._ny(STANDARD_BRUGERNAVN, "Administrator", ROLLE_ADMIN, STANDARD_KODE)]
            self.repo.gem_alle(brugere)
        return brugere

    @staticmethod
    def _ny(brugernavn, navn, rolle, kode) -> dict:
        salt = secrets.token_hex(16)
        return {"brugernavn": brugernavn, "navn": navn, "rolle": rolle,
                "salt": salt, "hash": _hash(kode, salt), "oprettet": nu()}

    @staticmethod
    def _find(brugere, brugernavn):
        return next((b for b in brugere
                     if b["brugernavn"].lower() == str(brugernavn).strip().lower()), None)

    @staticmethod
    def _kode_passer(bruger: dict, kode: str) -> bool:
        return bool(bruger.get("salt")) and hmac.compare_digest(
            _hash(kode, bruger["salt"]), bruger.get("hash", "")
        )

    @staticmethod
    def valider_ny_kode(kode: str, gentag: str | None = None) -> None:
        if len(kode or "") < MIN_KODE_LAENGDE:
            raise ValideringsFejl(f"Adgangskoden skal være mindst {MIN_KODE_LAENGDE} tegn.")
        if gentag is not None and kode != gentag:
            raise ValideringsFejl("De to adgangskoder er ikke ens.")

    ### ----- log på ---------------------------------------------------------

    def klargoer(self) -> None:
        self._alle()

    def log_ind(self, brugernavn: str, kode: str) -> dict | None:
        bruger = self._find(self._alle(), brugernavn)
        if bruger is None or not self._kode_passer(bruger, kode):
            log.info("Mislykket log på for %r", brugernavn)
            return None
        log.info("Bruger %s logget på", bruger["brugernavn"])
        return offentlig(bruger)

    def brugere(self) -> list[dict]:
        return [offentlig(b) for b in self._alle()]

    ### ----- egen adgangskode -----------------------------------------------

    def skift_egen_kode(self, brugernavn: str, nuvaerende: str, ny: str, gentag: str) -> None:
        brugere = self._alle()
        bruger = self._find(brugere, brugernavn)
        if bruger is None or not self._kode_passer(bruger, nuvaerende):
            raise ValideringsFejl("Den nuværende adgangskode er forkert.")
        self.valider_ny_kode(ny, gentag)
        if ny == nuvaerende:
            raise ValideringsFejl("Den nye adgangskode skal være forskellig fra den gamle.")
        self._saet_kode(brugere, bruger, ny)

    def _saet_kode(self, brugere, bruger, kode) -> None:
        bruger["salt"] = secrets.token_hex(16)
        bruger["hash"] = _hash(kode, bruger["salt"])
        self.repo.gem_alle(brugere)
        log.info("Adgangskode skiftet for %s", bruger["brugernavn"])

    ### ----- administration (kun administratorer) ---------------------------

    def opret(self, brugernavn: str, navn: str, rolle: str, kode: str) -> None:
        brugernavn = (brugernavn or "").strip()
        if not brugernavn or " " in brugernavn:
            raise ValideringsFejl("Brugernavnet skal udfyldes og må ikke indeholde mellemrum.")
        if rolle not in ROLLER:
            raise ValideringsFejl("Ukendt rolle.")
        self.valider_ny_kode(kode)
        brugere = self._alle()
        if self._find(brugere, brugernavn):
            raise ValideringsFejl(f"Brugernavnet '{brugernavn}' findes allerede.")
        brugere.append(self._ny(brugernavn, (navn or "").strip() or brugernavn, rolle, kode))
        self.repo.gem_alle(brugere)

    def slet(self, brugernavn: str, aktuel_brugernavn: str) -> None:
        brugere = self._alle()
        bruger = self._find(brugere, brugernavn)
        if bruger is None:
            raise ValideringsFejl("Brugeren findes ikke længere.")
        if bruger["brugernavn"].lower() == str(aktuel_brugernavn).lower():
            raise ValideringsFejl("Du kan ikke slette den bruger, du er logget ind med.")
        if bruger["rolle"] == ROLLE_ADMIN and sum(b["rolle"] == ROLLE_ADMIN for b in brugere) <= 1:
            raise ValideringsFejl("Der skal altid være mindst én administrator.")
        brugere.remove(bruger)
        self.repo.gem_alle(brugere)

    def nulstil_kode(self, brugernavn: str, kode: str) -> None:
        """Administrator sætter en ny kode for en anden bruger."""
        self.valider_ny_kode(kode)
        brugere = self._alle()
        bruger = self._find(brugere, brugernavn)
        if bruger is None:
            raise ValideringsFejl("Brugeren findes ikke længere.")
        self._saet_kode(brugere, bruger, kode)
