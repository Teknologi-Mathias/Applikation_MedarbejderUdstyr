"""Sager (onboarding/offboarding) i Supabase.

- Læsning: én forespørgsel pr. liste, inkl. personer, ansættelse, opgaver,
  rykkere og tidslinje (mapping.SAG_SELECT), filtreret på proces og arkiv.
- Skrivning: kun via RPC inbase_save_case (003), som gemmer sagen og dens
  egne rækker atomisk og afviser forældede versioner (KonfliktFejl).
  Repositoryet husker rækkerne fra sidste hentning, så kun ændrede opgaver,
  rykkere og nye hændelser sendes.
- Arkivering er blot en gemning med arkiveringsdato.
"""
import logging
from typing import Optional, Type

from app.domain.sag import Sag
from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import hent_alle, kald

log = logging.getLogger(__name__)


class SupabaseSagRepository:
    def __init__(self, klient, sagstype: Type[Sag]):
        self.klient = klient
        self.sagstype = sagstype
        self.proces = sagstype.PROCES
        # sag_id -> (version, rækker) fra sidste hentning/gemning.
        self._kendt: dict[str, tuple[int, dict]] = {}

    ### ----- læsning --------------------------------------------------------

    def _forespoergsel(self):
        return (self.klient.table("lifecycle_cases").select(mapping.SAG_SELECT)
                .eq("process", self.proces))

    def _til_sager(self, raekker: list[dict]) -> list[Sag]:
        sager = []
        for raekke in raekker:
            try:
                sag = mapping.sag_fra_raekke(raekke, self.sagstype)
            except Exception as fejl:
                log.exception("Ugyldig %s-sag i databasen: %r", self.proces, raekke.get("id"))
                raise DataFejl(f"En {self.proces}-sag kunne ikke indlæses ({fejl}). "
                               "Se logfilen.") from fejl
            self._husk(sag)
            sager.append(sag)
        return sager

    def _husk(self, sag: Sag) -> None:
        try:
            self._kendt[sag.id] = (sag.version, mapping.sag_til_raekker(sag))
        except Exception:   # en sag, der ikke kan gemmes uændret, sendes bare fuldt
            self._kendt.pop(sag.id, None)

    def hent_aktive(self) -> list[Sag]:
        return self._til_sager(hent_alle(
            lambda: self._forespoergsel().is_("archived_on", "null")
            .order("created_at").order("id"),
            f"hente aktive {self.proces}-sager"))

    def hent_arkiverede(self) -> list[Sag]:
        return self._til_sager(hent_alle(
            lambda: self._forespoergsel().not_.is_("archived_on", "null")
            .order("created_at").order("id"),
            f"hente arkiverede {self.proces}-sager"))

    def hent(self, sag_id: str) -> Optional[Sag]:
        if mapping.til_uuid(sag_id) is None:
            return None
        with kald("hente sagen"):
            svar = self._forespoergsel().eq("id", sag_id).limit(1).execute()
        sager = self._til_sager(svar.data or [])
        return sager[0] if sager else None

    def signatur(self) -> tuple:
        """Ændrer sig, når en sag i processen er oprettet, ændret eller slettet."""
        with kald("tjekke for ændringer"):
            svar = (self.klient.table("lifecycle_cases").select("updated_at", count="exact")
                    .eq("process", self.proces).order("updated_at", desc=True)
                    .limit(1).execute())
        seneste = svar.data[0]["updated_at"] if svar.data else None
        return (svar.count, seneste)

    ### ----- skrivning ------------------------------------------------------

    def gem(self, sag: Sag) -> Sag:
        raekker = mapping.sag_til_raekker(sag)
        kendt = self._kendt.get(sag.id)
        forrige = kendt[1] if kendt and kendt[0] == sag.version else None
        payload = mapping.rpc_payload(raekker, forrige)
        with kald("gemme sagen"):
            svar = self.klient.rpc("inbase_save_case", {
                "p_case": payload, "p_expected_version": sag.version,
            }).execute()
        resultat = svar.data or {}
        sag.version = int(resultat["version"])
        sag.opdateret = mapping.fra_tidspunkt(resultat.get("updated_at"))
        self._kendt[sag.id] = (sag.version, raekker)
        return sag

    def arkiver(self, sag: Sag) -> Sag:
        return self.gem(sag)

    def aktiver(self, sag: Sag) -> Sag:
        return self.gem(sag)

    def slet(self, sag: Sag) -> None:
        with kald("slette sagen"):
            self.klient.rpc("inbase_delete_case", {
                "p_case_id": sag.id, "p_expected_version": sag.version,
            }).execute()
        self._kendt.pop(sag.id, None)
