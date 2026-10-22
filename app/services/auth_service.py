"""Autentificering og brugeradministration.

To implementeringer med samme offentlige metoder, så login, skift af kode og
brugerkartotek i UI'en virker uændret:

- SupabaseAuthService (standard): Supabase Auth + user_profiles. Rollen
  afgøres af profilen i databasen; andre brugeres konti oprettes, nulstilles
  og slettes af Edge Functions, der selv tjekker administratorrollen.
- AuthService (kun INBASE_BACKEND=json): saltede PBKDF2-hashes i
  Data/brugere.json – BETA, filen er ikke beskyttet.

Adgangskoder gemmes aldrig i klartekst.
"""
import hashlib
import hmac
import logging
import re
import secrets

from app.domain.historik import nu
from app.repositories.base import BrugerRepository, KontoRepository
from app.repositories.fejl import DataFejl, ForkertLoginFejl, ValideringsFejl

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
    # Til brugerfladen: hvad man logger på med, og om adgangskoderne er BETA.
    LOGIN_FELT = "Brugernavn"
    LOGIN_FEJL = "Forkert brugernavn eller adgangskode."
    KRAEVER_EMAIL = False
    BETA = True
    MIN_KODE = MIN_KODE_LAENGDE

    def __init__(self, repo: BrugerRepository):
        self.repo = repo

    def log_ud(self) -> None:
        """Lokale konti har ingen server-session."""

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

    def opret(self, brugernavn: str, navn: str, rolle: str, kode: str, email: str = "") -> None:
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


### ===== Supabase Auth ======================================================

SUPABASE_MIN_KODE_LAENGDE = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BRUGERNAVN = re.compile(r"^[A-Za-z0-9._-]{2,40}$")


class SupabaseAuthService:
    """Login og brugeradministration mod Supabase Auth.

    - Log på sker med e-mail + adgangskode. Uden en user_profiles-række har
      kontoen ingen adgang (RLS) – også selvom login lykkes.
    - Rollen kommer fra profilen i databasen, aldrig fra klienten.
    - Nye brugere får en midlertidig kode af administratoren og skal skifte
      den ved første log på (skal_skifte_kode).
    """

    LOGIN_FELT = "E-mail"
    LOGIN_FEJL = "Forkert e-mail eller adgangskode."
    KRAEVER_EMAIL = True
    BETA = False
    MIN_KODE = SUPABASE_MIN_KODE_LAENGDE

    def __init__(self, repo: KontoRepository):
        self.repo = repo
        self._aktuel: dict | None = None

    @staticmethod
    def valider_ny_kode(kode: str, gentag: str | None = None) -> None:
        if len(kode or "") < SUPABASE_MIN_KODE_LAENGDE:
            raise ValideringsFejl(
                f"Adgangskoden skal være mindst {SUPABASE_MIN_KODE_LAENGDE} tegn.")
        if gentag is not None and kode != gentag:
            raise ValideringsFejl("De to adgangskoder er ikke ens.")

    ### ----- log på ---------------------------------------------------------

    def klargoer(self) -> None:
        """Intet at forberede: konti findes i Supabase Auth."""

    def log_ind(self, email: str, kode: str) -> dict | None:
        """Brugeren (profil) ved korrekt login, ellers None. DataFejl ved andre fejl."""
        email = (email or "").strip().lower()
        if not _EMAIL.match(email) or not kode:
            return None
        try:
            bruger_id = self.repo.log_ind(email, kode)
        except ForkertLoginFejl:
            log.info("Mislykket log på for %r", email)
            return None
        profil = self.repo.profil(bruger_id)
        if profil is None:
            self.repo.log_ud()
            log.warning("Konto uden IN-BASE-profil forsøgte at logge på: %s", email)
            raise DataFejl("Kontoen har ikke adgang til IN-BASE. Kontakt en administrator.")
        self._aktuel = profil
        log.info("Bruger %s logget på", profil["brugernavn"])
        return profil

    def log_ud(self) -> None:
        self._aktuel = None
        self.repo.log_ud()

    def brugere(self) -> list[dict]:
        """Administratorer: alle profiler. Brugere: kun navne (til "Ansvarlig")."""
        if self._aktuel and self._aktuel.get("rolle") == ROLLE_ADMIN:
            return self.repo.alle_profiler()
        return self.repo.katalog()

    ### ----- egen adgangskode -----------------------------------------------

    def skift_egen_kode(self, brugernavn: str, nuvaerende: str, ny: str, gentag: str) -> None:
        if not self._aktuel:
            raise ValideringsFejl("Du er ikke logget på.")
        self.valider_ny_kode(ny, gentag)
        if ny == nuvaerende:
            raise ValideringsFejl("Den nye adgangskode skal være forskellig fra den gamle.")
        try:   # bekræft den nuværende kode, før den skiftes
            self.repo.log_ind(self._aktuel["email"], nuvaerende)
        except ForkertLoginFejl as fejl:
            raise ValideringsFejl("Den nuværende adgangskode er forkert.") from fejl
        self.repo.skift_egen_kode(ny)
        self._aktuel["skal_skifte_kode"] = False
        log.info("Adgangskode skiftet for %s", brugernavn)

    def skift_midlertidig_kode(self, ny: str, gentag: str) -> None:
        """Første log på: brugeren vælger sin egen kode i stedet for den midlertidige."""
        if not self._aktuel:
            raise ValideringsFejl("Du er ikke logget på.")
        self.valider_ny_kode(ny, gentag)
        self.repo.skift_egen_kode(ny)
        self._aktuel["skal_skifte_kode"] = False
        log.info("Midlertidig adgangskode skiftet for %s", self._aktuel["brugernavn"])

    ### ----- administration (Edge Functions tjekker selv administratorrollen) -

    def _profil_for(self, brugernavn: str) -> dict:
        for profil in self.repo.alle_profiler():
            if profil["brugernavn"].lower() == str(brugernavn).strip().lower():
                return profil
        raise ValideringsFejl("Brugeren findes ikke længere.")

    def opret(self, brugernavn: str, navn: str, rolle: str, kode: str, email: str = "") -> None:
        brugernavn, email = (brugernavn or "").strip(), (email or "").strip().lower()
        if not _BRUGERNAVN.match(brugernavn):
            raise ValideringsFejl(
                "Brugernavnet skal være 2-40 tegn: bogstaver, tal, punktum, - eller _.")
        if not _EMAIL.match(email):
            raise ValideringsFejl("Skriv en gyldig e-mailadresse – den bruges til at logge på.")
        if rolle not in ROLLER:
            raise ValideringsFejl("Ukendt rolle.")
        self.valider_ny_kode(kode)
        self.repo.opret(email, brugernavn, (navn or "").strip() or brugernavn, rolle, kode)
        log.info("Bruger %s (%s) oprettet med rollen %s", brugernavn, email, rolle)

    def nulstil_kode(self, brugernavn: str, kode: str) -> None:
        """Administrator sætter en ny midlertidig kode for en anden bruger."""
        self.valider_ny_kode(kode)
        self.repo.nulstil_kode(self._profil_for(brugernavn)["id"], kode)

    def slet(self, brugernavn: str, aktuel_brugernavn: str) -> None:
        profil = self._profil_for(brugernavn)
        if profil["brugernavn"].lower() == str(aktuel_brugernavn).lower():
            raise ValideringsFejl("Du kan ikke slette den bruger, du er logget ind med.")
        self.repo.slet(profil["id"])
