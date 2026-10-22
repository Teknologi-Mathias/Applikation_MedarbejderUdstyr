"""JSON-lagring af skabeloner, fælles indstillinger og lokale præferencer."""
import logging
from pathlib import Path

from app.domain import skabelon as sk
from app.infrastructure.stier import INDSTILLINGER, SKABELONER
from app.repositories.fejl import DataFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import gem_json, hent_json

log = logging.getLogger(__name__)


class JsonSkabelonRepository:
    """Data/skabeloner.json – sager, mails og påmindelser."""

    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def hent_alle(self) -> dict:
        fil = self.datakilde.fil(SKABELONER)
        raa = hent_json(fil, forventet=(list, dict))
        try:
            alle = sk.normaliser_alle(raa)
        except ValueError as fejl:
            raise DataFejl(
                f"{fil.name} er ugyldig ({fejl}). Slet filen for at få "
                "standardskabelonerne tilbage."
            ) from fejl
        if raa != alle and not self.datakilde.offline:
            # Skriv nye felter/standardskabeloner, så id'er er stabile.
            gem_json(alle, fil)
        return alle

    def gem(self, slags: str, skabelon: dict, placering: int) -> None:
        self.datakilde.kraev_online("Ændring af skabeloner")
        alle = self.hent_alle()
        liste = alle[slags]
        index = next((i for i, s in enumerate(liste) if s["id"] == skabelon["id"]), None)
        if index is None:
            liste.insert(placering, skabelon)
        else:
            liste[index] = skabelon
        gem_json({s: alle[s] for s in sk.SLAGS}, self.datakilde.fil(SKABELONER))


class JsonIndstillingRepository:
    """Data/indstillinger.json – fælles for alle brugere."""

    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def hent(self) -> dict:
        return hent_json(self.datakilde.fil(INDSTILLINGER), forventet=dict)

    def gem(self, indstillinger: dict) -> None:
        self.datakilde.kraev_online("Ændring af fælles indstillinger")
        gem_json(indstillinger, self.datakilde.fil(INDSTILLINGER))


class JsonLokalFil:
    """En lille JSON-fil i den lokale mappe (præferencer, lagring, notifikationslog).

    Lokale filer virker altid – også offline – fordi de hører til denne pc.
    """

    def __init__(self, fil: Path):
        self.fil = fil

    def hent(self) -> dict:
        try:
            return hent_json(self.fil, forventet=dict)
        except DataFejl:
            log.exception("Lokal fil %s kunne ikke læses – bruger standardværdier", self.fil)
            return {}

    def gem(self, data: dict) -> None:
        gem_json(data, self.fil)


class JsonPraeferenceRepository:
    """Brugerens præferencer på denne pc: {brugernavn: {...}}."""

    def __init__(self, fil: Path):
        self.lager = JsonLokalFil(fil)

    def hent(self, brugernavn: str) -> dict:
        return dict(self.lager.hent().get(brugernavn.lower(), {}))

    def gem(self, brugernavn: str, praeferencer: dict) -> None:
        alle = self.lager.hent()
        alle[brugernavn.lower()] = praeferencer
        self.lager.gem(alle)
