class Medarbejder:
    STATUS_AFVENTER = "Afventer Udstyr"
    STATUS_DELVIST = "Delvist afleveret"
    STATUS_AFVIKLET = "Afviklet"

    STATUSER = (
        STATUS_AFVENTER,
        STATUS_DELVIST,
        STATUS_AFVIKLET,
    )

    def __init__(self, loennr, navn, fratraedelsesdato, status, kommentar=""):
        self.loennr = str(loennr).strip()
        self.navn = navn
        self.fratraedelsesdato = fratraedelsesdato
        self.status = self.normaliser_status(status)
        self.kommentar = "" if kommentar is None else kommentar

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

    def til_dict(self):
        """Gør objektet klar til JSON."""
        return {
            "loennr": self.loennr,
            "navn": self.navn,
            "fratraedelsesdato": self.fratraedelsesdato,
            "status": self.status,
            "kommentar": self.kommentar,
        }

    @classmethod
    def fra_dict(cls, data):
        """Opretter en Medarbejder ud fra et dictionary (fx fra JSON)."""
        return cls(
            data["loennr"],
            data.get("navn", ""),
            data.get("fratraedelsesdato", ""),
            data.get("status", cls.STATUS_AFVENTER),
            data.get("kommentar", ""),
        )
