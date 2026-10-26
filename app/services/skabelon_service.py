"""Skabeloner: hentning, gem med versionering og valg af relevant skabelon.

Arbejdsgangsskabeloner (slags "sager") versionsstyres: når indholdet ændres,
gemmes den tidligere udgave i "versioner", og "version" tælles op. Sager
gemmer en reference til den version, de blev oprettet ud fra, og har deres
egne kopier af opgaverne – så ændringer rammer kun nye forløb.
"""
import copy
import logging

from app.domain import afhaengighed
from app.domain import skabelon as sk
from app.domain.historik import nu, nuvaerende_bruger
from app.repositories.base import SkabelonRepository
from app.repositories.fejl import ValideringsFejl

log = logging.getLogger(__name__)

_IKKE_INDHOLD = ("version", "versioner", "aktiv", "aendret", "aendret_af")
MAKS_VERSIONER = 25


def _indhold(skabelon: dict) -> dict:
    return {k: v for k, v in skabelon.items() if k not in _IKKE_INDHOLD}


class SkabelonService:
    def __init__(self, repo: SkabelonRepository):
        self.repo = repo

    def hent_alle(self) -> dict:
        return self.repo.hent_alle()

    def aktive(self, slags: str, proces: str | None = None) -> list[dict]:
        return sk.aktive(self.hent_alle(), slags, proces)

    def sagsskabeloner(self, proces: str, stilling: str | None = None) -> list[dict]:
        skabeloner = self.aktive(sk.SAG, proces)
        return sk.til_stilling(skabeloner, stilling) if stilling else skabeloner

    def gem(self, slags: str, skabelon: dict) -> dict:
        if not (skabelon.get("navn") or "").strip():
            raise ValideringsFejl("Skabelonen skal have et navn.")
        if slags == sk.SAG:
            fejl = afhaengighed.find_fejl(skabelon.get("opgaver") or [])
            if fejl:
                raise ValideringsFejl(" ".join(fejl))
        alle = self.hent_alle()
        liste = alle[slags]
        ny = copy.deepcopy(skabelon)
        index = next((i for i, s in enumerate(liste) if s["id"] == ny["id"]), None)
        if index is not None and slags == sk.SAG:
            gammel = liste[index]
            if _indhold(gammel) != _indhold(ny):
                forrige = {k: v for k, v in gammel.items() if k != "versioner"}
                ny["versioner"] = (gammel.get("versioner") or [])[-(MAKS_VERSIONER - 1):] + [forrige]
                ny["version"] = int(gammel.get("version", 1)) + 1
                log.info("Skabelon %s gemt som version %s", ny["navn"], ny["version"])
        ny["aendret"], ny["aendret_af"] = nu(), nuvaerende_bruger()
        self.repo.gem(slags, ny, len(liste) if index is None else index)
        return ny

    def skift_aktiv(self, slags: str, skabelon: dict) -> dict:
        return self.gem(slags, dict(skabelon, aktiv=not skabelon["aktiv"]))

    def relevant_mailskabelon(self, medarbejder) -> dict | None:
        return sk.relevant_mailskabelon(self.hent_alle(), medarbejder)
