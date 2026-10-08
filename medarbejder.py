class Medarbejder:
    STATUSER = (
        "Afventer Udstyr",
        "Delvist afleveret",
        "Afviklet",
    )

    def __init__(self, loennr, navn, fratraedelsesdato, status, kommentar):
        self.loennr = loennr
        self.navn = navn
        self.fratraedelsesdato = fratraedelsesdato
        self.status = status
        self.kommentar = kommentar        



    def til_dict(self):
        """Gør objektet klar til JSON.

        TODO:
        - Beslut præcis hvilke felter der skal gemmes.
        - Overvej hvad der skal ske, hvis status ikke er en af de 3 tilladte.
        """
        return {
            "loennr": self.loennr,
            "navn": self.navn,
            "fratraedelsesdato": self.fratraedelsesdato,
            "status": self.status,
            "kommentar": self.kommentar,
        }

    @classmethod
    def fra_dict(cls, data):
        """Opretter en Medarbejder ud fra et dictionary.

        Dette er et godt sted at øve dig i at læse JSON-data og bygge objekter.
        """
        return cls(
            data["loennr"],
            data["navn"],
            data["fratraedelsesdato"],
            data.get("status", "Afventer Udstyr"),
            data["kommentar"],
        )
