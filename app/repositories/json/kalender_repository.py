"""JSON-lagring af Kalender (Data/kalender.json) – kun udvikling/tests.

Gør det samme som RPC'erne i migrering 020 og 021 (ejer og opretter ud fra
login, deling på niveauer, administratorer ser alt, maskering af ledig/optaget
og private begivenheder, versionskontrol, dubletkontrol ved import), men UDEN
databasens beskyttelse: filen kan læses direkte. Brugerne, der deles med,
kontrolleres ikke mod brugerlisten. Kræver online-tilstand.
"""
import uuid
from datetime import datetime
from typing import Callable, Optional

from app.domain import kalender as kl
from app.domain.bruger import normaliser_brugernavn
from app.domain.historik import nuvaerende_bruger
from app.domain.kalender import Begivenhed, Deling, Kalender, serie_slut
from app.infrastructure.stier import KALENDER
from app.repositories.fejl import DataFejl, KonfliktFejl, ValideringsFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import fil_signatur, gem_json, hent_json

_TIDER = ("start", "slut", "oprindelig_start")
_KALENDERFELTER = ("navn", "farve", "ejer", "id", "version")
_RANG = {kl.EJER: 5, kl.SKRIVE: 4, kl.LAESE: 3, kl.ADMIN_ADGANG: 2, kl.FREEBUSY: 1}


def _ud(b: Begivenhed) -> dict:
    data = b.til_dict()
    for felt in _TIDER:
        data[felt] = data[felt].isoformat() if data[felt] else None
    data["undtagelser"] = [t.isoformat() for t in b.undtagelser]
    data.pop("maskeret", None)
    return data


def _ind(data: dict) -> Begivenhed:
    data = dict(data)
    for felt in _TIDER:
        data[felt] = datetime.fromisoformat(data[felt]) if data.get(felt) else None
    data["undtagelser"] = [datetime.fromisoformat(t) for t in data.get("undtagelser") or []]
    return Begivenhed(**data)


class JsonKalenderRepository:
    def __init__(self, datakilde: Datakilde,
                 aktuel_bruger: Callable[[], Optional[dict]] = lambda: None):
        self.datakilde = datakilde
        self._aktuel_bruger = aktuel_bruger

    def _laes(self) -> dict:
        data = hent_json(self.datakilde.fil(KALENDER), forventet=dict)
        return {"kalendre": data.get("kalendre", []), "begivenheder": data.get("begivenheder", []),
                "delinger": data.get("delinger", [])}

    def _gem(self, data: dict) -> None:
        gem_json(data, self.datakilde.fil(KALENDER))

    def _skriv(self) -> dict:
        self.datakilde.kraev_online("Kalender")
        return self._laes()

    ### ----- adgang (som inbase_calendar_access) ----------------------------

    def _er_admin(self) -> bool:
        return (self._aktuel_bruger() or {}).get("rolle") == "Administrator"

    def _adgang(self, data: dict, kalender: dict) -> Optional[str]:
        mig = normaliser_brugernavn(nuvaerende_bruger())
        if normaliser_brugernavn(kalender["ejer"]) == mig:
            return kl.EJER
        niveauer = [d["niveau"] for d in data["delinger"]
                    if d["kalender_id"] == kalender["id"] and d["brugernavn"] == mig]
        if self._er_admin():
            niveauer.append(kl.ADMIN_ADGANG)
        return max(niveauer, key=_RANG.get, default=None)

    def _kan_moderere(self, data: dict, kalender: dict) -> bool:
        return self._adgang(data, kalender) == kl.EJER or self._er_admin()

    def _find(self, data: dict, kalender_id: str) -> dict:
        kalender = next((k for k in data["kalendre"] if k["id"] == kalender_id), None)
        if kalender is None:
            raise KonfliktFejl("Kalenderen findes ikke længere.")
        return kalender

    def _kraev(self, data: dict, kalender_id: str, niveauer=(kl.EJER, kl.SKRIVE)) -> dict:
        kalender = self._find(data, kalender_id)
        if self._adgang(data, kalender) not in niveauer:
            raise DataFejl("Du har ikke rettighed til at ændre i denne kalender.")
        return kalender

    def _kraev_begivenhed(self, data: dict, b: Begivenhed, sletning: bool = False) -> None:
        kalender = self._find(data, b.kalender_id)
        if sletning and self._kan_moderere(data, kalender):
            return
        self._kraev(data, b.kalender_id)
        if b.privat and self._adgang(data, kalender) != kl.EJER:
            raise DataFejl("Begivenheden er privat – kun ejeren kan ændre den.")

    def _kalender(self, data: dict, k: dict) -> Kalender:
        delinger = [Deling(d["brugernavn"], d["brugernavn"], d["niveau"])
                    for d in data["delinger"] if d["kalender_id"] == k["id"]] \
            if self._kan_moderere(data, k) else []
        return Kalender(**{f: k[f] for f in _KALENDERFELTER}, adgang=self._adgang(data, k),
                        ejer_navn=k["ejer"], delinger=sorted(delinger, key=lambda d: d.brugernavn))

    ### ----- kalendere ------------------------------------------------------

    def kalendre(self) -> list[Kalender]:
        data = self._laes()
        return [self._kalender(data, k) for k in data["kalendre"] if self._adgang(data, k)]

    def opret_kalender(self, kalender: Kalender) -> Kalender:
        data = self._skriv()
        ny = {"navn": kalender.navn.strip(), "farve": kalender.farve, "ejer": nuvaerende_bruger(),
              "id": kalender.id or str(uuid.uuid4()), "version": 1}
        data["kalendre"].append(ny)
        self._gem(data)
        return self._kalender(data, ny)

    def opdater_kalender(self, kalender_id: str, version: int, aendringer: dict) -> Kalender:
        data = self._skriv()
        kalender = self._kraev(data, kalender_id, (kl.EJER,))
        if kalender["version"] != version:
            raise KonfliktFejl("Kalenderen er ændret et andet sted, efter du åbnede den.")
        kalender.update({k: v for k, v in aendringer.items() if k in ("navn", "farve")},
                        version=version + 1)
        self._gem(data)
        return self._kalender(data, kalender)

    def slet_kalender(self, kalender_id: str) -> None:
        data = self._skriv()
        if not self._kan_moderere(data, self._find(data, kalender_id)):
            raise DataFejl("Kun ejeren eller en administrator kan slette kalenderen.")
        for noegle in ("begivenheder", "delinger"):
            data[noegle] = [x for x in data[noegle] if x["kalender_id"] != kalender_id]
        data["kalendre"] = [k for k in data["kalendre"] if k["id"] != kalender_id]
        self._gem(data)

    ### ----- deling ---------------------------------------------------------

    def del_kalender(self, kalender_id: str, brugernavn: str, niveau: str) -> Kalender:
        data = self._skriv()
        kalender = self._find(data, kalender_id)
        if not self._kan_moderere(data, kalender):
            raise DataFejl("Kun ejeren eller en administrator kan dele kalenderen.")
        if niveau not in dict(kl.NIVEAUER):
            raise ValideringsFejl("Ukendt delingsniveau.")
        brugernavn = normaliser_brugernavn(brugernavn)
        if not brugernavn or brugernavn == normaliser_brugernavn(kalender["ejer"]):
            raise ValideringsFejl(f"Kalenderen tilhører allerede {brugernavn}.")
        data["delinger"] = [d for d in data["delinger"]
                            if not (d["kalender_id"] == kalender_id and d["brugernavn"] == brugernavn)]
        data["delinger"].append({"kalender_id": kalender_id, "brugernavn": brugernavn,
                                 "niveau": niveau})
        self._gem(data)
        return self._kalender(data, kalender)

    def fjern_deling(self, kalender_id: str, brugernavn: str) -> Kalender:
        data = self._skriv()
        kalender = self._find(data, kalender_id)
        brugernavn = normaliser_brugernavn(brugernavn)
        selv = brugernavn == normaliser_brugernavn(nuvaerende_bruger())
        if not selv and not self._kan_moderere(data, kalender):
            raise DataFejl("Kun ejeren eller en administrator kan fjerne delinger.")
        data["delinger"] = [d for d in data["delinger"]
                            if not (d["kalender_id"] == kalender_id and d["brugernavn"] == brugernavn)]
        self._gem(data)
        return self._kalender(data, kalender)

    ### ----- begivenheder ---------------------------------------------------

    def begivenheder(self, fra: datetime, til: datetime) -> list[Begivenhed]:
        data = self._laes()
        adgang = {k["id"]: self._adgang(data, k) for k in data["kalendre"]}
        alle = [_ind(b) for b in data["begivenheder"] if adgang.get(b["kalender_id"])]
        serier = {b.id for b in alle
                  if b.start < til and (serie_slut(b) is None or serie_slut(b) >= fra)}
        return [kl.masker(b) if kl.skal_maskeres(b, adgang[b.kalender_id]) else b
                for b in alle if b.id in serier or b.gentagelse_af in serier]

    def opret(self, begivenhed: Begivenhed) -> Begivenhed:
        data = self._skriv()
        self._kraev(data, begivenhed.kalender_id)
        ny = begivenhed.kopi(id=begivenhed.id or str(uuid.uuid4()), oprettet_af=nuvaerende_bruger(),
                             version=1, maskeret=False)
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
        self._kraev_begivenhed(data, gammel)
        self._kraev(data, begivenhed.kalender_id)
        if begivenhed.privat and not gammel.privat \
                and self._adgang(data, self._find(data, begivenhed.kalender_id)) != kl.EJER:
            raise DataFejl("Kun ejeren kan gøre en begivenhed privat.")
        if gammel.version != begivenhed.version:
            raise KonfliktFejl("Begivenheden er ændret et andet sted, efter du åbnede den. "
                               "Dine ændringer er ikke gemt – åbn den igen.")
        ny = begivenhed.kopi(gentagelse_af=gammel.gentagelse_af,
                             oprindelig_start=gammel.oprindelig_start, ical_uid=gammel.ical_uid,
                             oprettet_af=gammel.oprettet_af, version=gammel.version + 1,
                             maskeret=False)
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
        self._kraev_begivenhed(data, _ind(post), sletning=True)
        data["begivenheder"] = [b for b in data["begivenheder"]
                                if begivenhed_id not in (b["id"], b["gentagelse_af"])]
        self._gem(data)

    def importer(self, kalender_id: str, begivenheder: list[Begivenhed]) -> int:
        data = self._skriv()
        self._kraev(data, kalender_id)
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
                        oprettet_af=nuvaerende_bruger(), version=1, maskeret=False)
            data["begivenheder"].append(_ud(ny))
            kendte.add(noegle)
            antal += 1
        self._gem(data)
        return antal

    def signatur(self) -> tuple:
        return fil_signatur(self.datakilde.fil(KALENDER))
