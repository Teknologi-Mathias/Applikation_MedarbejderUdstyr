class Medarbejder:
    STATUS_AFVENTER = "Afventer Udstyr"
    STATUS_DELVIST = "Delvist afleveret"
    STATUS_AFVIKLET = "Afviklet"

    STATUSER = (
        STATUS_AFVENTER,
        STATUS_DELVIST,
        STATUS_AFVIKLET,
    )

    # Udstyr der kan krydses af: (nøgle i JSON, visningsnavn).
    # Tilføj en linje her for at få en ny type udstyr i hele programmet.
    UDSTYR = (
        ("toej", "Tøj"),
        ("telefon", "Telefon"),
        ("tankkort", "Tankkort"),
        ("andet", "Andet"),
    )

    def __init__(
        self,
        loennr,
        navn,
        fratraedelsesdato,
        status,
        kommentar="",
        udstyr=None,
        andet_beskrivelse="",
    ):
        self.loennr = str(loennr).strip()
        self.navn = navn
        self.fratraedelsesdato = fratraedelsesdato
        self.status = self.normaliser_status(status)
        self.kommentar = "" if kommentar is None else kommentar
        self.udstyr = self.normaliser_udstyr(udstyr)
        self.andet_beskrivelse = (
            "" if andet_beskrivelse is None else str(andet_beskrivelse).strip()
        )

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

    ### ----- udstyr ---------------------------------------------------------

    @classmethod
    def normaliser_udstyr(cls, udstyr):
        """Returnerer {nøgle: {"har": bool, "afleveret": bool}} for alt udstyr.

        Manglende eller ugyldige data (fx fra versioner før V0.6) bliver til
        "har ikke". Udstyr kan kun være afleveret, hvis det er krydset af.
        """
        udstyr = udstyr if isinstance(udstyr, dict) else {}
        resultat = {}
        for noegle, _ in cls.UDSTYR:
            post = udstyr.get(noegle)
            post = post if isinstance(post, dict) else {}
            har = bool(post.get("har", False))
            resultat[noegle] = {
                "har": har,
                "afleveret": har and bool(post.get("afleveret", False)),
            }
        return resultat

    def udstyr_navn(self, noegle):
        navn = dict(self.UDSTYR)[noegle]
        if noegle == "andet" and self.andet_beskrivelse:
            return f"{navn}: {self.andet_beskrivelse}"
        return navn

    def udstyr_optaelling(self):
        """(antal afleveret, antal krydset af) – fx (2, 4)."""
        valgte = [post for post in self.udstyr.values() if post["har"]]
        return sum(post["afleveret"] for post in valgte), len(valgte)

    def udstyr_tekst(self):
        afleveret, total = self.udstyr_optaelling()
        return f"{afleveret}/{total} afleveret" if total else "Intet udstyr"

    def manglende_udstyr(self):
        return [
            self.udstyr_navn(noegle)
            for noegle, _ in self.UDSTYR
            if self.udstyr[noegle]["har"] and not self.udstyr[noegle]["afleveret"]
        ]

    ### ----- JSON -----------------------------------------------------------

    def til_dict(self):
        return {
            "loennr": self.loennr,
            "navn": self.navn,
            "fratraedelsesdato": self.fratraedelsesdato,
            "status": self.status,
            "kommentar": self.kommentar,
            "udstyr": {noegle: dict(post) for noegle, post in self.udstyr.items()},
            "andet_beskrivelse": self.andet_beskrivelse,
        }

    @classmethod
    def fra_dict(cls, data):
        return cls(
            data["loennr"],
            data.get("navn", ""),
            data.get("fratraedelsesdato", ""),
            data.get("status", cls.STATUS_AFVENTER),
            data.get("kommentar", ""),
            data.get("udstyr"),
            data.get("andet_beskrivelse", ""),
        )
