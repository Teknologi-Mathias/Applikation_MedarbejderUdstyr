"""En opgave i en sag (onboarding eller offboarding), fx "Modtag telefon og SIM-kort"."""
import uuid
from datetime import date, datetime


# Opgavenavne fra V0.5.x -> udstyr. Bruges kun til ældre data uden "udstyr"-felt.
_KENDT_UDSTYR = {
    "Modtag tøj": "Tøj",
    "Modtag telefon og SIM-kort": "Telefon og SIM-kort",
    "Modtag og spær tankkort": "Tankkort",
    "Modtag andet udstyr": "Andet udstyr",
}


def udled_udstyr(opgavenavn):
    """Gæt udstyret ud fra et opgavenavn fra en ældre version ("" = intern opgave)."""
    if opgavenavn in _KENDT_UDSTYR:
        return _KENDT_UDSTYR[opgavenavn]
    if opgavenavn.startswith("Modtag andet: "):
        return opgavenavn.removeprefix("Modtag andet: ")
    return ""


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
        udstyr="",
        beskrivelse="",
        milepael="",
        afsluttet="",
    ):
        # Fast id, så Action Center kan pege direkte på opgaven.
        self.id = str(id) if id else str(uuid.uuid4())
        self.navn = str(navn).strip()
        self.ansvarlig = str(ansvarlig or "").strip()
        self.frist = str(frist or "")
        self.status = self.normaliser_status(status)
        self.obligatorisk = bool(obligatorisk)
        self.begrundelse = str(begrundelse or "").strip()
        self.naeste_handling = str(naeste_handling or "").strip()
        # Det udstyr medarbejderen skal returnere, fx "Telefon og SIM-kort".
        # Tom = intern opgave (fx "Er lukket i NAV?"), som ikke nævnes i rykkere.
        self.udstyr = str(udstyr or "").strip()
        self.beskrivelse = str(beskrivelse or "").strip()
        # Nøgle for den milepæl, opgaven hører til (fx "kontrakt"); tom = ingen.
        self.milepael = str(milepael or "").strip()
        # Tidspunkt hvor opgaven blev udført/undtaget – bruges til rapporter.
        self.afsluttet_tid = str(afsluttet or "")

    @classmethod
    def normaliser_status(cls, status):
        for tilladt in cls.STATUSER:
            if str(status).strip().lower() == tilladt.lower():
                return tilladt
        return cls.IKKE_STARTET

    @property
    def afsluttet(self):
        return self.status in self.AFSLUTTEDE

    def saet_status(self, status):
        """Skifter status og registrerer, hvornår opgaven blev afsluttet."""
        status = self.normaliser_status(status)
        if status in self.AFSLUTTEDE and not self.afsluttet:
            self.afsluttet_tid = datetime.now().isoformat(timespec="seconds")
        elif status not in self.AFSLUTTEDE:
            self.afsluttet_tid = ""
        self.status = status

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
            "udstyr": self.udstyr,
            "beskrivelse": self.beskrivelse,
            "milepael": self.milepael,
            "afsluttet": self.afsluttet_tid,
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
            data["udstyr"] if "udstyr" in data else udled_udstyr(data.get("navn", "")),
            data.get("beskrivelse", ""),
            data.get("milepael", ""),
            data.get("afsluttet", ""),
        )
