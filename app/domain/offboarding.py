"""Offboarding: en fratrådt medarbejder og dennes afviklingssag.

Klassen hedder Medarbejder af historiske grunde (OffboardingSag er et alias).
Udover de fælles sagsfelter har den sidste arbejdsdag, e-mail, tracking-link
til returpakken og rykkere.
"""
from app.domain.historik import Historik
from app.domain.opgave import Opgave, laes_iso_dato
from app.domain.rykker import Rykker
from app.domain.sag import Sag

# Udstyr fra V0.5.0-dataformatet -> (opgavenavn, ansvarlig, udstyr). Kun til konvertering.
_GAMMELT_UDSTYR = {
    "toej": ("Modtag tøj", "Administration", "Tøj"),
    "telefon": ("Modtag telefon og SIM-kort", "IT", "Telefon og SIM-kort"),
    "tankkort": ("Modtag og spær tankkort", "Administration", "Tankkort"),
    "andet": ("Modtag andet udstyr", "Administration", "Andet udstyr"),
}


class Medarbejder(Sag):
    PROCES = "offboarding"

    STATUS_AFVENTER = "Afventer Udstyr"
    STATUS_DELVIST = "Delvist afleveret"
    STATUS_AFVIKLET = "Afviklet"
    STATUSER = (STATUS_AFVENTER, STATUS_DELVIST, STATUS_AFVIKLET)

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
        **basis,
    ):
        super().__init__(
            navn=navn, loennr=loennr, kommentar=kommentar, opgaver=opgaver,
            status_manuel=status_manuel, status_begrundelse=status_begrundelse,
            historik=historik, arkiveret=arkiveret, **basis,
        )
        self.fratraedelsesdato = fratraedelsesdato
        self.email = str(email or "").strip()
        # Link til sporing af returforsendelsen (returlabel).
        self.tracking_link = str(tracking_link or "").strip()
        self.rykkere = list(rykkere or [])

    ### ----- status ---------------------------------------------------------

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

    def er_afsluttet(self):
        return self.status == self.STATUS_AFVIKLET

    ### ----- udstyr og datoer -----------------------------------------------

    def manglende_udstyr(self):
        """Udstyr der endnu ikke er afleveret, fx ["Telefon og SIM-kort", "Tøj"]."""
        return [o.udstyr for o in self.aabne_opgaver() if o.udstyr]

    def startdato(self):
        return self.fratraedelsesdato

    def beskrivelse(self):
        dato = laes_iso_dato(self.fratraedelsesdato)
        vis = dato.strftime("%d-%m-%Y") if dato else str(self.fratraedelsesdato)
        return f"Lønnummer {self.loennr or '–'} · Sidste arbejdsdag {vis}"

    def flyt_fratraedelse(self, ny_dato):
        """Ændrer fratrædelsesdatoen og flytter åbne opgavers frister med samme antal dage."""
        gammel, ny = laes_iso_dato(self.fratraedelsesdato), laes_iso_dato(ny_dato)
        if gammel is not None and ny is not None and gammel != ny:
            forskel = ny - gammel
            for opgave in self.opgaver:
                frist = opgave.frist_dato()
                if frist is not None and not opgave.afsluttet:
                    opgave.frist = (frist + forskel).isoformat()
        self.fratraedelsesdato = ny_dato

    ### ----- rykkere --------------------------------------------------------

    def find_rykker(self, rykker_id):
        return next((r for r in self.rykkere if r.id == rykker_id), None)

    def usendte_rykkere(self):
        return [r for r in self.rykkere if not r.sendt]

    ### ----- JSON -----------------------------------------------------------

    def til_dict(self):
        return {
            **self._basis_dict(),
            "fratraedelsesdato": self.fratraedelsesdato,
            "email": self.email,
            "tracking_link": self.tracking_link,
            "rykkere": [r.til_dict() for r in self.rykkere],
        }

    @classmethod
    def fra_dict(cls, data):
        if "opgaver" in data:
            basis = cls._basis_kwargs(data)
            medarbejder = cls(
                basis.pop("loennr"),
                basis.pop("navn"),
                data.get("fratraedelsesdato", ""),
                email=data.get("email", ""),
                tracking_link=data.get("tracking_link", ""),
                rykkere=[Rykker.fra_dict(r) for r in data.get("rykkere") or []
                         if isinstance(r, dict)],
                **basis,
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
            historik=Historik(),
        )
        gammel_status = cls.normaliser_status(data.get("status", cls.STATUS_AFVENTER))
        if gammel_status != medarbejder.beregnet_status():
            medarbejder.status_manuel = gammel_status
            medarbejder.status_begrundelse = "Overført fra tidligere version"
        return medarbejder


OffboardingSag = Medarbejder
