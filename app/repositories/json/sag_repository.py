"""JSON-lagring af sager: én fil til aktive og én til arkiverede.

Bruges til både offboarding (medarbejdere.json / arkiv.json) og onboarding
(onboarding.json / onboarding_arkiv.json).

- Sager findes på deres id (UUID) – aldrig på lønnr.
- Hver skrivning læser filen forfra og ændrer kun den ene sag, så kollegers
  samtidige ændringer i andre sager ikke overskrives.
- Optimistisk låsning: er sagen gemt af en anden siden den blev hentet
  (versionen afviger), afvises skrivningen med KonfliktFejl.
- Arkivering skriver arkivet først og fjerner derefter fra aktive. Afbrydes
  det midtvejs, ligger sagen i begge filer; den vises så som arkiveret.
"""
import logging
from typing import Optional, Type

from app.domain.historik import nu
from app.domain.sag import Sag
from app.repositories.fejl import DataFejl, KonfliktFejl
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import fil_signatur, gem_json, hent_json

log = logging.getLogger(__name__)


class JsonSagRepository:
    def __init__(self, datakilde: Datakilde, sagstype: Type[Sag],
                 aktiv_filnavn: str, arkiv_filnavn: str):
        self.datakilde = datakilde
        self.sagstype = sagstype
        self.proces = sagstype.PROCES
        self.aktiv_filnavn = aktiv_filnavn
        self.arkiv_filnavn = arkiv_filnavn

    ### ----- læsning --------------------------------------------------------

    def _laes(self, filnavn: str) -> list[dict]:
        return [p for p in hent_json(self.datakilde.fil(filnavn)) if isinstance(p, dict)]

    def _til_sager(self, poster: list[dict]) -> list[Sag]:
        sager = []
        for post in poster:
            try:
                sager.append(self.sagstype.fra_dict(post))
            except Exception as fejl:
                # En enkelt ødelagt post må ikke vælte hele listen – men den
                # skal ikke forsvinde tavst: log den, og meld fejl.
                log.exception("Ugyldig sag i %s: %r", self.proces, post.get("id"))
                raise DataFejl(
                    f"En {self.proces}-sag kunne ikke indlæses ({fejl}). Se logfilen."
                ) from fejl
        return sager

    def hent_aktive(self) -> list[Sag]:
        arkiv_ids = {p.get("id") for p in self._laes(self.arkiv_filnavn) if p.get("id")}
        aktive = []
        for post in self._laes(self.aktiv_filnavn):
            if post.get("id") and post["id"] in arkiv_ids:
                log.warning("Sag %s findes både som aktiv og arkiveret – vises som arkiveret",
                            post["id"])
                continue
            aktive.append(post)
        return self._til_sager(aktive)

    def hent_arkiverede(self) -> list[Sag]:
        return self._til_sager(self._laes(self.arkiv_filnavn))

    def hent(self, sag_id: str) -> Optional[Sag]:
        for sag in self.hent_arkiverede() + self.hent_aktive():
            if sag.id == sag_id:
                return sag
        return None

    def signatur(self) -> tuple:
        return fil_signatur(
            self.datakilde.fil(self.aktiv_filnavn), self.datakilde.fil(self.arkiv_filnavn)
        )

    ### ----- skrivning ------------------------------------------------------

    @staticmethod
    def _find(poster: list[dict], sag_id: str) -> Optional[int]:
        return next((i for i, p in enumerate(poster) if p.get("id") == sag_id), None)

    def _tjek_version(self, post: Optional[dict], sag: Sag) -> None:
        if post is None:
            if sag.version:
                raise KonfliktFejl(
                    f"{sag.navn} findes ikke længere – den er slettet eller flyttet af en anden."
                )
            return
        gemt = int(post.get("version", 0) or 0)
        if gemt != sag.version:
            raise KonfliktFejl(
                f"{sag.navn} er ændret af {self._sidst_af(post)}, efter du åbnede sagen. "
                "Dine ændringer er ikke gemt – åbn sagen igen og gentag dem."
            )

    @staticmethod
    def _sidst_af(post: dict) -> str:
        historik = post.get("historik") or []
        return historik[-1].get("bruger", "en anden") if historik else "en anden"

    def _ny_post(self, sag: Sag) -> dict:
        data = sag.til_dict()
        data["version"] = sag.version + 1
        data["opdateret"] = nu()
        return data

    def _efter_skrivning(self, sag: Sag, data: dict, op: str, basis: int) -> Sag:
        sag.version = data["version"]
        sag.opdateret = data["opdateret"]
        self.datakilde.registrer_aendring(self.proces, op, sag.id, basis, data)
        return sag

    def gem(self, sag: Sag) -> Sag:
        """Opretter eller opdaterer sagen, der hvor den ligger (aktiv eller arkiv)."""
        for filnavn in (self.aktiv_filnavn, self.arkiv_filnavn):
            poster = self._laes(filnavn)
            index = self._find(poster, sag.id)
            if index is not None:
                break
        else:
            filnavn, poster, index = self.aktiv_filnavn, self._laes(self.aktiv_filnavn), None

        self._tjek_version(None if index is None else poster[index], sag)
        basis = sag.version
        data = self._ny_post(sag)
        if index is None:
            poster.append(data)
        else:
            poster[index] = data
        gem_json(poster, self.datakilde.fil(filnavn))
        return self._efter_skrivning(sag, data, "gem", basis)

    def _flyt(self, sag: Sag, fra: str, til: str, op: str) -> Sag:
        fra_poster, til_poster = self._laes(fra), self._laes(til)
        index = self._find(fra_poster, sag.id)
        self._tjek_version(None if index is None else fra_poster[index], sag)
        basis = sag.version
        data = self._ny_post(sag)
        til_poster = [p for p in til_poster if p.get("id") != sag.id] + [data]
        # Målfilen skrives først: går noget galt midtvejs, findes sagen hellere
        # to steder end ingen steder.
        gem_json(til_poster, self.datakilde.fil(til))
        if index is not None:
            del fra_poster[index]
            gem_json(fra_poster, self.datakilde.fil(fra))
        return self._efter_skrivning(sag, data, op, basis)

    def arkiver(self, sag: Sag) -> Sag:
        return self._flyt(sag, self.aktiv_filnavn, self.arkiv_filnavn, "arkiver")

    def aktiver(self, sag: Sag) -> Sag:
        return self._flyt(sag, self.arkiv_filnavn, self.aktiv_filnavn, "aktiver")

    def slet(self, sag: Sag) -> None:
        for filnavn in (self.arkiv_filnavn, self.aktiv_filnavn):
            poster = self._laes(filnavn)
            index = self._find(poster, sag.id)
            if index is not None:
                self._tjek_version(poster[index], sag)
                del poster[index]
                gem_json(poster, self.datakilde.fil(filnavn))
        self.datakilde.registrer_aendring(self.proces, "slet", sag.id, sag.version, None)

    ### ----- migrering ------------------------------------------------------

    def kraever_migrering(self) -> bool:
        for filnavn in (self.aktiv_filnavn, self.arkiv_filnavn):
            for post in self._laes(filnavn):
                if not post.get("id") or "version" not in post or "historik" not in post \
                        or "proces" not in post:
                    return True
        return False

    def migrer(self) -> int:
        """Giver ældre poster id, person_id, version og tidslinje og gemmer dem.

        Indholdet ændres ikke ud over de nye felter (fx konverteres V0.5.0-udstyr
        til opgaver). Kaldes kun efter en backup (se bootstrap).
        """
        aendret = 0
        for filnavn in (self.aktiv_filnavn, self.arkiv_filnavn):
            poster = self._laes(filnavn)
            nye = []
            for post in poster:
                if post.get("id") and "version" in post and "historik" in post \
                        and "proces" in post:
                    nye.append(post)
                    continue
                sag = self.sagstype.fra_dict(post)
                data = sag.til_dict()
                data["version"] = int(post.get("version", 0) or 0)
                nye.append(data)
                aendret += 1
            if nye != poster:
                gem_json(nye, self.datakilde.fil(filnavn))
        if aendret:
            log.info("Migrerede %d %s-sager til nyt format", aendret, self.proces)
        return aendret
