"""Telefoner (MDM) i Supabase (tabellen og RPC'erne fra migrering 007 og 008).

Styrings-appen til automatisk opdatering udgives med RPC'en fra migrering 026 (ét kald, appen
som base64).

Læsning direkte fra tabellen (RLS: kun administratorer). Oprettelse og
ændringer går gennem RPC'erne – flere ændringer kan sendes i ét kald. Sletning direkte.
"""
import base64
from typing import Optional

from app.domain.mdm_enhed import INFOFELTER, MdmEnhed
from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import hent_alle, kald

TABEL = "mdm_devices"


class SupabaseMdmRepository:
    def __init__(self, klient):
        self.klient = klient

    def hent_alle(self) -> list[MdmEnhed]:
        raekker = hent_alle(lambda: self.klient.table(TABEL).select("*").order("name"),
                            "hente telefoner")
        return [mapping.mdm_fra_raekke(r) for r in raekker]

    def hent(self, enhed_id: str) -> Optional[MdmEnhed]:
        with kald("hente telefonen"):
            svar = self.klient.table(TABEL).select("*").eq("id", enhed_id).execute()
        return mapping.mdm_fra_raekke(svar.data[0]) if svar.data else None

    def opret(self, enhed: MdmEnhed) -> MdmEnhed:
        felter = {"id": enhed.id, **{k: getattr(enhed, k) for k in INFOFELTER}}
        with kald("oprette telefonen"):
            svar = self.klient.rpc("inbase_mdm_create_device",
                                   {"p_device": mapping.mdm_til_rpc(felter)}).execute()
        if not isinstance(svar.data, dict):
            raise DataFejl("Oprettelsen af telefonen mislykkedes: uventet svar fra databasen.")
        return mapping.mdm_fra_raekke(svar.data)

    def opdater(self, aendringer: list[dict]) -> int:
        payload = [{"id": a["id"], **mapping.mdm_til_rpc({k: v for k, v in a.items() if k != "id"})}
                   for a in aendringer]
        with kald("gemme telefoner"):
            svar = self.klient.rpc("inbase_mdm_update_devices", {"p_changes": payload}).execute()
        return int(svar.data or 0)

    def slet(self, enhed_id: str) -> None:
        with kald("slette telefonen"):
            svar = self.klient.table(TABEL).delete().eq("id", enhed_id).execute()
        if not svar.data:
            raise DataFejl("Telefonen blev ikke slettet. Kun administratorer kan slette – "
                           "eller den er allerede slettet.")

    def app_info(self) -> dict:
        with kald("hente den udgivne styrings-app"):
            svar = self.klient.rpc("inbase_mdm_app_info", {}).execute()
        return mapping.mdm_app_fra_rpc(svar.data)

    def udgiv_app(self, version_code: int, version_name: str, apk: bytes) -> dict:
        with kald("udgive styrings-appen"):
            svar = self.klient.rpc("inbase_mdm_publish_app", {
                "p_version_code": version_code, "p_version_name": version_name,
                "p_apk": base64.b64encode(apk).decode("ascii")}).execute()
        return mapping.mdm_app_fra_rpc(svar.data)
