"""Minut-tjekket i ét kald (RPC inbase_tick, migrering 023).

Svaret er lille: profilen (sessionstjek) og signaturer for sager, kalender,
indstillinger og skabeloner. Hovedvinduet henter kun det, hvis signatur har
ændret sig siden sidst.
"""
from dataclasses import dataclass

from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.kalender_repository import signatur_fra
from app.repositories.supabase.klient import kald


@dataclass(frozen=True)
class Signaturer:
    profil: dict | None          # som SupabaseKontoRepository.profil(); None = ingen adgang
    sager: dict                  # proces -> (aktive, arkiv) som SupabaseSagRepository.signatur()
    kalender: tuple
    indstillinger: tuple
    skabeloner: tuple


class SupabaseTjekRepository:
    def __init__(self, klient):
        self.klient = klient

    def signaturer(self) -> Signaturer:
        with kald("tjekke for ændringer"):
            svar = self.klient.rpc("inbase_tick", {}).execute()
        if not isinstance(svar.data, dict):
            raise DataFejl("Tjek for ændringer mislykkedes: uventet svar fra databasen.")
        data = svar.data
        profil = data.get("profile")
        return Signaturer(
            profil=mapping.bruger_fra_profil(profil) if profil else None,
            sager={proces: (tuple(sig.get("aktive") or ()), tuple(sig.get("arkiv") or ()))
                   for proces, sig in (data.get("cases") or {}).items()},
            kalender=signatur_fra(data.get("calendar") or {}),
            indstillinger=tuple(data.get("settings") or ()),
            skabeloner=tuple(data.get("templates") or ()),
        )
