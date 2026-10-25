"""Telefoner (MDM) i Supabase (tabellen og RPC'erne fra migrering 007 og 008).

Læsning direkte fra tabellen (RLS: kun administratorer). Oprettelse og
ændringer går gennem RPC'erne – flere ændringer kan sendes i ét kald. Sletning direkte.
"""
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
