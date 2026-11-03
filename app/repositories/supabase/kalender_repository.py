"""Kalender i Supabase (tabeller og RPC'er fra migrering 020 og 021).

Al læsning og skrivning går gennem RPC'erne – tabellerne kan ikke læses
direkte. RPC'erne sætter ejer/opretter ud fra login, kontrollerer adgangen
(inbase_calendar_access) og versionen og maskerer det, brugeren ikke må se.
"""
from datetime import datetime

from app.domain.kalender import Begivenhed, Kalender
from app.repositories.fejl import DataFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import kald

IMPORT_BIDDER = 200     # begivenheder pr. kald ved import (RPC'en tager højst 500)


class SupabaseKalenderRepository:
    def __init__(self, klient):
        self.klient = klient

    def _rpc(self, funktion: str, parametre: dict, handling: str, forventet=dict):
        with kald(handling):
            svar = self.klient.rpc(funktion, parametre).execute()
        if forventet is not None and not isinstance(svar.data, forventet):
            raise DataFejl(f"{handling.capitalize()} mislykkedes: uventet svar fra databasen.")
        return svar.data

    ### ----- kalendere ------------------------------------------------------

    def kalendre(self) -> list[Kalender]:
        raekker = self._rpc("inbase_calendars", {}, "hente kalendere", list)
        return [mapping.kalender_fra_raekke(r) for r in raekker]

    def opret_kalender(self, kalender: Kalender) -> Kalender:
        raekke = self._rpc("inbase_calendar_create", {"p_calendar": mapping.kalender_til_rpc(
            {"id": mapping.til_uuid(kalender.id), "navn": kalender.navn, "farve": kalender.farve})},
            "oprette kalenderen")
        return mapping.kalender_fra_raekke(raekke)

    def opdater_kalender(self, kalender_id: str, version: int, aendringer: dict) -> Kalender:
        raekke = self._rpc("inbase_calendar_update", {
            "p_id": kalender_id, "p_expected_version": version,
            "p_changes": mapping.kalender_til_rpc(aendringer)}, "gemme kalenderen")
        return mapping.kalender_fra_raekke(raekke)

    def slet_kalender(self, kalender_id: str) -> None:
        self._rpc("inbase_calendar_delete", {"p_id": kalender_id}, "slette kalenderen", None)

    ### ----- begivenheder ---------------------------------------------------

    def begivenheder(self, fra: datetime, til: datetime) -> list[Begivenhed]:
        raekker = self._rpc("inbase_calendar_events", {
            "p_from": mapping.til_tidspunkt(fra.isoformat()),
            "p_to": mapping.til_tidspunkt(til.isoformat())}, "hente kalenderen", list)
        return [mapping.begivenhed_fra_raekke(r) for r in raekker]

    def opret(self, begivenhed: Begivenhed) -> Begivenhed:
        raekke = self._rpc("inbase_calendar_event_create",
                           {"p_event": mapping.begivenhed_til_rpc(begivenhed)},
                           "oprette begivenheden")
        return mapping.begivenhed_fra_raekke(raekke)

    def opdater(self, begivenhed: Begivenhed) -> Begivenhed:
        raekke = self._rpc("inbase_calendar_event_update", {
            "p_id": begivenhed.id, "p_expected_version": begivenhed.version,
            "p_event": mapping.begivenhed_til_rpc(begivenhed, ny=False)}, "gemme begivenheden")
        return mapping.begivenhed_fra_raekke(raekke)

    def slet(self, begivenhed_id: str) -> None:
        self._rpc("inbase_calendar_event_delete", {"p_id": begivenhed_id},
                  "slette begivenheden", None)

    def importer(self, kalender_id: str, begivenheder: list[Begivenhed]) -> int:
        """Rettede forekomster kobles til serien via dens ical_uid (samme kald eller tidligere)."""
        serier = [b for b in begivenheder if b.oprindelig_start is None]
        rettede = [b for b in begivenheder if b.oprindelig_start is not None]
        antal = 0
        for liste in (serier, rettede):
            for start in range(0, len(liste), IMPORT_BIDDER):
                data = []
                for b in liste[start:start + IMPORT_BIDDER]:
                    raekke = mapping.begivenhed_til_rpc(b)
                    if b.oprindelig_start is not None:
                        raekke["recurrence_of_uid"] = b.ical_uid
                    data.append(raekke)
                antal += int(self._rpc("inbase_calendar_import", {
                    "p_calendar_id": kalender_id, "p_events": data},
                    "importere begivenheder", None) or 0)
        return antal

    ### ----- deling -------------------------------------------------------

    def del_kalender(self, kalender_id: str, brugernavn: str, niveau: str) -> Kalender:
        raekke = self._rpc("inbase_calendar_share_set", {
            "p_calendar_id": kalender_id, "p_username": brugernavn, "p_level": niveau},
            "dele kalenderen")
        return mapping.kalender_fra_raekke(raekke)

    def fjern_deling(self, kalender_id: str, brugernavn: str) -> Kalender:
        raekke = self._rpc("inbase_calendar_share_remove", {
            "p_calendar_id": kalender_id, "p_username": brugernavn}, "fjerne delingen")
        return mapping.kalender_fra_raekke(raekke)

    def signatur(self) -> tuple:
        data = self._rpc("inbase_calendar_signature", {}, "tjekke kalenderen for ændringer")
        return (data.get("calendars"), data.get("events"), data.get("shares"), data.get("updated"))
