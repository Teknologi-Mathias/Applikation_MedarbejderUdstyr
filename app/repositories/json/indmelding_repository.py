"""JSON-lagring af Ønsker & Udvikling (Data/oensker.json) – kun udvikling/tests.

Gør det samme som RPC'erne i migrering 006 (løbenummer, indsender ud fra
login, versionskontrol, historik pr. felt), men UDEN databasens
adgangskontrol: i JSON-tilstanden er filen ikke beskyttet (BETA), og
rettighederne kontrolleres kun af IndmeldingService. Kræver online-tilstand.
"""
import uuid
from typing import Optional

from app.domain import indmelding as im
from app.domain.historik import nu, nuvaerende_bruger
from app.domain.indmelding import Aendring, Indmelding, Kommentar
from app.infrastructure.stier import OENSKER
from app.repositories.fejl import KonfliktFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import fil_signatur, gem_json, hent_json


class JsonIndmeldingRepository:
    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def _laes(self) -> dict:
        data = hent_json(self.datakilde.fil(OENSKER), forventet=dict)
        return {"indmeldinger": data.get("indmeldinger", []),
                "kommentarer": data.get("kommentarer", []),
                "historik": data.get("historik", [])}

    def _gem(self, data: dict) -> None:
        gem_json(data, self.datakilde.fil(OENSKER))

    @staticmethod
    def _find(data: dict, indmelding_id: str) -> Optional[dict]:
        return next((i for i in data["indmeldinger"] if i["id"] == indmelding_id), None)

    @staticmethod
    def _log(data, indmelding_id, handling, felt="", fra="", til="") -> None:
        data["historik"].append({"indmelding_id": indmelding_id, "tidspunkt": nu(),
                                 "bruger": nuvaerende_bruger(), "handling": handling,
                                 "felt": felt, "fra": fra, "til": til})

    ### ----- læsning --------------------------------------------------------

    def hent_alle(self) -> list[Indmelding]:
        return [Indmelding.fra_dict(i) for i in self._laes()["indmeldinger"]]

    def hent(self, indmelding_id: str) -> Optional[Indmelding]:
        post = self._find(self._laes(), indmelding_id)
        return Indmelding.fra_dict(post) if post else None

    def kommentarer(self, indmelding_id: str) -> list[Kommentar]:
        return [Kommentar(**k) for k in self._laes()["kommentarer"]
                if k["indmelding_id"] == indmelding_id]

    def historik(self, indmelding_id: str) -> list[Aendring]:
        return [Aendring(**{k: v for k, v in h.items() if k != "indmelding_id"})
                for h in self._laes()["historik"] if h["indmelding_id"] == indmelding_id]

    def signatur(self) -> tuple:
        return fil_signatur(self.datakilde.fil(OENSKER))

    ### ----- skrivning ------------------------------------------------------

    def opret(self, felter: dict) -> Indmelding:
        self.datakilde.kraev_online("Ønsker & Udvikling")
        data = self._laes()
        tid = nu()
        ny = Indmelding(**{k: felter.get(k, "") for k in im.TEKSTFELTER},
                        id=str(uuid.uuid4()), indsender=nuvaerende_bruger(), oprettet=tid,
                        opdateret=tid, version=1,
                        nummer=max((i.get("nummer", 0) for i in data["indmeldinger"]), default=0) + 1)
        data["indmeldinger"].append(ny.til_dict())
        self._log(data, ny.id, Aendring.OPRETTET, "status", "", ny.status)
        self._gem(data)
        return ny

    def opdater(self, indmelding_id: str, version: int, aendringer: dict) -> Indmelding:
        self.datakilde.kraev_online("Ønsker & Udvikling")
        data = self._laes()
        post = self._find(data, indmelding_id)
        if post is None:
            raise KonfliktFejl("Indmeldingen findes ikke længere – den er slettet af en anden.")
        if post.get("version") != version:
            raise KonfliktFejl("Indmeldingen er ændret af en anden, efter du åbnede den. "
                               "Dine ændringer er ikke gemt – åbn den igen og gentag dem.")
        for felt in im.TEKSTFELTER + im.BEHANDLINGSFELTER:
            if felt in aendringer and aendringer[felt] != post.get(felt, ""):
                self._log(data, indmelding_id, Aendring.AENDRET, felt, post.get(felt, ""),
                          aendringer[felt])
                post[felt] = aendringer[felt]
        post["version"] = version + 1
        post["opdateret"] = nu()
        self._gem(data)
        return Indmelding.fra_dict(post)

    def tilfoej_kommentar(self, indmelding_id: str, tekst: str, intern: bool) -> Kommentar:
        self.datakilde.kraev_online("Ønsker & Udvikling")
        data = self._laes()
        if self._find(data, indmelding_id) is None:
            raise KonfliktFejl("Indmeldingen findes ikke længere.")
        kommentar = Kommentar(indmelding_id, nuvaerende_bruger(), tekst, intern, nu(),
                              str(uuid.uuid4()))
        data["kommentarer"].append(vars(kommentar).copy())
        self._gem(data)
        return kommentar

    def slet(self, indmelding_id: str) -> None:
        self.datakilde.kraev_online("Ønsker & Udvikling")
        data = self._laes()
        data["indmeldinger"] = [i for i in data["indmeldinger"] if i["id"] != indmelding_id]
        for noegle in ("kommentarer", "historik"):
            data[noegle] = [x for x in data[noegle] if x["indmelding_id"] != indmelding_id]
        self._gem(data)
