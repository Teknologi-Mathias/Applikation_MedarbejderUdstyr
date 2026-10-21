"""En fratrådt medarbejder og dennes afviklingssag (opgaver, rykkere, tidslinje)."""
from datetime import timedelta

from app.historik import Historik
from app.opgave import Opgave, laes_iso_dato
from app.rykker import Rykker

# Udstyr fra V0.5.0-dataformatet -> (opgavenavn, ansvarlig, udstyr). Kun til konvertering.
_GAMMELT_UDSTYR = {
    "toej": ("Modtag tøj", "Administration", "Tøj"),
    "telefon": ("Modtag telefon og SIM-kort", "IT", "Telefon og SIM-kort"),
    "tankkort": ("Modtag og spær tankkort", "Administration", "Tankkort"),
    "andet": ("Modtag andet udstyr", "Administration", "Andet udstyr"),
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
        email="",
        tracking_link="",
        historik=None,
        rykkere=None,
        arkiveret="",
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
        self.email = str(email or "").strip()
        # Link til sporing af returforsendelsen (returlabel).
        self.tracking_link = str(tracking_link or "").strip()
        self.historik = historik if historik is not None else Historik()
        self.rykkere = list(rykkere or [])
        # Dato for arkivering – bruges af slettepolitikken.
        self.arkiveret = str(arkiveret or "")

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

    ### ----- opgaver og udstyr ----------------------------------------------

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

    def manglende_udstyr(self):
        """Udstyr der endnu ikke er afleveret, fx ["Telefon og SIM-kort", "Tøj"]."""
        return [o.udstyr for o in self.aabne_opgaver() if o.udstyr]

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

    ### ----- rykkere --------------------------------------------------------

    def find_rykker(self, rykker_id):
        for rykker in self.rykkere:
            if rykker.id == rykker_id:
                return rykker
        return None

    def usendte_rykkere(self):
        return [r for r in self.rykkere if not r.sendt]

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
            "email": self.email,
            "tracking_link": self.tracking_link,
            "arkiveret": self.arkiveret,
            "opgaver": [o.til_dict() for o in self.opgaver],
            "rykkere": [r.til_dict() for r in self.rykkere],
            "historik": self.historik.til_liste(),
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
                data.get("email", ""),
                data.get("tracking_link", ""),
                Historik(data.get("historik")),
                [Rykker.fra_dict(r) for r in data.get("rykkere") or []
                 if isinstance(r, dict)],
                data.get("arkiveret", ""),
            )
        else:
            medarbejder = cls._fra_gammelt_format(data)

        if "historik" not in data:
            medarbejder.historik.tilfoej(
                "Overført fra tidligere version",
                "Tidslinjen starter her; tidligere hændelser er ikke registreret.",
            )
        return medarbejder

    @classmethod
    def _fra_gammelt_format(cls, data):
        """Konverterer V0.5.0-data: udstyr bliver til opgaver.

        Var den gamle (manuelle) status en anden end den beregnede, låses den,
        så ingen medarbejder skifter status af sig selv ved opdateringen.
        """
        fratraedelse = data.get("fratraedelsesdato", "")
        udstyr = data.get("udstyr") if isinstance(data.get("udstyr"), dict) else {}
        opgaver = []
        for noegle, (navn, ansvarlig, genstand) in _GAMMELT_UDSTYR.items():
            post = udstyr.get(noegle)
            if not isinstance(post, dict) or not post.get("har"):
                continue
            beskrivelse = str(data.get("andet_beskrivelse") or "").strip()
            if noegle == "andet" and beskrivelse:
                navn, genstand = f"Modtag andet: {beskrivelse}", beskrivelse
            opgaver.append(Opgave(
                navn,
                ansvarlig,
                fratraedelse,
                Opgave.UDFOERT if post.get("afleveret") else Opgave.IKKE_STARTET,
                udstyr=genstand,
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
