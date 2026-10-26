"""Fælles basis for alle sager (onboarding- og offboardingforløb).

En sag har en stabil intern id (UUID), en person_id (samme person kan senere
have flere sager), opgaver, milepæle, en tidslinje og et versionsnummer til
optimistisk låsning. Status beregnes af underklassen ud fra opgaverne, men kan
låses manuelt med en begrundelse.

Opgaverne er parallelle: en opgave er kun blokeret af sine egne
forudsætninger (afhaenger_af), ikke af en fælles rækkefølge. Milepæle er
kontrolpunkter, som sagsstatus beregnes ud fra.

Lønnr. er bevidst IKKE identiteten: en kandidat kan oprettes uden lønnr.
"""
import uuid
from datetime import date, datetime
from typing import ClassVar, Optional

from app.domain.historik import Historik, nu
from app.domain.opgave import Opgave


def ny_uuid() -> str:
    return str(uuid.uuid4())


class Sag:
    PROCES: ClassVar[str] = ""
    STATUSER: ClassVar[tuple] = ()
    # Ordnede milepæle: ((nøgle, visningsnavn), ...). Tom = ingen milepæle.
    MILEPAELE: ClassVar[tuple] = ()

    def __init__(
        self,
        *,
        id: Optional[str] = None,
        person_id: Optional[str] = None,
        navn: str = "",
        loennr: str = "",
        kommentar: str = "",
        ansvarlig: str = "",
        opgaver=None,
        status_manuel: Optional[str] = None,
        status_begrundelse: str = "",
        historik: Optional[Historik] = None,
        version: int = 0,
        oprettet: str = "",
        opdateret: str = "",
        arkiveret: str = "",
        skabelon: Optional[dict] = None,
    ):
        self.id = str(id) if id else ny_uuid()
        self.person_id = str(person_id) if person_id else ny_uuid()
        self.navn = navn or ""
        self.loennr = str(loennr or "").strip()
        self.kommentar = kommentar or ""
        self.ansvarlig = str(ansvarlig or "").strip()
        self.opgaver = list(opgaver or [])
        self.status_manuel = (
            None if status_manuel in (None, "") else self.normaliser_status(status_manuel)
        )
        self.status_begrundelse = str(status_begrundelse or "").strip()
        self.historik = historik if historik is not None else Historik()
        self.version = int(version or 0)
        self.oprettet = oprettet or nu()
        self.opdateret = opdateret or self.oprettet
        self.arkiveret = str(arkiveret or "")
        # Hvilken skabelon (og version) sagen blev oprettet ud fra.
        self.skabelon = dict(skabelon or {})

    ### ----- status ---------------------------------------------------------

    @classmethod
    def normaliser_status(cls, status):
        for tilladt in cls.STATUSER:
            if str(status).strip().lower() == tilladt.lower():
                return tilladt
        return cls.STATUSER[0]

    @property
    def status(self) -> str:
        return self.status_manuel or self.beregnet_status()

    def beregnet_status(self) -> str:
        raise NotImplementedError

    def er_afsluttet(self) -> bool:
        """Sagens arbejde er gjort (klar til arkivering)."""
        raise NotImplementedError

    ### ----- opgaver og milepæle --------------------------------------------

    def find_opgave(self, opgave_id) -> Optional[Opgave]:
        return next((o for o in self.opgaver if o.id == opgave_id), None)

    def opgave_optaelling(self):
        """(antal afsluttede, antal i alt) – fx (3, 5)."""
        return sum(o.afsluttet for o in self.opgaver), len(self.opgaver)

    def opgave_tekst(self) -> str:
        afsluttede, total = self.opgave_optaelling()
        return f"{afsluttede}/{total} udført" if total else "Ingen opgaver"

    def milepael_faerdig(self, noegle: str) -> bool:
        return all(o.afsluttet for o in self.opgaver if o.milepael == noegle and o.obligatorisk)

    def aktiv_milepael(self) -> Optional[str]:
        """Første milepæl, der ikke er færdig (None = alle færdige)."""
        for noegle, _ in self.MILEPAELE:
            if not self.milepael_faerdig(noegle):
                return noegle
        return None

    def forudsaetninger(self, opgave: Opgave) -> list:
        """De forudsætninger (opgaver), der endnu ikke er afsluttet."""
        if not opgave.afhaenger_af:
            return []
        efter_noegle = {o.noegle: o for o in self.opgaver if o.noegle}
        return [efter_noegle[n] for n in opgave.afhaenger_af
                if n in efter_noegle and not efter_noegle[n].afsluttet]

    def er_blokeret(self, opgave: Opgave) -> bool:
        return not opgave.afsluttet and bool(self.forudsaetninger(opgave))

    def blokeringsaarsag(self, opgave: Opgave) -> str:
        """Fx "Venter på: Kontrakt (Administration)" – tom, hvis opgaven ikke er blokeret."""
        if opgave.afsluttet:
            return ""
        mangler = [f"{o.navn} ({o.afdeling})" if o.afdeling else o.navn
                   for o in self.forudsaetninger(opgave)]
        return "Venter på: " + ", ".join(mangler) if mangler else ""

    def milepael_navn(self, noegle: str) -> str:
        return dict(self.MILEPAELE).get(noegle, noegle)

    def aabne_opgaver(self):
        """Ikke-afsluttede opgaver, der kan udføres nu (ikke blokerede)."""
        return [o for o in self.opgaver if not o.afsluttet and not self.er_blokeret(o)]

    def forsinkede_opgaver(self, i_dag: date):
        return [o for o in self.aabne_opgaver() if o.er_forsinket(i_dag)]

    ### ----- tid ------------------------------------------------------------

    def sidste_aktivitet(self) -> Optional[datetime]:
        return self.historik.sidste_tid()

    ### ----- visning (overskrives af underklasser) --------------------------

    def startdato(self) -> str:
        """Dato som skabelonfrister regnes fra."""
        raise NotImplementedError

    def maaldato(self) -> str:
        """Dato forløbet skal være klar til (første arbejdsdag / sidste arbejdsdag)."""
        return self.startdato()

    def beskrivelse(self) -> str:
        """Kort undertitel til sagsvinduet."""
        return f"Lønnr. {self.loennr or '–'}"

    ### ----- JSON -----------------------------------------------------------

    def _basis_dict(self) -> dict:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "proces": self.PROCES,
            "navn": self.navn,
            "loennr": self.loennr,
            "status": self.status,
            "status_manuel": self.status_manuel is not None,
            "status_begrundelse": self.status_begrundelse,
            "kommentar": self.kommentar,
            "ansvarlig": self.ansvarlig,
            "version": self.version,
            "oprettet": self.oprettet,
            "opdateret": self.opdateret,
            "arkiveret": self.arkiveret,
            "skabelon": self.skabelon,
            "opgaver": [o.til_dict() for o in self.opgaver],
            "historik": self.historik.til_liste(),
        }

    @staticmethod
    def _basis_kwargs(data: dict) -> dict:
        return {
            "id": data.get("id"),
            "person_id": data.get("person_id"),
            "navn": data.get("navn", ""),
            "loennr": data.get("loennr", ""),
            "kommentar": data.get("kommentar", ""),
            "ansvarlig": data.get("ansvarlig", ""),
            "opgaver": [Opgave.fra_dict(o) for o in data.get("opgaver") or [] if isinstance(o, dict)],
            "status_manuel": data.get("status") if data.get("status_manuel") else None,
            "status_begrundelse": data.get("status_begrundelse", ""),
            "historik": Historik(data.get("historik")),
            "version": data.get("version", 0),
            "oprettet": data.get("oprettet", ""),
            "opdateret": data.get("opdateret", ""),
            "arkiveret": data.get("arkiveret", ""),
            "skabelon": data.get("skabelon"),
        }

    def til_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def fra_dict(cls, data: dict) -> "Sag":
        raise NotImplementedError

    def kopi(self) -> "Sag":
        """En selvstændig kopi, som dialoger kan ændre i uden at røre originalen."""
        return type(self).fra_dict(self.til_dict())
