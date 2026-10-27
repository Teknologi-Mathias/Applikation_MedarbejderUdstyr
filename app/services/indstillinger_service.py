"""Indstillinger: fælles (alle brugere) og personlige præferencer.

Fælles indstillinger (Data/indstillinger.json): backup, slettepolitik,
områder, ansvarlige afdelinger, grænser for Action Center og standardprofiler
for udstyr pr. stilling (app/domain/behov.py). Alle brugere ændrer
Organisation; backup og slettepolitik (Data & sikkerhed) kun administratorer.

Personlige præferencer (Lokal/praeferencer.json, pr. bruger): tema og
Windows-notifikationer. De gemmes på pc'en, så de også virker offline. Ved
databaseintegration flyttes de til user_profiles.
"""
from app.domain import behov as bh
from app.domain.onboarding import OnboardingForloeb
from app.repositories.base import IndstillingRepository, PraeferenceRepository
from app.repositories.fejl import ValideringsFejl

STANDARD = {
    # Arkiverede sager slettes efter så mange måneder (aftal perioden med HR).
    "opbevaring_maaneder": 12,
    # Antal sikkerhedskopier der gemmes, før de ældste slettes.
    "backup_antal": 30,
    # Tom = Data/Backup. Bør helst være et andet drev, fx et netværksdrev.
    "backup_mappe": "",
    # Organisatoriske områder (onboarding).
    "omraader": ["Område Nord", "Område Syd", "Område Øst", "Område Vest"],
    # Afdelinger, der kan vælges som ansvarlig (ud over brugerne).
    "ansvarlige": ["Administration", "HR", "MERCH"],
    # Action Center: en sag uden aktivitet i så mange dage markeres.
    "stillestaaende_dage": 14,
    # Action Center: fratrædelse/første arbejdsdag inden for så mange dage.
    "naermer_sig_dage": 7,
    # Onboarding: forvalgt udstyr pr. stillingskategori ({stilling: behov uden
    # størrelser}). Tom = intet forvalgt; HR vælger selv i formularen.
    "udstyrsprofiler": {},
}

TEMAER = {"lilla": "Lilla", "lys": "Lyst (Standard)"}
STANDARD_PRAEFERENCER = {"tema": "lilla", "windows_notifikationer": True}


class IndstillingerService:
    def __init__(self, repo: IndstillingRepository, praeferencer: PraeferenceRepository):
        self.repo = repo
        self.praeferencer = praeferencer

    ### ----- fælles ---------------------------------------------------------

    def hent(self) -> dict:
        data = self.repo.hent()
        return {**STANDARD, **{k: v for k, v in data.items() if k in STANDARD}}

    def gem(self, indstillinger: dict) -> None:
        tal = ("opbevaring_maaneder", "backup_antal", "stillestaaende_dage", "naermer_sig_dage")
        for noegle in tal:
            if int(indstillinger.get(noegle, 0)) < 1:
                raise ValideringsFejl(f"{noegle} skal være mindst 1.")
        lister = {
            noegle: list(dict.fromkeys(v.strip() for v in indstillinger.get(noegle, []) if v.strip()))
            for noegle in ("omraader", "ansvarlige")
        }
        profiler = indstillinger.get("udstyrsprofiler") or {}
        fejl = bh.valider_profiler(profiler, OnboardingForloeb.STILLINGER)
        if fejl:
            raise ValideringsFejl(" ".join(fejl))
        lister["udstyrsprofiler"] = bh.normaliser_profiler(profiler, OnboardingForloeb.STILLINGER)
        self.repo.gem({**{k: indstillinger.get(k, STANDARD[k]) for k in STANDARD}, **lister})

    def udstyrsprofiler(self) -> dict:
        """{stilling: Behov} – standardprofilen pr. stilling (tom, hvis ingen er sat op),
        altid begrænset til det, stillingen må få."""
        gemte = self.hent()["udstyrsprofiler"]
        return {s: bh.profil(gemte.get(s), s) for s in OnboardingForloeb.STILLINGER}

    def opdater(self, **aendringer) -> dict:
        indstillinger = {**self.hent(), **aendringer}
        self.gem(indstillinger)
        return indstillinger

    ### ----- personlige -----------------------------------------------------

    def praeference(self, brugernavn: str) -> dict:
        return {**STANDARD_PRAEFERENCER, **self.praeferencer.hent(brugernavn)}

    def gem_praeference(self, brugernavn: str, **aendringer) -> dict:
        if "tema" in aendringer and aendringer["tema"] not in TEMAER:
            raise ValideringsFejl("Ukendt tema.")
        ny = {**self.praeference(brugernavn), **aendringer}
        self.praeferencer.gem(brugernavn, ny)
        return ny
