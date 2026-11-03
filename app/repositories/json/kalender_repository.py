"""JSON-lagring af Kalender (Data/kalender.json) – kun udvikling/tests.

Gør det samme som RPC'erne i migrering 020 (ejer og opretter ud fra login,
kun egne kalendere, versionskontrol, dubletkontrol ved import), men UDEN
databasens adgangskontrol: filen er ikke beskyttet. Kræver online-tilstand.
"""
import uuid
from datetime import datetime

from app.domain.historik import nuvaerende_bruger
from app.domain.kalender import Begivenhed, Kalender, serie_slut
from app.infrastructure.stier import KALENDER
from app.repositories.fejl import DataFejl, KonfliktFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import fil_signatur, gem_json, hent_json

_TIDER = ("start", "slut", "oprindelig_start")


def _ud(b: Begivenhed) -> dict:
    data = b.til_dict()
    for felt in _TIDER:
        data[felt] = data[felt].isoformat() if data[felt] else None
    data["undtagelser"] = [t.isoformat() for t in b.undtagelser]
    return data


def _ind(data: dict) -> Begivenhed:
    data = dict(data)
    for felt in _TIDER:
        data[felt] = datetime.fromisoformat(data[felt]) if data.get(felt) else None
    data["undtagelser"] = [datetime.fromisoformat(t) for t in data.get("undtagelser") or []]
    return Begivenhed(**data)


class JsonKalenderRepository:
    def __init__(self, datakilde: Datakilde):
        self.datakilde = datakilde

    def _laes(self) -> dict:
        data = hent_json(self.datakilde.fil(KALENDER), forventet=dict)
        return {"kalendre": data.get("kalendre", []), "begivenheder": data.get("begivenheder", [])}

    def _gem(self, data: dict) -> None:
        gem_json(data, self.datakilde.fil(KALENDER))

    def _skriv(self) -> dict:
        self.datakilde.kraev_online("Kalender")
        return self._laes()

    @staticmethod
    def _egne(data: dict) -> dict:
        """Kalender-id -> kalender for den, der er logget på."""
        return {k["id"]: k for k in data["kalendre"] if k["ejer"] == nuvaerende_bruger()}

    def _kraev_egen(self, data: dict, kalender_id: str) -> dict:
        kalender = next((k for k in data["kalendre"] if k["id"] == kalender_id), None)
        if kalender is None:
            raise KonfliktFejl("Kalenderen findes ikke længere.")
        if kalender["ejer"] != nuvaerende_bruger():
            raise DataFejl("Du har ikke rettighed til at ændre i denne kalender.")
        return kalender

    ### ----- kalendere ------------------------------------------------------

    def kalendre(self) -> list[Kalender]:
        return [Kalender(**k) for k in self._egne(self._laes()).values()]

    def opret_kalender(self, kalender: Kalender) -> Kalender:
        data = self._skriv()
        ny = Kalender(kalender.navn.strip(), kalender.farve, nuvaerende_bruger(),
                      kalender.id or str(uuid.uuid4()), 1)
        data["kalendre"].append(vars(ny).copy())
        self._gem(data)
        return ny

    def opdater_kalender(self, kalender_id: str, version: int, aendringer: dict) -> Kalender:
        data = self._skriv()
        kalender = self._kraev_egen(data, kalender_id)
        if kalender["version"] != version:
            raise KonfliktFejl("Kalenderen er ændret et andet sted, efter du åbnede den.")
        kalender.update({k: v for k, v in aendringer.items() if k in ("navn", "farve")},
                        version=version + 1)
        self._gem(data)
        return Kalender(**kalender)

    def slet_kalender(self, kalender_id: str) -> None:
        data = self._skriv()
        self._kraev_egen(data, kalender_id)
        data["kalendre"] = [k for k in data["kalendre"] if k["id"] != kalender_id]
        data["begivenheder"] = [b for b in data["begivenheder"] if b["kalender_id"] != kalender_id]
        self._gem(data)

    ### ----- begivenheder ---------------------------------------------------

    def begivenheder(self, fra: datetime, til: datetime) -> list[Begivenhed]:
        data = self._laes()
        egne = self._egne(data)
        alle = [_ind(b) for b in data["begivenheder"] if b["kalender_id"] in egne]
        serier = {b.id for b in alle
                  if b.start < til and (serie_slut(b) is None or serie_slut(b) >= fra)}
        return [b for b in alle if b.id in serier or b.gentagelse_af in serier]

    def opret(self, begivenhed: Begivenhed) -> Begivenhed:
        data = self._skriv()
        self._kraev_egen(data, begivenhed.kalender_id)
        ny = begivenhed.kopi(id=begivenhed.id or str(uuid.uuid4()), oprettet_af=nuvaerende_bruger(),
                             version=1)
        if not ny.gentages:
            ny.undtagelser = []
        data["begivenheder"].append(_ud(ny))
        self._gem(data)
        return ny

    def opdater(self, begivenhed: Begivenhed) -> Begivenhed:
        data = self._skriv()
        index = next((i for i, b in enumerate(data["begivenheder"]) if b["id"] == begivenhed.id),
                     None)
        if index is None:
            raise KonfliktFejl("Begivenheden findes ikke længere – den er slettet et andet sted.")
        gammel = _ind(data["begivenheder"][index])
        self._kraev_egen(data, gammel.kalender_id)
        self._kraev_egen(data, begivenhed.kalender_id)
        if gammel.version != begivenhed.version:
            raise KonfliktFejl("Begivenheden er ændret et andet sted, efter du åbnede den. "
                               "Dine ændringer er ikke gemt – åbn den igen.")
        ny = begivenhed.kopi(gentagelse_af=gammel.gentagelse_af,
                             oprindelig_start=gammel.oprindelig_start, ical_uid=gammel.ical_uid,
                             oprettet_af=gammel.oprettet_af, version=gammel.version + 1)
        if not ny.gentages:
            ny.undtagelser = []
            data["begivenheder"] = [b for b in data["begivenheder"] if b["gentagelse_af"] != ny.id]
            index = next(i for i, b in enumerate(data["begivenheder"]) if b["id"] == ny.id)
        data["begivenheder"][index] = _ud(ny)
        self._gem(data)
        return ny

    def slet(self, begivenhed_id: str) -> None:
        data = self._skriv()
        post = next((b for b in data["begivenheder"] if b["id"] == begivenhed_id), None)
        if post is None:
            return
        self._kraev_egen(data, post["kalender_id"])
        data["begivenheder"] = [b for b in data["begivenheder"]
                                if begivenhed_id not in (b["id"], b["gentagelse_af"])]
        self._gem(data)

    def importer(self, kalender_id: str, begivenheder: list[Begivenhed]) -> int:
        data = self._skriv()
        self._kraev_egen(data, kalender_id)
        kendte = {(b["ical_uid"], b["oprindelig_start"]) for b in data["begivenheder"]
                  if b["kalender_id"] == kalender_id and b["ical_uid"]}
        antal = 0
        for b in sorted(begivenheder, key=lambda b: b.oprindelig_start is not None):
            noegle = (b.ical_uid, b.oprindelig_start.isoformat() if b.oprindelig_start else None)
            if b.ical_uid and noegle in kendte:
                continue
            serie = ""
            if b.oprindelig_start is not None:
                serie = next((s["id"] for s in data["begivenheder"]
                              if s["kalender_id"] == kalender_id and s["ical_uid"] == b.ical_uid
                              and not s["oprindelig_start"] and s["gentagelse"]), "")
                if not serie:
                    continue
            ny = b.kopi(kalender_id=kalender_id, id=str(uuid.uuid4()), gentagelse_af=serie,
                        oprettet_af=nuvaerende_bruger(), version=1)
            data["begivenheder"].append(_ud(ny))
            kendte.add(noegle)
            antal += 1
        self._gem(data)
        return antal

    def signatur(self) -> tuple:
        return fil_signatur(self.datakilde.fil(KALENDER))
