"""HR's behovsregistrering for en ny medarbejder: tøj, mobil, e-mail og firmabil.

Behovet er adskilt fra opgaverne: at HR vælger en telefon betyder ikke, at den
er bestilt eller sendt. Behovet afgør kun, hvilke betingede opgaver der er
relevante (Opgave.betingelse) – se betingelse_opfyldt().

Sortiment, størrelser og hvilke stillinger der kan få hvad, ligger kun her, så
brugerflade, validering og rapporter altid bruger samme lister.

Standardprofiler (Indstillinger → Organisation) er et udgangspunkt pr.
stillingskategori: hvilket udstyr og hvor mange – aldrig størrelser eller
bemærkninger, som afhænger af personen. En profil er adskilt fra
arbejdsgangsskabelonerne (de bestemmer opgaverne, profilen kun forvalget) og
begrænses altid af, hvad stillingen må få. At en profil vælger udstyr, betyder
ikke, at noget er bestilt eller udleveret.
"""
import copy
from dataclasses import dataclass, field

# Arbejdstøj: nøgle -> navn. Udvides her (og med en betinget skabelonopgave).
BEKLAEDNING = {"polo": "Polo", "fleece": "Fleece"}
STOERRELSER = ("XS", "S", "M", "L", "XL", "XXL", "3XL")
MAKS_ANTAL = 5          # flere aftales og skrives i bemærkningen

TALE_OG_DATA = "Tale og data"
KUN_DATA = "Kun data"
ABONNEMENTER = (TALE_OG_DATA, KUN_DATA)

# Mobil med tale og data, firmabil og e-mail kun for disse stillinger.
UDVIDET_UDSTYR = ("FM", "DM", "Afløser")

# Betingelser, som skabelonopgaver kan bruge (Opgave.betingelse).
BETINGELSER = {
    "polo": "Polo valgt",
    "fleece": "Fleece valgt",
    "toej": "Polo eller fleece valgt",
    "udstyr": "Telefon, e-mail, polo eller fleece valgt",
    "mobil": "Mobiltelefon valgt",
    "email": "E-mailkonto valgt",
    "firmabil": "Firmabil valgt",
}


def tilladt_udvidet(stilling: str) -> bool:
    return stilling in UDVIDET_UDSTYR


def tilladte_abonnementer(stilling: str) -> tuple:
    return ABONNEMENTER if tilladt_udvidet(stilling) else (KUN_DATA,)


@dataclass
class Toej:
    valgt: bool = False
    stoerrelse: str = ""
    antal: int = 0

    def til_dict(self) -> dict:
        # Fravalgt tøj gemmer ingen størrelse/antal, så data aldrig bliver ulogiske.
        if not self.valgt:
            return {"valgt": False, "stoerrelse": "", "antal": 0}
        return {"valgt": True, "stoerrelse": self.stoerrelse, "antal": self.antal}

    @classmethod
    def fra_dict(cls, data) -> "Toej":
        data = data if isinstance(data, dict) else {}
        try:
            antal = int(data.get("antal") or 0)
        except (TypeError, ValueError):
            antal = 0
        return cls(bool(data.get("valgt")), str(data.get("stoerrelse") or "").strip(), antal)


@dataclass
class Behov:
    polo: Toej = field(default_factory=Toej)
    fleece: Toej = field(default_factory=Toej)
    toej_bemaerkning: str = ""
    mobil: bool = False
    abonnement: str = ""
    email: bool = False
    firmabil: bool = False
    firmabil_bemaerkning: str = ""
    # Udstyrsposter (nøgler fra udstyrsposter()), som Administration har sendt.
    sendt: list = field(default_factory=list)

    def toej(self, noegle: str) -> Toej:
        return getattr(self, noegle)

    def betingelse_opfyldt(self, betingelse: str) -> bool:
        """Er opgaver med denne betingelse relevante? Tom betingelse = altid."""
        if not betingelse:
            return True
        if betingelse == "toej":
            return any(self.toej(n).valgt for n in BEKLAEDNING)
        if betingelse == "udstyr":
            return bool(self.udstyrsliste())
        if betingelse in BEKLAEDNING:
            return self.toej(betingelse).valgt
        return bool(getattr(self, betingelse, False))

    def valider(self, stilling: str, kraev_stoerrelse: bool = True) -> list[str]:
        """kraev_stoerrelse=False: størrelsen må mangle (kandidatfasen, før
        tøjbehovet er afklaret) – men en angivet størrelse skal være gyldig."""
        fejl = []
        for noegle, navn in BEKLAEDNING.items():
            t = self.toej(noegle)
            if not t.valgt:
                continue
            if t.stoerrelse not in STOERRELSER and (kraev_stoerrelse or t.stoerrelse):
                fejl.append(f"Vælg en størrelse til {navn.lower()}.")
            if not 1 <= t.antal <= MAKS_ANTAL:
                fejl.append(f"Antal {navn.lower()} skal være 1-{MAKS_ANTAL} "
                            "(skriv større behov i bemærkningen).")
        if self.mobil and self.abonnement not in tilladte_abonnementer(stilling):
            fejl.append("Vælg abonnement: " + " eller ".join(tilladte_abonnementer(stilling)) + ".")
        if self.email and not self.mobil:
            # Firma-mailen ligger på telefonen (Gmail på den klargjorte telefon).
            fejl.append("E-mailkonto kræver mobiltelefon.")
        if not tilladt_udvidet(stilling):
            kun = ", ".join(UDVIDET_UDSTYR)
            if self.email:
                fejl.append(f"E-mailkonto kan kun vælges for {kun}.")
            if self.firmabil:
                fejl.append(f"Firmabil kan kun vælges for {kun}.")
        return fejl

    def udstyrsposter(self) -> list[tuple[str, str]]:
        """Det valgte udstyr som (nøgle, tekst) (ikke firmabil – den bestilles for sig),
        fx [("telefon", "Telefon (Tale og data)"), ("polo", "Polo M × 2")]."""
        poster = []
        if self.mobil:
            poster.append(("telefon", f"Telefon ({self.abonnement})" if self.abonnement
                           else "Telefon"))
        if self.email:
            poster.append(("email", "E-mail"))
        for noegle, navn in BEKLAEDNING.items():
            t = self.toej(noegle)
            if t.valgt:
                poster.append((noegle, f"{navn} {t.stoerrelse or '(størrelse mangler)'} "
                                       f"× {t.antal}"))
        return poster

    def udstyrsliste(self) -> list[str]:
        """Det valgte udstyr som tekst, fx ["Telefon (Tale og data)", "E-mail",
        "Polo M × 2"]. Tom = intet udstyr."""
        return [tekst for _, tekst in self.udstyrsposter()]

    def sendte_poster(self) -> list[str]:
        """De sendte poster, som stadig er valgt (et fravalg glemmer forsendelsen)."""
        valgte = {n for n, _ in self.udstyrsposter()}
        return [n for n in self.sendt if n in valgte]

    def linjer(self) -> list[str]:
        """Læsbar oversigt, fx ["Polo: M × 2", "Mobil: Kun data", ...]."""
        linjer = []
        for noegle, navn in BEKLAEDNING.items():
            t = self.toej(noegle)
            linjer.append(f"{navn}: {t.stoerrelse} × {t.antal}" if t.valgt else f"{navn}: nej")
        if self.toej_bemaerkning:
            linjer.append(f"Tøj, bemærkning: {self.toej_bemaerkning}")
        linjer.append(f"Mobil: {self.abonnement}" if self.mobil else "Mobil: nej")
        linjer.append(f"E-mailkonto: {'ja' if self.email else 'nej'}")
        bil = "ja" if self.firmabil else "nej"
        if self.firmabil and self.firmabil_bemaerkning:
            bil += f" ({self.firmabil_bemaerkning})"
        linjer.append(f"Firmabil: {bil}")
        poster = self.udstyrsposter()
        if poster:
            sendt = set(self.sendte_poster())
            linjer.append("Sendt: " + (", ".join(t for n, t in poster if n in sendt) or "intet"))
        return linjer

    def aendringer(self, ny: "Behov") -> list[str]:
        """Hvad er ændret fra self til ny – til tidslinjen."""
        foer, efter = self.linjer(), ny.linjer()
        return [f"{a} → {b.split(': ', 1)[-1]}" for a, b in zip(foer, efter) if a != b] + \
            [b for b in efter[len(foer):]]

    def til_dict(self) -> dict:
        return {
            "polo": self.polo.til_dict(),
            "fleece": self.fleece.til_dict(),
            "toej_bemaerkning": self.toej_bemaerkning,
            "mobil": self.mobil,
            "abonnement": self.abonnement if self.mobil else "",
            "email": self.email,
            "firmabil": self.firmabil,
            "firmabil_bemaerkning": self.firmabil_bemaerkning if self.firmabil else "",
            "sendt": self.sendte_poster(),
        }

    @classmethod
    def fra_dict(cls, data) -> "Behov":
        data = data if isinstance(data, dict) else {}
        return cls(
            Toej.fra_dict(data.get("polo")),
            Toej.fra_dict(data.get("fleece")),
            str(data.get("toej_bemaerkning") or "").strip(),
            bool(data.get("mobil")),
            str(data.get("abonnement") or "").strip(),
            bool(data.get("email")),
            bool(data.get("firmabil")),
            str(data.get("firmabil_bemaerkning") or "").strip(),
            [str(n) for n in data.get("sendt") or [] if n],
        )


### ----- standardprofiler ----------------------------------------------------

def profil(data, stilling: str) -> Behov:
    """En standardprofil som behov til formularen: kun udstyr og antal, ingen
    størrelser eller bemærkninger, og intet stillingen ikke må få."""
    b = Behov.fra_dict(data)
    for noegle in BEKLAEDNING:
        t = b.toej(noegle)
        t.stoerrelse = ""
        if t.valgt and not 1 <= t.antal <= MAKS_ANTAL:
            t.antal = 1
    b.toej_bemaerkning = b.firmabil_bemaerkning = ""
    b.sendt = []
    if b.abonnement not in tilladte_abonnementer(stilling):
        tilladte = tilladte_abonnementer(stilling)
        b.abonnement = tilladte[0] if b.mobil and len(tilladte) == 1 else ""
    if not tilladt_udvidet(stilling):
        b.email = b.firmabil = False
    b.email = b.email and b.mobil
    return b


def valider_profiler(profiler: dict, stillinger) -> list[str]:
    """Fejl i standardprofilerne (pr. stilling) – samme regler som behovet,
    blot uden krav om størrelse."""
    fejl = []
    for stilling, data in (profiler or {}).items():
        if stilling not in stillinger:
            fejl.append(f"Ukendt stilling i udstyrsprofil: {stilling}.")
            continue
        fejl += [f"{stilling}: {f}"
                 for f in Behov.fra_dict(data).valider(stilling, kraev_stoerrelse=False)]
    return fejl


def normaliser_profiler(profiler: dict, stillinger) -> dict:
    """Kendte stillinger i fast rækkefølge; tomme profiler udelades."""
    resultat = {}
    for stilling in stillinger:
        data = (profiler or {}).get(stilling)
        if isinstance(data, dict):
            b = profil(copy.deepcopy(data), stilling)
            if b != Behov():
                resultat[stilling] = b.til_dict()
    return resultat
