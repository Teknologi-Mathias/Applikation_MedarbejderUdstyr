"""Hvor ligger data lige nu? Den centrale mappe – eller offline-kopien.

Alle JSON-repositories spørger Datakilde om mappen ved hvert kald. Når
brugeren slår "Arbejd offline" til, skifter LagringService blot Datakilde
til offline, og hele programmet arbejder videre på den lokale kopi. Ingen
tavse skift: det sker kun, når brugeren selv vælger det.

I offline-tilstand skrives hver ændring af en sag også i ændringsloggen
(Aendringslog), så den kan synkroniseres til den centrale mappe bagefter.
"""
import logging
from pathlib import Path

from app.domain.historik import nu, nuvaerende_bruger
from app.repositories.fejl import OfflineFejl
from app.repositories.json.json_fil import gem_json, hent_json

log = logging.getLogger(__name__)

AENDRINGSLOG = "aendringslog.json"
KONFLIKTER = "konflikter.json"
OFFLINE_INFO = "offline_info.json"


class Aendringslog:
    """Ændringer foretaget offline, i den rækkefølge de skete."""

    def __init__(self, mappe: Path):
        self.fil = mappe / AENDRINGSLOG

    def alle(self) -> list[dict]:
        return hent_json(self.fil)

    def antal(self) -> int:
        return len(self.alle())

    def registrer(self, proces: str, op: str, sag_id: str, basis_version: int,
                  data: dict | None) -> None:
        poster = self.alle()
        poster.append({
            "tid": nu(),
            "bruger": nuvaerende_bruger(),
            "proces": proces,
            "op": op,
            "sag_id": sag_id,
            "basis_version": basis_version,
            "data": data,
        })
        gem_json(poster, self.fil)

    def ryd(self) -> None:
        gem_json([], self.fil)


class Datakilde:
    def __init__(self, central_mappe: Path, offline_mappe: Path, offline: bool = False):
        self.central_mappe = Path(central_mappe)
        self.offline_mappe = Path(offline_mappe)
        self.offline = offline
        self.aendringslog = Aendringslog(self.offline_mappe)

    @property
    def mappe(self) -> Path:
        return self.offline_mappe if self.offline else self.central_mappe

    def fil(self, filnavn: str) -> Path:
        return self.mappe / filnavn

    def kraev_online(self, handling: str) -> None:
        """Handlinger på fælles opsætning (brugere, skabeloner, indstillinger)
        kræver den centrale datakilde – de synkroniseres ikke."""
        if self.offline:
            raise OfflineFejl(
                f"{handling} er ikke muligt i offline-tilstand. "
                "Gå online under Indstillinger først."
            )

    def registrer_aendring(self, proces, op, sag_id, basis_version, data) -> None:
        if self.offline:
            self.aendringslog.registrer(proces, op, sag_id, basis_version, data)
