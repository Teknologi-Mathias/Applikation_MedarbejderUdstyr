"""Skabeloner: arbejdsgange (sager), mails (rykkere) og påmindelser.

Rene regler uden filadgang – indlæsning og lagring ligger i
app/repositories/json/skabelon_repository.py, versionering i
app/services/skabelon_service.py og oprettelse af opgaver i
app/services/workflow.py.

Format (Data/skabeloner.json):

    {
        "sager":        [{"id", "navn", "aktiv", "proces", "stillinger",
                          "beskrivelse", "version", "versioner", "opgaver": [...]}],
        "mails":        [{"id", "navn", "aktiv", "kategori", "tone",
                          "frist_dage", "emne", "broedtekst"}],
        "paamindelser": [{"id", "navn", "aktiv", "regel", "dage",
                          "gentag_dage", "titel", "tekst"}]
    }

En opgave i en arbejdsgangsskabelon: {"navn", "beskrivelse", "ansvarlig",
"udstyr", "milepael", "frist_dage", "obligatorisk"}. frist_dage regnes fra
sagens startdato (offboarding: sidste arbejdsdag, onboarding: ansættelsesdato).
Milepælen styrer, hvornår opgaven aktiveres (efter de tidligere milepæle).

Tekster kan indeholde variabler som {navn} og {frist}. De flettes med flet(),
som afviser beskeden, hvis en variabel er ukendt eller mangler en værdi.
"""
import copy
import re
import uuid
from datetime import date, timedelta

from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave, laes_iso_dato, udled_udstyr

SAG = "sager"
MAIL = "mails"
PAAMINDELSE = "paamindelser"
SLAGS = (SAG, MAIL, PAAMINDELSE)

MAIL_KATEGORIER = ("Første påmindelse", "Anden rykker", "Sidste rykker", "Andet")
TONER = ("Venlig", "Neutral", "Bestemt")

# Variabler i mails: navn -> forklaring (vises i editoren).
MAIL_VARIABLER = {
    "navn": "Medarbejderens fulde navn",
    "fornavn": "Medarbejderens fornavn",
    "loennr": "Lønnummer",
    "email": "Medarbejderens e-mailadresse",
    "sidste_arbejdsdag": "Sidste arbejdsdag",
    "manglende_udstyr": "Liste over udstyr, der ikke er afleveret",
    "frist": "Frist for returnering (vælges ved rykkeren)",
    "tracking_link": "Link til sporing af returforsendelsen",
}

# Variabler i påmindelser (Windows-notifikationer).
PAAMINDELSE_VARIABLER = {
    "navn": "Medarbejderens navn",
    "opgave": "Opgavens navn",
    "ansvarlig": "Ansvarlig for opgaven",
    "frist": "Opgavens frist",
    "dage": "Antal dage (over frist / siden rykker / til fratrædelse)",
    "manglende_udstyr": "Udstyr, der ikke er afleveret",
}

PROCESSER = {
    Medarbejder.PROCES: "Offboarding",
    OnboardingForloeb.PROCES: "Onboarding",
}

# Foruddefinerede regler for påmindelser: nøgle -> (beskrivelse, bruger "dage").
REGLER = {
    "opgave_forsinket": ("En opgave er over sin frist", False),
    "frist_i_dag": ("En opgave har frist i dag", False),
    "fratraedelse_naermer_sig": ("Sidste arbejdsdag er om X dage", True),
    "rykker_ikke_sendt": ("En rykker-kladde er ikke markeret som sendt efter X dage", True),
    "intet_svar_efter_rykker": ("Udstyr mangler stadig X dage efter sendt rykker", True),
    "sag_stillestaaende": ("En sag har ikke bevæget sig i X dage", True),
}

_ONBOARDING_BASIS = [
    {"navn": "Kandidat godkendt", "ansvarlig": "HR", "milepael": "kandidat",
     "frist_dage": -14, "obligatorisk": True},
    {"navn": "Kontrakt sendt", "ansvarlig": "HR", "milepael": "kontrakt",
     "frist_dage": -10, "obligatorisk": True},
    {"navn": "Kontrakt underskrevet og bekræftet", "ansvarlig": "HR",
     "milepael": "kontrakt", "frist_dage": -3, "obligatorisk": True},
    {"navn": "Lønnr. tildelt", "ansvarlig": "Løn", "milepael": "kontrakt",
     "frist_dage": -1, "obligatorisk": True},
    {"navn": "Første oplæring planlagt", "ansvarlig": "Butik", "milepael": "oplaering",
     "frist_dage": 0, "obligatorisk": True},
    {"navn": "Første oplæring gennemført", "ansvarlig": "Butik", "milepael": "oplaering",
     "frist_dage": 7, "obligatorisk": True},
    {"navn": "Oprettet i medarbejderappen", "ansvarlig": "Butik", "milepael": "jobs",
     "frist_dage": 7, "obligatorisk": True},
    {"navn": "Første job tildelt", "ansvarlig": "Butik", "milepael": "jobs",
     "frist_dage": 14, "obligatorisk": True},
]

_STANDARD = {
    SAG: [
        {
            "navn": "Standard",
            "proces": "offboarding",
            "opgaver": [
                {"navn": "Er lukket i NAV?", "ansvarlig": "IT", "udstyr": "",
                 "frist_dage": 0, "obligatorisk": True},
                {"navn": "Modtag og spær tankkort", "ansvarlig": "Administration",
                 "udstyr": "Tankkort", "frist_dage": 0, "obligatorisk": True},
                {"navn": "Modtag telefon og SIM-kort", "ansvarlig": "IT",
                 "udstyr": "Telefon og SIM-kort", "frist_dage": 7, "obligatorisk": True},
                {"navn": "Modtag tøj", "ansvarlig": "Administration", "udstyr": "Tøj",
                 "frist_dage": 14, "obligatorisk": True},
                {"navn": "Afslut og dokumentér afviklingen", "ansvarlig": "Ansvarlig leder",
                 "udstyr": "", "frist_dage": 21, "obligatorisk": True},
            ],
        },
        {"navn": "Tom sag (tilføj opgaver selv)", "proces": "offboarding", "opgaver": []},
        {
            "navn": "Onboarding – standard",
            "proces": "onboarding",
            "beskrivelse": "Ad Hoc og Afløsere",
            "stillinger": ["Ad Hoc", "Afløser"],
            "opgaver": _ONBOARDING_BASIS,
        },
        {
            "navn": "Onboarding – FM/DM",
            "proces": "onboarding",
            "beskrivelse": "Ledere: ekstra introduktion",
            "stillinger": ["FM", "DM"],
            "opgaver": _ONBOARDING_BASIS + [
                {"navn": "Introduktion til ledelsesopgaver", "ansvarlig": "Områdeleder",
                 "milepael": "oplaering", "frist_dage": 14, "obligatorisk": True},
            ],
        },
    ],
    MAIL: [
        {
            "navn": "Første venlige påmindelse",
            "kategori": "Første påmindelse",
            "tone": "Venlig",
            "frist_dage": 7,
            "emne": "Returnering af udstyr",
            "broedtekst": (
                "Hej {fornavn}\n\n"
                "Vi mangler fortsat at modtage følgende udstyr:\n"
                "{manglende_udstyr}\n\n"
                "Vi beder dig venligst sørge for, at det resterende udstyr "
                "returneres senest {frist}. Returvejledningen fremgår af den "
                "tidligere fremsendte e-mail.\n\n"
                "På forhånd tak for din hjælp."
            ),
        },
        {
            "navn": "Anden rykker med tydelig frist",
            "kategori": "Anden rykker",
            "tone": "Bestemt",
            "frist_dage": 5,
            "emne": "Rykker: Udstyr skal returneres senest {frist}",
            "broedtekst": (
                "Hej {fornavn}\n\n"
                "Vi har tidligere skrevet til dig om returnering af udstyr, men "
                "har endnu ikke modtaget:\n"
                "{manglende_udstyr}\n\n"
                "Udstyret skal være returneret senest {frist}. Returvejledningen "
                "fremgår af den tidligere fremsendte e-mail.\n\n"
                "Har du spørgsmål, er du velkommen til at svare på denne mail."
            ),
        },
    ],
    PAAMINDELSE: [
        {"navn": "Forsinket opgave", "regel": "opgave_forsinket", "dage": 0,
         "titel": "Forsinket: {opgave}",
         "tekst": "{navn} · Ansvarlig: {ansvarlig} · {dage} dage over frist"},
        {"navn": "Frist i dag", "regel": "frist_i_dag", "dage": 0,
         "titel": "Frist i dag: {opgave}",
         "tekst": "{navn} · Ansvarlig: {ansvarlig}"},
        {"navn": "Rykker venter på afsendelse", "regel": "rykker_ikke_sendt", "dage": 2,
         "titel": "Rykker ikke markeret som sendt",
         "tekst": "Rykkeren til {navn} blev oprettet for {dage} dage siden."},
        {"navn": "Intet svar efter rykker", "regel": "intet_svar_efter_rykker", "dage": 7,
         "titel": "Overvej næste rykker: {navn}",
         "tekst": "Mangler stadig: {manglende_udstyr}"},
        {"navn": "Fratrædelse nærmer sig", "regel": "fratraedelse_naermer_sig", "dage": 3,
         "titel": "{navn} stopper om {dage} dage",
         "tekst": "Sørg for, at opgaverne er fordelt inden sidste arbejdsdag."},
        {"navn": "Stillestående sag", "regel": "sag_stillestaaende", "dage": 14,
         "gentag_dage": 7,
         "titel": "Ingen bevægelse: {navn}",
         "tekst": "Sagen har ikke ændret sig i {dage} dage."},
    ],
}


### ----- normalisering ------------------------------------------------------

def ny_id():
    return uuid.uuid4().hex[:12]


def klargoer(skabelon, slags):
    """Udfylder manglende felter, så resten af programmet kan stole på dem."""
    s = copy.deepcopy(skabelon)
    s.setdefault("id", ny_id())
    s.setdefault("navn", "Uden navn")
    s["aktiv"] = bool(s.get("aktiv", True))
    if slags == SAG:
        s.setdefault("proces", Medarbejder.PROCES)
        s.setdefault("beskrivelse", "")
        s.setdefault("stillinger", [])
        s.setdefault("version", 1)
        s.setdefault("versioner", [])
        opgaver = []
        for post in s.get("opgaver") or []:
            if isinstance(post, dict) and post.get("navn"):
                post = dict(post)
                post.setdefault("udstyr", udled_udstyr(post["navn"]))
                post.setdefault("beskrivelse", "")
                post.setdefault("milepael", "")
                post.setdefault("frist_dage", 0)
                post.setdefault("obligatorisk", True)
                opgaver.append(post)
        s["opgaver"] = opgaver
    elif slags == MAIL:
        s.setdefault("kategori", MAIL_KATEGORIER[0])
        s.setdefault("tone", TONER[0])
        s.setdefault("frist_dage", 7)
        s.setdefault("emne", "")
        s.setdefault("broedtekst", "")
    else:
        s.setdefault("regel", next(iter(REGLER)))
        s.setdefault("dage", 0)
        # Hvor ofte samme påmindelse må gentages (dage). 0 = kun én gang.
        s.setdefault("gentag_dage", 1)
        s.setdefault("titel", "")
        s.setdefault("tekst", "")
    return s


def normaliser_alle(data):
    """Rå fildata -> {slags: [skabelon, ...]}.

    Mangler en slags (fx ældre filer), bruges standardskabelonerne. Har filen
    ingen onboarding-skabeloner, tilføjes standarderne til onboarding.
    Kaster ValueError ved et ugyldigt format.
    """
    if isinstance(data, list):          # format fra V0.5.4: kun sagsskabeloner
        data = {SAG: data}
    data = data or {}
    alle = {}
    for slags in SLAGS:
        liste = data.get(slags)
        if liste is None:
            liste = _STANDARD[slags]
        if not isinstance(liste, list) or not all(isinstance(s, dict) for s in liste):
            raise ValueError(f'ugyldig liste "{slags}"')
        alle[slags] = [klargoer(s, slags) for s in liste]
    if not any(s["proces"] == OnboardingForloeb.PROCES for s in alle[SAG]):
        alle[SAG] += [
            klargoer(s, SAG) for s in _STANDARD[SAG] if s.get("proces") == OnboardingForloeb.PROCES
        ]
    return alle


def aktive(alle, slags, proces=None):
    return [
        s for s in alle[slags]
        if s["aktiv"] and (proces is None or s.get("proces") == proces)
    ]


def til_stilling(skabeloner, stilling):
    """Skabeloner der passer til stillingen (tom "stillinger" = alle)."""
    return [s for s in skabeloner if not s.get("stillinger") or stilling in s["stillinger"]]


def kopier(skabelon):
    kopi = copy.deepcopy(skabelon)
    kopi.update(id=ny_id(), navn=f"Kopi af {skabelon['navn']}", version=1, versioner=[])
    return kopi


def ny_skabelon(slags, proces=None):
    data = {"navn": "Ny skabelon"}
    if slags == SAG and proces:
        data["proces"] = proces
    return klargoer(data, slags)


### ----- fletning og validering ---------------------------------------------

_VARIABEL = re.compile(r"\{([a-z_]+)\}")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def gyldig_email(tekst):
    return bool(_EMAIL.match(tekst or ""))


def brugte_variabler(*tekster):
    return {navn for tekst in tekster for navn in _VARIABEL.findall(tekst or "")}


def flet(tekst, vaerdier, kendte):
    """Indsætter variabler. Returnerer (resultat, fejl).

    Fejl er en liste af beskeder – fx ukendte variabler, eller variabler uden
    værdi (manglende e-mail, frist osv.). Ved fejl må beskeden ikke bruges.
    """
    fejl = []
    for navn in _VARIABEL.findall(tekst or ""):
        if navn not in kendte:
            fejl.append(f"Ukendt variabel {{{navn}}}.")
        elif not str(vaerdier.get(navn) or "").strip():
            fejl.append(f"Mangler værdi for {{{navn}}} ({kendte[navn].lower()}).")

    def erstat(match):
        return str(vaerdier.get(match.group(1)) or match.group(0))

    return _VARIABEL.sub(erstat, tekst or ""), list(dict.fromkeys(fejl))


def dansk_kort_dato(iso):
    dato = laes_iso_dato(iso)
    return dato.strftime("%d-%m-%Y") if dato else ""


def mail_vaerdier(medarbejder, frist_iso):
    manglende = medarbejder.manglende_udstyr()
    return {
        "navn": medarbejder.navn,
        "fornavn": (medarbejder.navn or "").split(" ")[0],
        "loennr": medarbejder.loennr,
        "email": medarbejder.email,
        "sidste_arbejdsdag": dansk_kort_dato(medarbejder.fratraedelsesdato),
        "manglende_udstyr": "\n".join(f"- {u}" for u in manglende),
        "frist": dansk_kort_dato(frist_iso),
        "tracking_link": medarbejder.tracking_link,
    }


def byg_mail(skabelon, medarbejder, frist_iso):
    """Fletter en mailskabelon. Returnerer (emne, brødtekst, fejl)."""
    vaerdier = mail_vaerdier(medarbejder, frist_iso)
    emne, fejl_emne = flet(skabelon.get("emne", ""), vaerdier, MAIL_VARIABLER)
    broedtekst, fejl_tekst = flet(skabelon.get("broedtekst", ""), vaerdier, MAIL_VARIABLER)

    fejl = []
    if not medarbejder.email:
        fejl.append("Medarbejderen har ingen e-mailadresse (tilføj den under Rediger).")
    elif not gyldig_email(medarbejder.email):
        fejl.append(f"E-mailadressen \"{medarbejder.email}\" ser ikke gyldig ud.")
    if not frist_iso:
        fejl.append("Der er ikke valgt en frist.")
    if not medarbejder.manglende_udstyr():
        fejl.append("Der er intet manglende udstyr – en rykker er ikke nødvendig.")
    if not emne.strip():
        fejl.append("Skabelonen har intet emne.")
    fejl += fejl_emne + fejl_tekst
    return emne, broedtekst, list(dict.fromkeys(fejl))


def relevant_mailskabelon(alle, medarbejder):
    """Vælger skabelon ud fra antal tidligere rykkere.

    0 sendte -> "Første påmindelse", 1 -> "Anden rykker", 2+ -> "Sidste rykker".
    Kun sendte rykkere tæller – en kladde, der aldrig blev sendt, eskalerer ikke.
    Findes kategorien ikke, bruges den nærmeste mildere kategori.
    """
    mails = aktive(alle, MAIL)
    if not mails:
        return None
    rykker_kategorier = MAIL_KATEGORIER[:-1]          # uden "Andet"
    sendte = sum(1 for r in medarbejder.rykkere if r.sendt)
    nummer = min(sendte, len(rykker_kategorier) - 1)
    for kategori in reversed(rykker_kategorier[:nummer + 1]):
        for skabelon in mails:
            if skabelon["kategori"] == kategori:
                return skabelon
    return mails[0]


def eksempel_medarbejder():
    """Fiktiv medarbejder til forhåndsvisning, når der ikke vælges en rigtig."""
    i_dag = date.today()
    m = Medarbejder(
        "10482", "Mette Jensen", (i_dag - timedelta(days=10)).isoformat(),
        email="mette.jensen@example.com",
        tracking_link="https://track.example.com/AB123456789DK",
    )
    m.opgaver = [
        Opgave("Modtag telefon og SIM-kort", "IT", i_dag.isoformat(), udstyr="Telefon og SIM-kort"),
        Opgave("Modtag tøj", "Administration", i_dag.isoformat(), udstyr="Tøj"),
    ]
    return m
