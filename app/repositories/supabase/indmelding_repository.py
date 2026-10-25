"""Ønsker & Udvikling i Supabase (tabeller og RPC'er fra migrering 006).

Læsning direkte fra tabellerne (RLS: kun aktive medlemmer; interne noter kun
for administratorer). Oprettelse, ændring og kommentarer går gennem RPC'erne,
som selv sætter indsender/forfatter ud fra login, tjekker rettigheder og
versionen og skriver historikken. Sletning direkte (RLS: kun administratorer).
"""
from typing import Optional

from app.domain.indmelding import Aendring, Indmelding, Kommentar
from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import hent_alle, kald

TABEL = "development_requests"
KOMMENTARER = "development_request_comments"
HISTORIK = "development_request_events"


class SupabaseIndmeldingRepository:
    def __init__(self, klient):
        self.klient = klient

    ### ----- læsning --------------------------------------------------------

    def hent_alle(self) -> list[Indmelding]:
        raekker = hent_alle(lambda: self.klient.table(TABEL).select("*").order("number"),
                            "hente indmeldinger")
        return [mapping.indmelding_fra_raekke(r) for r in raekker]

    def hent(self, indmelding_id: str) -> Optional[Indmelding]:
        if mapping.til_uuid(indmelding_id) is None:
            return None
        with kald("hente indmeldingen"):
            svar = self.klient.table(TABEL).select("*").eq("id", indmelding_id).limit(1).execute()
        return mapping.indmelding_fra_raekke(svar.data[0]) if svar.data else None

    def kommentarer(self, indmelding_id: str) -> list[Kommentar]:
        raekker = hent_alle(lambda: self.klient.table(KOMMENTARER).select("*")
                            .eq("request_id", indmelding_id).order("created_at").order("id"),
                            "hente kommentarer")
        return [mapping.kommentar_fra_raekke(r) for r in raekker]

    def historik(self, indmelding_id: str) -> list[Aendring]:
        raekker = hent_alle(lambda: self.klient.table(HISTORIK).select("*")
                            .eq("request_id", indmelding_id).order("id"),
                            "hente historikken")
        return [mapping.aendring_fra_raekke(r) for r in raekker]

    def signatur(self) -> tuple:
        """Ændrer sig, når en indmelding er oprettet, ændret eller slettet."""
        with kald("tjekke for ændringer"):
            svar = (self.klient.table(TABEL).select("updated_at", count="exact")
                    .order("updated_at", desc=True).limit(1).execute())
        return (svar.count, svar.data[0]["updated_at"] if svar.data else None)

    ### ----- skrivning ------------------------------------------------------

    def _rpc(self, funktion: str, parametre: dict, handling: str) -> dict:
        with kald(handling):
            svar = self.klient.rpc(funktion, parametre).execute()
        if not isinstance(svar.data, dict):
            raise DataFejl(f"{handling.capitalize()} mislykkedes: uventet svar fra databasen.")
        return svar.data

    def opret(self, felter: dict) -> Indmelding:
        raekke = self._rpc("inbase_create_request",
                           {"p_request": mapping.indmelding_til_rpc(felter)},
                           "oprette indmeldingen")
        return mapping.indmelding_fra_raekke(raekke)

    def opdater(self, indmelding_id: str, version: int, aendringer: dict) -> Indmelding:
        raekke = self._rpc("inbase_update_request", {
            "p_id": indmelding_id, "p_expected_version": version,
            "p_changes": mapping.indmelding_til_rpc(aendringer),
        }, "gemme indmeldingen")
        return mapping.indmelding_fra_raekke(raekke)

    def tilfoej_kommentar(self, indmelding_id: str, tekst: str, intern: bool) -> Kommentar:
        raekke = self._rpc("inbase_add_request_comment", {
            "p_request_id": indmelding_id, "p_body": tekst, "p_internal": intern,
        }, "tilføje kommentaren")
        return mapping.kommentar_fra_raekke(raekke)

    def slet(self, indmelding_id: str) -> None:
        with kald("slette indmeldingen"):
            svar = self.klient.table(TABEL).delete().eq("id", indmelding_id).execute()
        if not svar.data:   # RLS filtrerer rækken fra for andre end administratorer
            raise DataFejl("Indmeldingen blev ikke slettet. Kun administratorer kan slette "
                           "indmeldinger – eller den er allerede slettet.")
