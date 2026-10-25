"""Autentificering og brugeradministration.

To implementeringer med samme offentlige metoder, så login, skift af kode og
brugerkartotek i UI'en virker uændret:

- SupabaseAuthService (standard): Supabase Auth + user_profiles. Man logger
  på med BRUGERNAVN; repositoryet oversætter det til kontoens interne
  login-alias. Rollen og om kontoen er aktiv afgøres af profilen i
  databasen; andre brugeres konti oprettes, nulstilles, (de)aktiveres og
  slettes af Edge Functions, der selv tjekker administratorrollen.
- AuthService (kun INBASE_BACKEND=json): saltede PBKDF2-hashes i
  Data/brugere.json – BETA, filen er ikke beskyttet. Ingen standardbruger:
  den første administrator oprettes med tools/opret_json_administrator.py.

Brugernavne normaliseres altid (app/domain/bruger.py). Adgangskoder gemmes
aldrig i klartekst og logges aldrig.
"""
import hashlib
import hmac
import logging
import secrets

from app.domain import adgang
from app.domain.bruger import BRUGERNAVN_REGEL, er_gyldigt_brugernavn, normaliser_brugernavn
from app.domain.historik import nu
from app.repositories.base import BrugerRepository, KontoRepository
from app.repositories.fejl import (
    DataFejl,
    ForkertLoginFejl,
    SessionUdloebetFejl,
    ValideringsFejl,
)

log = logging.getLogger(__name__)

ROLLE_ADMIN = "Administrator"
ROLLE_BRUGER = "Bruger"
ROLLER = (ROLLE_ADMIN, ROLLE_BRUGER)

MIN_KODE_LAENGDE = 6
_ITERATIONER = 200_000

DEAKTIVERET = "Kontoen er deaktiveret. Kontakt en administrator."
INGEN_ADGANG = "Kontoen har ikke adgang til IN-BASE. Kontakt en administrator."
ADGANG_LUKKET = "Din adgang til IN-BASE er lukket. Kontakt en administrator."
ROLLE_AENDRET = "Din rolle er ændret af en administrator. Log på igen for at fortsætte."
ADGANG_AENDRET = "Din adgang er ændret af en administrator. Log på igen for at fortsætte."


def _hash(kode: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", kode.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONER
    ).hex()


def offentlig(bruger: dict) -> dict:
    """Brugeren uden salt og hash (det, resten af programmet må se)."""
    return {"aktiv": True, **{k: v for k, v in bruger.items() if k not in ("salt", "hash")}}


def valider_brugernavn(tekst) -> str:
    """Det normaliserede brugernavn – eller ValideringsFejl."""
    brugernavn = normaliser_brugernavn(tekst)
    if not er_gyldigt_brugernavn(brugernavn):
        raise ValideringsFejl(BRUGERNAVN_REGEL)
    return brugernavn


def _samme(a, b) -> bool:
    return normaliser_brugernavn(a) == normaliser_brugernavn(b)


class AuthService:
    # Til brugerfladen: hvad man logger på med, og om adgangskoderne er BETA.
    LOGIN_FELT = "Brugernavn"
    LOGIN_FEJL = "Forkert brugernavn eller adgangskode."
    MIDLERTIDIG_KODE = False
    BETA = True
    MIN_KODE = MIN_KODE_LAENGDE

    def __init__(self, repo: BrugerRepository):
        self.repo = repo

    def log_ud(self) -> None:
        """Lokale konti har ingen server-session."""

    def kontroller_session(self) -> None:
        """Lokale konti har ingen server-session at kontrollere."""

    ### ----- hjælpere -------------------------------------------------------

    def _alle(self) -> list[dict]:
        return self.repo.hent_alle()

    @staticmethod
    def _ny(brugernavn, navn, rolle, kode) -> dict:
        salt = secrets.token_hex(16)
        return {"brugernavn": brugernavn, "navn": navn, "rolle": rolle, "aktiv": True,
                "salt": salt, "hash": _hash(kode, salt), "oprettet": nu()}

    @staticmethod
    def _find(brugere, brugernavn):
        return next((b for b in brugere if _samme(b["brugernavn"], brugernavn)), None)

    def _hent(self, brugere, brugernavn) -> dict:
        bruger = self._find(brugere, brugernavn)
        if bruger is None:
            raise ValideringsFejl("Brugeren findes ikke længere.")
        return bruger

    @staticmethod
    def _kode_passer(bruger: dict, kode: str) -> bool:
        return bool(bruger.get("salt")) and hmac.compare_digest(
            _hash(kode, bruger["salt"]), bruger.get("hash", "")
        )

    @staticmethod
    def _kraev_aktiv_admin_tilbage(brugere, uden: dict) -> None:
        if not any(b is not uden and b["rolle"] == ROLLE_ADMIN and b.get("aktiv", True)
                   for b in brugere):
            raise ValideringsFejl("Der skal altid være mindst én aktiv administrator.")

    @staticmethod
    def valider_ny_kode(kode: str, gentag: str | None = None) -> None:
        if len(kode or "") < MIN_KODE_LAENGDE:
            raise ValideringsFejl(f"Adgangskoden skal være mindst {MIN_KODE_LAENGDE} tegn.")
        if gentag is not None and kode != gentag:
            raise ValideringsFejl("De to adgangskoder er ikke ens.")

    ### ----- første administrator og log på ---------------------------------

    def klargoer(self) -> None:
        if not self._alle():
            log.warning("Ingen brugere i JSON-tilstand – opret den første administrator med "
                        "tools/opret_json_administrator.py")

    def opret_foerste_administrator(self, brugernavn: str, navn: str, kode: str) -> None:
        """Engangsprocedure (kun når der ingen brugere er)."""
        if self._alle():
            raise ValideringsFejl("Der findes allerede brugere. Opret nye brugere fra IN-BASE.")
        brugernavn = valider_brugernavn(brugernavn)
        self.valider_ny_kode(kode)
        self.repo.gem_alle([self._ny(brugernavn, (navn or "").strip() or brugernavn,
                                     ROLLE_ADMIN, kode)])
        log.info("Første administrator %s oprettet", brugernavn)

    def log_ind(self, brugernavn: str, kode: str) -> dict | None:
        bruger = self._find(self._alle(), brugernavn)
        if bruger is None or not self._kode_passer(bruger, kode):
            log.info("Mislykket log på for %r", normaliser_brugernavn(brugernavn))
            return None
        if not bruger.get("aktiv", True):
            log.warning("Deaktiveret bruger %s forsøgte at logge på", bruger["brugernavn"])
            raise DataFejl(DEAKTIVERET)
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
        brugernavn = valider_brugernavn(brugernavn)
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
        bruger = self._hent(brugere, brugernavn)
        if _samme(bruger["brugernavn"], aktuel_brugernavn):
            raise ValideringsFejl("Du kan ikke slette den bruger, du er logget ind med.")
        if bruger["rolle"] == ROLLE_ADMIN:
            self._kraev_aktiv_admin_tilbage(brugere, bruger)
        brugere.remove(bruger)
        self.repo.gem_alle(brugere)

    def nulstil_kode(self, brugernavn: str, kode: str) -> None:
        """Administrator sætter en ny kode for en anden bruger."""
        self.valider_ny_kode(kode)
        brugere = self._alle()
        self._saet_kode(brugere, self._hent(brugere, brugernavn), kode)

    def saet_aktiv(self, brugernavn: str, aktiv: bool, aktuel_brugernavn: str) -> None:
        brugere = self._alle()
        bruger = self._hent(brugere, brugernavn)
        if _samme(bruger["brugernavn"], aktuel_brugernavn):
            raise ValideringsFejl("Du kan ikke deaktivere den bruger, du er logget ind med.")
        if not aktiv and bruger["rolle"] == ROLLE_ADMIN:
            self._kraev_aktiv_admin_tilbage(brugere, bruger)
        bruger["aktiv"] = bool(aktiv)
        self.repo.gem_alle(brugere)

    def saet_rolle(self, brugernavn: str, rolle: str, aktuel_brugernavn: str) -> None:
        if rolle not in ROLLER:
            raise ValideringsFejl("Ukendt rolle.")
        brugere = self._alle()
        bruger = self._hent(brugere, brugernavn)
        if _samme(bruger["brugernavn"], aktuel_brugernavn):
            raise ValideringsFejl("Du kan ikke ændre din egen rolle.")
        if rolle != ROLLE_ADMIN and bruger["rolle"] == ROLLE_ADMIN:
            self._kraev_aktiv_admin_tilbage(brugere, bruger)
        bruger["rolle"] = rolle
        self.repo.gem_alle(brugere)

    def saet_moduler(self, brugernavn: str, moduler) -> None:
        brugere = self._alle()
        self._hent(brugere, brugernavn)["moduler"] = adgang.normaliser(moduler)
        self.repo.gem_alle(brugere)


### ===== Supabase Auth ======================================================

SUPABASE_MIN_KODE_LAENGDE = 8


class SupabaseAuthService:
    """Login og brugeradministration mod Supabase Auth.

    - Log på sker med brugernavn + adgangskode. Supabase Auth kontrollerer
      koden (mod kontoens interne login-alias, se SupabaseKontoRepository).
    - Uden en AKTIV user_profiles-række har kontoen ingen adgang (RLS) – også
      selvom login lykkes. kontroller_session() opdager en lukket adgang
      eller udløbet session, mens programmet kører.
    - Rollen kommer fra profilen i databasen, aldrig fra klienten.
    - Nye brugere får en midlertidig kode af administratoren og skal skifte
      den ved første log på (skal_skifte_kode).
    """

    LOGIN_FELT = "Brugernavn"
    # Samme besked for ukendt brugernavn, forkert kode og deaktiveret konto,
    # så login ikke afslører, hvilke brugernavne der findes.
    LOGIN_FEJL = ("Forkert brugernavn eller adgangskode. Er du sikker på, at de er rigtige, "
                  "så kontakt en administrator.")
    MIDLERTIDIG_KODE = True
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

    def log_ind(self, brugernavn: str, kode: str) -> dict | None:
        """Brugeren (profil) ved korrekt login, ellers None. DataFejl ved andre fejl."""
        brugernavn = normaliser_brugernavn(brugernavn)
        if not er_gyldigt_brugernavn(brugernavn) or not kode:
            return None
        try:
            bruger_id = self.repo.log_ind(brugernavn, kode)
        except ForkertLoginFejl:
            log.info("Mislykket log på for %r", brugernavn)
            return None
        profil = self.repo.profil(bruger_id)
        if profil is None or not profil["aktiv"]:
            self.repo.log_ud()
            log.warning("Konto uden aktiv IN-BASE-profil forsøgte at logge på: %s", brugernavn)
            raise DataFejl(DEAKTIVERET if profil else INGEN_ADGANG)
        self._aktuel = profil
        log.info("Bruger %s logget på", profil["brugernavn"])
        return profil

    def log_ud(self) -> None:
        self._aktuel = None
        self.repo.log_ud()

    def kontroller_session(self) -> None:
        """Kaster SessionUdloebetFejl, hvis sessionen er udløbet, eller adgangen er lukket.

        Kaldes jævnligt af hovedvinduet. Databasen afviser i forvejen al adgang
        for en deaktiveret konto (RLS) – her lukkes også programmet ned.
        """
        if not self._aktuel:
            return
        profil = self.repo.profil(self._aktuel["id"])
        if profil is None or not profil["aktiv"]:
            raise SessionUdloebetFejl(ADGANG_LUKKET)
        if profil["rolle"] != self._aktuel["rolle"]:
            raise SessionUdloebetFejl(ROLLE_AENDRET)
        if profil.get("moduler") != self._aktuel.get("moduler"):
            raise SessionUdloebetFejl(ADGANG_AENDRET)

    def brugere(self) -> list[dict]:
        """Administratorer: alle profiler. Brugere: kun aktive navne (til "Ansvarlig")."""
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
            self.repo.log_ind(self._aktuel["brugernavn"], nuvaerende)
        except ForkertLoginFejl as fejl:
            raise ValideringsFejl("Den nuværende adgangskode er forkert.") from fejl
        self.repo.skift_egen_kode(ny)
        self._aktuel["skal_skifte_kode"] = False
        log.info("Adgangskode skiftet for %s", self._aktuel["brugernavn"])

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
            if _samme(profil["brugernavn"], brugernavn):
                return profil
        raise ValideringsFejl("Brugeren findes ikke længere.")

    def _ikke_mig(self, profil: dict, aktuel_brugernavn: str, handling: str) -> None:
        if _samme(profil["brugernavn"], aktuel_brugernavn):
            raise ValideringsFejl(f"Du kan ikke {handling} den bruger, du er logget ind med.")

    def opret(self, brugernavn: str, navn: str, rolle: str, kode: str) -> None:
        brugernavn = valider_brugernavn(brugernavn)
        if rolle not in ROLLER:
            raise ValideringsFejl("Ukendt rolle.")
        self.valider_ny_kode(kode)
        self.repo.opret(brugernavn, (navn or "").strip() or brugernavn, rolle, kode)
        log.info("Bruger %s oprettet med rollen %s", brugernavn, rolle)

    def nulstil_kode(self, brugernavn: str, kode: str) -> None:
        """Administrator sætter en ny midlertidig kode for en anden bruger."""
        self.valider_ny_kode(kode)
        self.repo.nulstil_kode(self._profil_for(brugernavn)["id"], kode)

    def saet_aktiv(self, brugernavn: str, aktiv: bool, aktuel_brugernavn: str) -> None:
        profil = self._profil_for(brugernavn)
        self._ikke_mig(profil, aktuel_brugernavn, "deaktivere")
        self.repo.saet_aktiv(profil["id"], bool(aktiv))
        log.info("Bruger %s %s", profil["brugernavn"], "aktiveret" if aktiv else "deaktiveret")

    def saet_rolle(self, brugernavn: str, rolle: str, aktuel_brugernavn: str) -> None:
        if rolle not in ROLLER:
            raise ValideringsFejl("Ukendt rolle.")
        profil = self._profil_for(brugernavn)
        if _samme(profil["brugernavn"], aktuel_brugernavn):
            raise ValideringsFejl("Du kan ikke ændre din egen rolle.")
        self.repo.saet_rolle(profil["id"], rolle)
        log.info("Bruger %s har nu rollen %s", profil["brugernavn"], rolle)

    def saet_moduler(self, brugernavn: str, moduler) -> None:
        profil = self._profil_for(brugernavn)
        self.repo.saet_moduler(profil["id"], adgang.normaliser(moduler))
        log.info("Bruger %s har nu adgang til: %s", profil["brugernavn"],
                 ", ".join(adgang.normaliser(moduler)) or "ingen moduler")

    def slet(self, brugernavn: str, aktuel_brugernavn: str) -> None:
        profil = self._profil_for(brugernavn)
        self._ikke_mig(profil, aktuel_brugernavn, "slette")
        self.repo.slet(profil["id"])
