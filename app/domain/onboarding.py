"""Onboarding: forløbet fra kandidat til aktiv medarbejder.

IN-BASE registrerer og følger forløbet – selve oplæringen foregår i butikken
og i medarbejderappen.

Status beregnes ud fra milepælene: den første milepæl, der ikke er færdig,
bestemmer status. Er alle færdige, er medarbejderen Aktiv. "Annulleret" kan
kun sættes manuelt med begrundelse (og lukker forløbet).

    Milepæl     Ikke færdig ->  Status
    kandidat                    Kandidat
    kontrakt                    Afventer kontrakt
    oplaering                   Afventer første oplæring
    jobs                        Afventer jobs
    (alle færdige)              Aktiv
"""
from app.domain.opgave import laes_iso_dato
from app.domain.sag import Sag


class OnboardingForloeb(Sag):
    PROCES = "onboarding"

    STATUS_KANDIDAT = "Kandidat"
    STATUS_KONTRAKT = "Afventer kontrakt"
    STATUS_OPLAERING = "Afventer første oplæring"
    STATUS_JOBS = "Afventer jobs"
    STATUS_AKTIV = "Aktiv"
    STATUS_ANNULLERET = "Annulleret"
    STATUSER = (
        STATUS_KANDIDAT, STATUS_KONTRAKT, STATUS_OPLAERING,
        STATUS_JOBS, STATUS_AKTIV, STATUS_ANNULLERET,
    )
    # Statusser i den rækkefølge forløbet skrider frem (uden Annulleret).
    FREMDRIFT = STATUSER[:-1]

    MILEPAELE = (
        ("kandidat", "Kandidat godkendt"),
        ("kontrakt", "Kontrakt bekræftet"),
        ("oplaering", "Første oplæring"),
        ("jobs", "Klar til jobs"),
    )
    _STATUS_FOR_MILEPAEL = {
        "kandidat": STATUS_KANDIDAT,
        "kontrakt": STATUS_KONTRAKT,
        "oplaering": STATUS_OPLAERING,
        "jobs": STATUS_JOBS,
    }

    STILLINGER = ("Ad Hoc", "FM", "DM", "Afløser")

    def __init__(
        self,
        navn,
        *,
        stilling="",
        omraade="",
        ansaettelsesdato="",
        foerste_arbejdsdag="",
        email="",
        **basis,
    ):
        super().__init__(navn=navn, **basis)
        self.stilling = stilling if stilling in self.STILLINGER else (stilling or "")
        self.omraade = str(omraade or "").strip()
        self.ansaettelsesdato = ansaettelsesdato or ""
        # Kun relevant, hvis den afviger fra ansættelsesdatoen.
        self.foerste_arbejdsdag = foerste_arbejdsdag or ""
        self.email = str(email or "").strip()

    ### ----- status ---------------------------------------------------------

    def beregnet_status(self) -> str:
        aktiv = self.aktiv_milepael()
        return self._STATUS_FOR_MILEPAEL[aktiv] if aktiv else self.STATUS_AKTIV

    def er_afsluttet(self) -> bool:
        return self.status in (self.STATUS_AKTIV, self.STATUS_ANNULLERET)

    def kraever_overstyring(self, ny_status: str) -> bool:
        """True, hvis ny_status springer over krav, der endnu ikke er opfyldt.

        En sådan statusændring er en kritisk overstyring og kræver begrundelse.
        """
        if ny_status == self.STATUS_ANNULLERET or ny_status not in self.FREMDRIFT:
            return False
        return self.FREMDRIFT.index(ny_status) > self.FREMDRIFT.index(self.beregnet_status())

    def mangler_for(self, ny_status: str) -> list:
        """Navne på obligatoriske opgaver, der mangler, før ny_status er opfyldt."""
        if ny_status not in self.FREMDRIFT:
            return []
        maal = self.FREMDRIFT.index(ny_status)
        noegler = [n for n, _ in self.MILEPAELE][:maal]
        return [
            o.navn for o in self.opgaver
            if o.milepael in noegler and o.obligatorisk and not o.afsluttet
        ]

    ### ----- datoer og visning ----------------------------------------------

    def startdato(self) -> str:
        return self.ansaettelsesdato

    def foerste_dag(self) -> str:
        return self.foerste_arbejdsdag or self.ansaettelsesdato

    def beskrivelse(self) -> str:
        dato = laes_iso_dato(self.foerste_dag())
        vis = dato.strftime("%d-%m-%Y") if dato else "ikke fastlagt"
        dele = [
            f"Lønnr. {self.loennr or 'ikke tildelt'}",
            self.stilling or "Stilling ikke valgt",
            self.omraade or "Område ikke valgt",
            f"Første arbejdsdag {vis}",
        ]
        return " · ".join(dele)

    ### ----- JSON -----------------------------------------------------------

    def til_dict(self) -> dict:
        return {
            **self._basis_dict(),
            "stilling": self.stilling,
            "omraade": self.omraade,
            "ansaettelsesdato": self.ansaettelsesdato,
            "foerste_arbejdsdag": self.foerste_arbejdsdag,
            "email": self.email,
        }

    @classmethod
    def fra_dict(cls, data: dict) -> "OnboardingForloeb":
        basis = cls._basis_kwargs(data)
        navn = basis.pop("navn")
        return cls(
            navn,
            stilling=data.get("stilling", ""),
            omraade=data.get("omraade", ""),
            ansaettelsesdato=data.get("ansaettelsesdato", ""),
            foerste_arbejdsdag=data.get("foerste_arbejdsdag", ""),
            email=data.get("email", ""),
            **basis,
        )
