"""En fratrådt medarbejder og dennes afviklingssag (listen af opgaver)."""
from datetime import timedelta

from app.opgave import Opgave, laes_iso_dato

# Udstyr fra V0.5.x-dataformatet -> (opgavenavn, ansvarlig). Kun til konvertering.
_GAMMELT_UDSTYR = {
    "toej": ("Modtag tøj", "Administration"),
    "telefon": ("Modtag telefon og SIM-kort", "IT"),
    "tankkort": ("Modtag og spær tankkort", "Administration"),
    "andet": ("Modtag andet udstyr", "Administration"),
}


class Medarbejder:
    STATUS_AFVENTER = "Afventer Udstyr"
    STATUS_DELVIST = "Delvist afleveret"
    STATUS_AFVIKLET = "Afviklet"

    STATUSER = (
        STATUS_AFVENTER,
        STATUS_DELVIST,
        STATUS_AFVIKLET,
    )

    def __init__(
        self,
        loennr,
        navn,
        fratraedelsesdato,
        kommentar="",
        opgaver=None,
        status_manuel=None,
        status_begrundelse="",
    ):
        self.loennr = str(loennr).strip()
        self.navn = navn
        self.fratraedelsesdato = fratraedelsesdato
        self.kommentar = "" if kommentar is None else kommentar
        self.opgaver = list(opgaver or [])
        # None = status beregnes ud fra opgaverne; ellers en låst status.
        self.status_manuel = (
            None if status_manuel is None else self.normaliser_status(status_manuel)
        )
        self.status_begrundelse = str(status_begrundelse or "").strip()

    ### ----- status ---------------------------------------------------------

    @classmethod
    def normaliser_status(cls, status):
        """Sikrer at status altid er en af de tilladte værdier.

        Ukendte eller manglende statuser bliver til "Afventer Udstyr", som er
        den sikreste standard: medarbejderen dukker op på dashboardet i stedet
        for at forsvinde stille.
        """
        for tilladt in cls.STATUSER:
            if str(status).strip().lower() == tilladt.lower():
                return tilladt
        return cls.STATUS_AFVENTER

    @property
    def status(self):
        return self.status_manuel or self.beregnet_status()

    def beregnet_status(self):
        """Status ud fra opgaverne.

        - Alle obligatoriske opgaver afsluttet       -> Afviklet
        - Mindst én opgave er påbegyndt eller udført -> Delvist afleveret
        - Ellers (eller ingen opgaver)               -> Afventer Udstyr
        """
        if not self.opgaver:
            return self.STATUS_AFVENTER
        if all(o.afsluttet for o in self.opgaver if o.obligatorisk):
            return self.STATUS_AFVIKLET
        if any(o.status in (Opgave.I_GANG, Opgave.AFVENTER, Opgave.UDFOERT)
               for o in self.opgaver):
            return self.STATUS_DELVIST
        return self.STATUS_AFVENTER

    ### ----- opgaver --------------------------------------------------------

    def find_opgave(self, opgave_id):
        for opgave in self.opgaver:
            if opgave.id == opgave_id:
                return opgave
        return None

    def opgave_optaelling(self):
        """(antal afsluttede, antal i alt) – fx (3, 5)."""
        return sum(o.afsluttet for o in self.opgaver), len(self.opgaver)

    def opgave_tekst(self):
        afsluttede, total = self.opgave_optaelling()
        return f"{afsluttede}/{total} udført" if total else "Ingen opgaver"

    def aabne_opgaver(self):
        return [o for o in self.opgaver if not o.afsluttet]

    def forsinkede_opgaver(self, i_dag):
        return [o for o in self.opgaver if o.er_forsinket(i_dag)]

    def flyt_fratraedelse(self, ny_dato):
        """Ændrer fratrædelsesdatoen og flytter åbne opgavers frister med samme antal dage."""
        gammel, ny = laes_iso_dato(self.fratraedelsesdato), laes_iso_dato(ny_dato)
        if gammel is not None and ny is not None and gammel != ny:
            forskel = ny - gammel
            for opgave in self.aabne_opgaver():
                frist = opgave.frist_dato()
                if frist is not None:
                    opgave.frist = (frist + forskel).isoformat()
        self.fratraedelsesdato = ny_dato

    ### ----- JSON -----------------------------------------------------------

    def kopi(self):
        """En selvstændig kopi, som dialoger kan ændre i uden at røre originalen."""
        return Medarbejder.fra_dict(self.til_dict())

    def til_dict(self):
        return {
            "loennr": self.loennr,
            "navn": self.navn,
            "fratraedelsesdato": self.fratraedelsesdato,
            # "status" gemmes også, så filen kan læses af mennesker.
            "status": self.status,
            "status_manuel": self.status_manuel is not None,
            "status_begrundelse": self.status_begrundelse,
            "kommentar": self.kommentar,
            "opgaver": [o.til_dict() for o in self.opgaver],
        }

    @classmethod
    def fra_dict(cls, data):
        if "opgaver" in data:
            opgaver = [
                Opgave.fra_dict(o) for o in data.get("opgaver") or []
                if isinstance(o, dict)
            ]
            medarbejder = cls(
                data["loennr"],
                data.get("navn", ""),
                data.get("fratraedelsesdato", ""),
                data.get("kommentar", ""),
                opgaver,
                data.get("status") if data.get("status_manuel") else None,
                data.get("status_begrundelse", ""),
            )
        else:
            medarbejder = cls._fra_gammelt_format(data)
        return medarbejder

    @classmethod
    def _fra_gammelt_format(cls, data):
        """Konverterer V0.5.x-data: udstyr bliver til opgaver.

        Var den gamle (manuelle) status en anden end den beregnede, låses den,
        så ingen medarbejder skifter status af sig selv ved opdateringen.
        """
        fratraedelse = data.get("fratraedelsesdato", "")
        udstyr = data.get("udstyr") if isinstance(data.get("udstyr"), dict) else {}
        opgaver = []
        for noegle, (navn, ansvarlig) in _GAMMELT_UDSTYR.items():
            post = udstyr.get(noegle)
            if not isinstance(post, dict) or not post.get("har"):
                continue
            beskrivelse = str(data.get("andet_beskrivelse") or "").strip()
            if noegle == "andet" and beskrivelse:
                navn = f"Modtag andet: {beskrivelse}"
            opgaver.append(Opgave(
                navn,
                ansvarlig,
                fratraedelse,
                Opgave.UDFOERT if post.get("afleveret") else Opgave.IKKE_STARTET,
            ))

        medarbejder = cls(
            data["loennr"],
            data.get("navn", ""),
            fratraedelse,
            data.get("kommentar", ""),
            opgaver,
        )
        gammel_status = cls.normaliser_status(data.get("status", cls.STATUS_AFVENTER))
        if gammel_status != medarbejder.beregnet_status():
            medarbejder.status_manuel = gammel_status
            medarbejder.status_begrundelse = "Overført fra tidligere version"
        return medarbejder


def frist_fra_dage(fratraedelsesdato, dage):
    """Frist som ISO-dato: fratrædelsesdato + antal dage (tom ved ugyldig dato)."""
    dato = laes_iso_dato(fratraedelsesdato)
    return (dato + timedelta(days=int(dage))).isoformat() if dato else ""
