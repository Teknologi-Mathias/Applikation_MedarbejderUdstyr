"""JSON-lagring af Telefoner (Data/mdm_enheder.json) – kun udvikling/tests.

Gør det samme som RPC'erne i migrering 007/008, men uden databasens
adgangskontrol (rettigheder kontrolleres kun af MdmService).
"""
from app.domain.historik import nu, nuvaerende_bruger
from app.domain.mdm_enhed import GEMTE_FELTER, INFOFELTER, MdmEnhed
from app.infrastructure.stier import MDM_ENHEDER
from app.repositories.fejl import ValideringsFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import gem_json, hent_json


class JsonMdmRepository:
    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def _laes(self) -> list[dict]:
        return hent_json(self.datakilde.fil(MDM_ENHEDER), forventet=dict).get("enheder", [])

    def _gem(self, enheder: list[dict]) -> None:
        gem_json({"enheder": enheder}, self.datakilde.fil(MDM_ENHEDER))

    def hent_alle(self) -> list[MdmEnhed]:
        return [MdmEnhed.fra_dict(e) for e in self._laes()]

    def opret(self, enhed: MdmEnhed) -> MdmEnhed:
        self.datakilde.kraev_online("Telefoner")
        enheder = self._laes()
        if any(e["id"] == enhed.id for e in enheder):
            raise ValideringsFejl("Telefonen findes allerede.")
        tid = nu()
        ny = MdmEnhed(**{k: getattr(enhed, k) for k in INFOFELTER}, id=enhed.id,
                      oprettet_af=nuvaerende_bruger(), oprettet=tid, opdateret=tid)
        enheder.append(ny.til_dict())
        self._gem(enheder)
        return ny

    def opdater(self, aendringer: list[dict]) -> int:
        self.datakilde.kraev_online("Telefoner")
        enheder = {e["id"]: e for e in self._laes()}
        antal = 0
        for aendring in aendringer:
            post = enheder.get(aendring["id"])
            if post is None:
                continue
            for felt, vaerdi in aendring.items():
                if felt in GEMTE_FELTER:
                    post[felt] = vaerdi
            post["opdateret"] = nu()
            antal += 1
        self._gem(list(enheder.values()))
        return antal

    def slet(self, enhed_id: str) -> None:
        self.datakilde.kraev_online("Telefoner")
        self._gem([e for e in self._laes() if e["id"] != enhed_id])
