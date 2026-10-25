"""Ønsker & Udvikling: fejlmeldinger, ønsker og forbedringsforslag.

En indmelding følges fra oprettelse til afslutning gennem en fast
statusmodel. Kategorier, statusser, prioriteter og tilladte statusovergange
er de samme som i databasen (migrering 006) – ændres de her, skal de også
ændres dér.

Rettigheder (håndhæves af databasen; services giver blot pæne beskeder først):
- Alle medlemmer opretter indmeldinger, kommenterer og ser hele køen.
- Indsenderen må rette teksten, mens indmeldingen har status Indsendt.
- Kun administratorer ændrer status, prioritet, ansvarlig, planlagt
  version og løsning – og skriver interne noter.
"""
from dataclasses import dataclass, field, fields

KATEGORIER = (
    "Fejlmelding", "Nyt ønske", "Automatisering", "Data og ERP",
    "Forbedring af arbejdsgang", "Andet",
)

INDSENDT = "Indsendt"
TIL_VURDERING = "Til vurdering"
ACCEPTERET = "Accepteret"
AFVIST = "Afvist"
PLANLAGT = "Planlagt"
UNDER_UDVIKLING = "Under udvikling"
TIL_TEST = "Til test"
UDGIVET = "Udgivet"
STATUSSER = (INDSENDT, TIL_VURDERING, ACCEPTERET, AFVIST, PLANLAGT, UNDER_UDVIKLING,
             TIL_TEST, UDGIVET)
AFSLUTTEDE = (AFVIST, UDGIVET)

# Status -> de statusser, den kan skifte til (svarer til
# inbase_request_transition_allowed() i migrering 006).
OVERGANGE = {
    INDSENDT: (TIL_VURDERING, ACCEPTERET, AFVIST),
    TIL_VURDERING: (INDSENDT, ACCEPTERET, AFVIST),
    ACCEPTERET: (PLANLAGT, UNDER_UDVIKLING, AFVIST),
    PLANLAGT: (ACCEPTERET, UNDER_UDVIKLING, AFVIST),
    UNDER_UDVIKLING: (PLANLAGT, TIL_TEST),
    TIL_TEST: (UNDER_UDVIKLING, UDGIVET),
    UDGIVET: (UNDER_UDVIKLING,),
    AFVIST: (TIL_VURDERING,),
}

LAV, NORMAL, HOEJ, KRITISK = "Lav", "Normal", "Høj", "Kritisk"
PRIORITETER = (LAV, NORMAL, HOEJ, KRITISK)

MAKS_TITEL = 200
MAKS_TEKST = 10_000
MAKS_KOMMENTAR = 5_000
MAKS_VERSION = 40

# Felter, som indsenderen (mens status er Indsendt) og administratorer må rette.
TEKSTFELTER = ("titel", "kategori", "beskrivelse", "problem", "oensket_resultat", "effekt",
               "supplerende")
# Behandling – kun administratorer.
BEHANDLINGSFELTER = ("status", "prioritet", "ansvarlig", "planlagt_version", "loesning")

FELT_NAVNE = {
    "titel": "Titel", "kategori": "Kategori", "beskrivelse": "Beskrivelse",
    "problem": "Problem / nuværende adfærd", "oensket_resultat": "Ønsket resultat",
    "effekt": "Forventet forretningsmæssig effekt", "supplerende": "Supplerende information",
    "status": "Status", "prioritet": "Prioritet", "ansvarlig": "Ansvarlig",
    "planlagt_version": "Planlagt version", "loesning": "Løsning / begrundelse",
}


def tilladte_statusser(fra: str) -> tuple:
    """Den nuværende status efterfulgt af dem, den må skifte til."""
    return (fra,) + OVERGANGE.get(fra, ())


def overgang_tilladt(fra: str, til: str) -> bool:
    return fra == til or til in OVERGANGE.get(fra, ())


@dataclass
class Indmelding:
    titel: str
    kategori: str
    beskrivelse: str = ""
    problem: str = ""
    oensket_resultat: str = ""
    effekt: str = ""
    supplerende: str = ""
    status: str = INDSENDT
    prioritet: str = NORMAL
    indsender: str = ""             # brugernavn – sættes af lagringen ud fra login
    ansvarlig: str = ""             # brugernavn eller ""
    planlagt_version: str = ""
    loesning: str = ""
    id: str = ""
    nummer: int = 0                 # løbenummer (#12) – kun til visning
    oprettet: str = ""
    opdateret: str = ""
    version: int = 0                # optimistisk låsning

    @property
    def afsluttet(self) -> bool:
        return self.status in AFSLUTTEDE

    @property
    def visningsnummer(self) -> str:
        return f"#{self.nummer}" if self.nummer else ""

    def til_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def fra_dict(cls, data: dict) -> "Indmelding":
        navne = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in navne})


@dataclass
class Kommentar:
    indmelding_id: str
    forfatter: str                  # brugernavn
    tekst: str
    intern: bool = False            # administratornote – kun synlig for administratorer
    oprettet: str = ""
    id: str = ""


@dataclass
class Aendring:
    """Én linje i historikken: hvem ændrede hvad, hvornår."""
    tidspunkt: str
    bruger: str
    handling: str                   # OPRETTET eller AENDRET
    felt: str = ""                  # domænets feltnavn, fx "status"
    fra: str = ""
    til: str = ""

    OPRETTET = "oprettet"
    AENDRET = "aendret"

    @property
    def tekst(self) -> str:
        if self.handling == self.OPRETTET:
            return "Indmeldingen er oprettet"
        navn = FELT_NAVNE.get(self.felt, self.felt)
        if self.felt in ("beskrivelse", "problem", "oensket_resultat", "effekt", "supplerende",
                         "loesning"):
            return f"{navn} ændret"
        return f"{navn}: {self.fra or '–'} → {self.til or '–'}"


@dataclass
class Detaljer:
    """En indmelding med de kommentarer og den historik, brugeren må se."""
    indmelding: Indmelding
    kommentarer: list = field(default_factory=list)
    historik: list = field(default_factory=list)
