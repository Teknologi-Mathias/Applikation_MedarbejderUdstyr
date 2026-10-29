"""Central opdatering i Supabase (migrering 019).

- krav(): skemaversion og mindste klientversion via RPC – virker også før log på.
  Findes RPC'en ikke, er migrering 019 ikke kørt: skemaversion 0.
- udgivelser(): app_releases (RLS: stabil for alle, pilot kun med pilotkanal).
- Installeren ligger i den private Storage-bucket "releases"; klienten henter den
  via en tidsbegrænset, signeret adresse (app/infrastructure/opdatering.py).
- Udgivelse og administration (kun administratorer, RLS) bruges af
  tools/udgiv_version.py.
"""
import logging

from app.domain.opdatering import Udgivelse
from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import hent_alle, kald, oversaet

log = logging.getLogger(__name__)

BUCKET = "releases"
TABEL = "app_releases"
# Hvor længe en signeret downloadadresse gælder (sekunder).
URL_GYLDIG = 15 * 60


class SupabaseOpdateringRepository:
    def __init__(self, klient):
        self.klient = klient

    ### ----- klienten -------------------------------------------------------

    def krav(self) -> dict:
        from postgrest.exceptions import APIError
        try:
            svar = self.klient.rpc("inbase_client_requirements", {}).execute()
        except APIError as fejl:
            if str(fejl.code or "") == "PGRST202":     # funktionen findes ikke
                log.warning("inbase_client_requirements mangler – migrering 019 er ikke kørt")
                return {"schema_version": 0, "min_client_version": "0.0.0"}
            raise oversaet(fejl, "tjekke databasens version") from fejl
        except Exception as fejl:
            raise oversaet(fejl, "tjekke databasens version") from fejl
        return svar.data if isinstance(svar.data, dict) else {}

    def udgivelser(self) -> list[Udgivelse]:
        raekker = hent_alle(lambda: self.klient.table(TABEL).select("*")
                            .order("created_at").order("version"), "hente udgivne versioner")
        return [mapping.udgivelse_fra_raekke(r) for r in raekker]

    def rapporter(self, version: str) -> None:
        with kald("melde programversionen"):
            self.klient.rpc("inbase_report_client", {"p_version": version}).execute()

    def download_url(self, sti: str) -> str:
        with kald("hente opdateringen"):
            svar = self.klient.storage.from_(BUCKET).create_signed_url(sti, URL_GYLDIG)
        url = (svar or {}).get("signedURL") or (svar or {}).get("signedUrl")
        if not url:
            raise DataFejl("Opdateringen kunne ikke hentes: ingen downloadadresse fra serveren.")
        return url

    ### ----- udgivelse (kun administratorer) --------------------------------

    def upload(self, sti: str, data: bytes) -> None:
        with kald("uploade installeren"):
            self.klient.storage.from_(BUCKET).upload(
                path=sti, file=data,
                file_options={"content-type": "application/octet-stream", "upsert": "false"})

    def slet_fil(self, sti: str) -> None:
        with kald("slette installeren"):
            self.klient.storage.from_(BUCKET).remove([sti])

    def opret(self, udgivelse: Udgivelse) -> None:
        raekke = mapping.udgivelse_til_raekke(udgivelse)
        with kald("registrere versionen"):
            self.klient.table(TABEL).insert(raekke).execute()

    def opdater(self, version: str, **felter) -> None:
        """felter med domænenavne, fx kanal="stabil", udrulning=50, trukket_tilbage=True."""
        kolonner = {kolonne: konv[0](felter[noegle])
                    for noegle, kolonne, konv in mapping.UDGIVELSE_FELTER if noegle in felter}
        with kald("ændre versionen"):
            svar = self.klient.table(TABEL).update(kolonner).eq("version", version).execute()
        if not svar.data:
            raise DataFejl(f"Version {version} findes ikke (eller du er ikke administrator).")

    def slet(self, version: str) -> None:
        with kald("slette versionen"):
            self.klient.table(TABEL).delete().eq("version", version).execute()

    def saet_minimum(self, version: str) -> None:
        with kald("sætte mindste klientversion"):
            self.klient.table("app_settings").upsert(
                {"key": "min_klient_version", "value": version}, on_conflict="key").execute()
