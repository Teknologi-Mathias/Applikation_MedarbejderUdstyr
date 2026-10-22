"""En rykker (påmindelses-mail) til en fratrådt medarbejder.

Programmet kan kun se, at en kladde er oprettet i mailprogrammet – ikke om
den faktisk er sendt. Derfor skal brugeren selv markere rykkeren som sendt.
"""
import uuid
from datetime import date, datetime

from app.domain.historik import nuvaerende_bruger


class Rykker:
    KLADDE = "Kladde oprettet"
    SENDT = "Sendt"

    def __init__(self, skabelon_navn, kategori, emne, frist, oprettet=None,
                 oprettet_af=None, sendt="", sendt_af="", id=None):
        self.id = str(id) if id else uuid.uuid4().hex[:12]
        self.skabelon_navn = skabelon_navn
        self.kategori = kategori
        self.emne = emne
        self.frist = frist
        self.oprettet = oprettet or datetime.now().isoformat(timespec="seconds")
        self.oprettet_af = oprettet_af or nuvaerende_bruger()
        self.sendt = sendt or ""
        self.sendt_af = sendt_af or ""

    @property
    def status(self):
        return self.SENDT if self.sendt else self.KLADDE

    def marker_sendt(self):
        self.sendt = datetime.now().isoformat(timespec="seconds")
        self.sendt_af = nuvaerende_bruger()

    def dage_siden(self, felt, i_dag):
        """Dage siden oprettet/sendt (felt = "oprettet" eller "sendt")."""
        vaerdi = getattr(self, felt)
        if not vaerdi:
            return None
        try:
            return (i_dag - date.fromisoformat(vaerdi[:10])).days
        except ValueError:
            return None

    def til_dict(self):
        return {
            "id": self.id,
            "skabelon_navn": self.skabelon_navn,
            "kategori": self.kategori,
            "emne": self.emne,
            "frist": self.frist,
            "oprettet": self.oprettet,
            "oprettet_af": self.oprettet_af,
            "sendt": self.sendt,
            "sendt_af": self.sendt_af,
        }

    @classmethod
    def fra_dict(cls, data):
        return cls(
            data.get("skabelon_navn", ""),
            data.get("kategori", ""),
            data.get("emne", ""),
            data.get("frist", ""),
            data.get("oprettet"),
            data.get("oprettet_af"),
            data.get("sendt", ""),
            data.get("sendt_af", ""),
            data.get("id"),
        )
