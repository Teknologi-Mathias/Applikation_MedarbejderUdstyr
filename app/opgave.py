"""En opgave i en afviklingssag, fx "Modtag telefon og SIM-kort"."""
import uuid
from datetime import date


def laes_iso_dato(tekst):
    """"2026-11-30" -> date, eller None hvis teksten ikke er en gyldig dato."""
    try:
        return date.fromisoformat(str(tekst))
    except ValueError:
        return None


class Opgave:
    IKKE_STARTET = "Ikke startet"
    I_GANG = "I gang"
    AFVENTER = "Afventer"
    UDFOERT = "Udført"
    UNDTAGET = "Undtaget"

    STATUSER = (IKKE_STARTET, I_GANG, AFVENTER, UDFOERT, UNDTAGET)
    # En opgave er afsluttet, når den er udført eller bevidst undtaget.
    AFSLUTTEDE = (UDFOERT, UNDTAGET)

    def __init__(
        self,
        navn,
        ansvarlig="",
        frist="",
        status=IKKE_STARTET,
        obligatorisk=True,
        begrundelse="",
        naeste_handling="",
        id=None,
    ):
        # Fast id, så Action Center kan pege direkte på opgaven.
        self.id = str(id) if id else uuid.uuid4().hex[:12]
        self.navn = str(navn).strip()
        self.ansvarlig = str(ansvarlig or "").strip()
        self.frist = str(frist or "")
        self.status = self.normaliser_status(status)
        self.obligatorisk = bool(obligatorisk)
        self.begrundelse = str(begrundelse or "").strip()
        self.naeste_handling = str(naeste_handling or "").strip()

    @classmethod
    def normaliser_status(cls, status):
        for tilladt in cls.STATUSER:
            if str(status).strip().lower() == tilladt.lower():
                return tilladt
        return cls.IKKE_STARTET

    @property
    def afsluttet(self):
        return self.status in self.AFSLUTTEDE

    def frist_dato(self):
        return laes_iso_dato(self.frist)

    def dage_over_frist(self, i_dag):
        """Dage efter fristen (negativ = fristen er ikke nået endnu).

        None, hvis opgaven er afsluttet eller ikke har en gyldig frist.
        """
        frist = self.frist_dato()
        if self.afsluttet or frist is None:
            return None
        return (i_dag - frist).days

    def er_forsinket(self, i_dag):
        dage = self.dage_over_frist(i_dag)
        return dage is not None and dage > 0

    def til_dict(self):
        return {
            "id": self.id,
            "navn": self.navn,
            "ansvarlig": self.ansvarlig,
            "frist": self.frist,
            "status": self.status,
            "obligatorisk": self.obligatorisk,
            "begrundelse": self.begrundelse,
            "naeste_handling": self.naeste_handling,
        }

    @classmethod
    def fra_dict(cls, data):
        return cls(
            data.get("navn", ""),
            data.get("ansvarlig", ""),
            data.get("frist", ""),
            data.get("status", cls.IKKE_STARTET),
            data.get("obligatorisk", True),
            data.get("begrundelse", ""),
            data.get("naeste_handling", ""),
            data.get("id"),
        )
