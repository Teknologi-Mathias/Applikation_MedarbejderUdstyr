"""Konti: Supabase Auth, user_profiles og administrator-Edge Functions.

Adgangskoder håndteres udelukkende af Supabase Auth – de gemmes eller hashes
aldrig af IN-BASE. Oprettelse, nulstilling og sletning af ANDRE brugeres
konti kræver privilegier, som desktopklienten ikke har. Det sker derfor i
Edge Functions (supabase/functions/admin-create-user og admin-manage-user),
som selv tjekker, at kalderen er administrator i user_profiles.
"""
import logging

from app.repositories.fejl import DataFejl, ForkertLoginFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import kald, oversaet

log = logging.getLogger(__name__)

FUNKTION_OPRET = "admin-create-user"
FUNKTION_ADMINISTRER = "admin-manage-user"


class SupabaseKontoRepository:
    def __init__(self, klient):
        self.klient = klient

    ### ----- session --------------------------------------------------------

    def log_ind(self, email: str, kode: str) -> str:
        """Logger på og returnerer brugerens id. Kaster ForkertLoginFejl ved forkert kode."""
        from supabase_auth.errors import AuthApiError
        try:
            svar = self.klient.auth.sign_in_with_password({"email": email, "password": kode})
        except AuthApiError as fejl:
            if fejl.status in (400, 401, 422):
                raise ForkertLoginFejl(fejl.message) from fejl
            raise oversaet(fejl, "logge på") from fejl
        except Exception as fejl:
            raise oversaet(fejl, "logge på") from fejl
        if svar.user is None:
            raise ForkertLoginFejl("Login returnerede ingen bruger.")
        return str(svar.user.id)

    def log_ud(self) -> None:
        try:
            self.klient.auth.sign_out({"scope": "local"})
        except Exception:   # en udløbet session må ikke forhindre log ud
            log.warning("Log ud fra Supabase mislykkedes", exc_info=True)

    def aktuel_id(self) -> str | None:
        session = self.klient.auth.get_session()
        return str(session.user.id) if session and session.user else None

    ### ----- profiler -------------------------------------------------------

    def profil(self, bruger_id: str) -> dict | None:
        with kald("hente din profil"):
            svar = (self.klient.table("user_profiles").select("*").eq("id", bruger_id)
                    .limit(1).execute())
        return mapping.bruger_fra_profil(svar.data[0]) if svar.data else None

    def alle_profiler(self) -> list[dict]:
        """Alle profiler med e-mail og rolle (RLS: kun administratorer ser andre end sig selv)."""
        with kald("hente brugere"):
            svar = self.klient.table("user_profiles").select("*").order("username").execute()
        return [mapping.bruger_fra_profil(p) for p in svar.data or []]

    def katalog(self) -> list[dict]:
        """Brugernavn og navn på alle brugere (til "Ansvarlig"-listen)."""
        with kald("hente brugerlisten"):
            svar = self.klient.rpc("inbase_user_directory", {}).execute()
        return [{"brugernavn": r["username"], "navn": r["display_name"] or r["username"]}
                for r in svar.data or []]

    ### ----- egen adgangskode -----------------------------------------------

    def skift_egen_kode(self, ny_kode: str) -> None:
        with kald("skifte adgangskode"):
            self.klient.auth.update_user({"password": ny_kode})
            self.klient.rpc("inbase_password_changed", {}).execute()

    ### ----- administration via Edge Functions ------------------------------

    def _funktion(self, navn: str, body: dict, handling: str) -> dict:
        with kald(handling):
            svar = self.klient.functions.invoke(navn, invoke_options={
                "body": body, "responseType": "json"})
        if not isinstance(svar, dict) or not svar.get("ok"):
            raise DataFejl(f"{handling.capitalize()} mislykkedes: uventet svar fra serveren.")
        return svar

    def opret(self, email: str, brugernavn: str, navn: str, rolle: str, kode: str) -> dict:
        svar = self._funktion(FUNKTION_OPRET, {
            "email": email, "username": brugernavn, "display_name": navn,
            "role": rolle, "password": kode,
        }, "oprette brugeren")
        return svar.get("user") or {}

    def nulstil_kode(self, bruger_id: str, kode: str) -> None:
        self._funktion(FUNKTION_ADMINISTRER, {
            "action": "reset_password", "user_id": bruger_id, "password": kode,
        }, "nulstille adgangskoden")

    def slet(self, bruger_id: str) -> None:
        self._funktion(FUNKTION_ADMINISTRER, {"action": "delete", "user_id": bruger_id},
                       "slette brugeren")
