"""JSON-lagring af brugere (Data/brugere.json).

Kun læsning/skrivning – regler for log på, adgangskoder og roller ligger i
app/services/auth_service.py.
"""
from app.infrastructure.stier import BRUGERE
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import gem_json, hent_json


class JsonBrugerRepository:
    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def hent_alle(self) -> list[dict]:
        return [
            b for b in hent_json(self.datakilde.fil(BRUGERE))
            if isinstance(b, dict) and b.get("brugernavn")
        ]

    def gem_alle(self, brugere: list[dict]) -> None:
        self.datakilde.kraev_online("Ændring af brugere")
        gem_json(brugere, self.datakilde.fil(BRUGERE))
