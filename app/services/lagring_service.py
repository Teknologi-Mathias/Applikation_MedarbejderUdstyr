"""Online/offline-drift og synkronisering af ændringer foretaget offline.

LagringService gælder kun JSON-tilstanden (INBASE_BACKEND=json), hvor
"central" er den fælles datamappe. I Supabase-tilstand bruges OnlineLagring
nederst i filen: ingen offline-drift, da en lokal kopi ikke kan holdes i
trit med databasens versionskontrol.

Arbejd offline:
  1. De centrale datafiler kopieres til Lokal/Offline.
  2. Datakilde skifter til kopien; alle sagsændringer logges i ændringsloggen.
  3. Brugere, skabeloner og fælles indstillinger er skrivebeskyttede offline.

Gå online (synkronisering):
  - Hver ændring anvendes på den centrale mappe, men kun hvis den centrale
    udgave af sagen stadig har den version, ændringen blev lavet ud fra.
  - Ellers er det en konflikt: intet overskrives. Ændringen gemmes i
    konfliktlisten, hvor brugeren vælger "behold central" eller "brug min".

Der skiftes aldrig automatisk mellem datakilderne – kun når brugeren vælger det.
"""
import logging
import shutil
from dataclasses import dataclass, field

from app.domain.historik import nu
from app.infrastructure import stier
from app.repositories.fejl import KonfliktFejl, OfflineFejl
from app.repositories.json.datakilde import KONFLIKTER, OFFLINE_INFO, Datakilde
from app.repositories.json.json_fil import gem_json, hent_json, tjek_skriveadgang
from app.repositories.json.opsaetning_repository import JsonLokalFil
from app.repositories.json.sag_repository import JsonSagRepository

log = logging.getLogger(__name__)


@dataclass
class SyncResultat:
    anvendt: int = 0
    konflikter: list = field(default_factory=list)


class LagringService:
    """JSON-tilstanden: central datamappe med mulighed for offline-kopi."""

    understoetter_offline = True

    def __init__(self, datakilde: Datakilde, konfig: JsonLokalFil, sagstyper: dict):
        """sagstyper: {proces: (sagstype, aktiv_filnavn, arkiv_filnavn)}."""
        self.datakilde = datakilde
        self.konfig = konfig
        self.sagstyper = sagstyper
        self.kilde = f"central datamappe ({datakilde.central_mappe})"

    ### ----- status ---------------------------------------------------------

    @property
    def offline(self) -> bool:
        return self.datakilde.offline

    def central_tilgaengelig(self) -> bool:
        try:
            tjek_skriveadgang(self.datakilde.central_mappe)
            return True
        except OSError:
            return False

    def offline_kopi_findes(self) -> bool:
        return (self.datakilde.offline_mappe / stier.OFFBOARDING_AKTIVE).exists() or \
            (self.datakilde.offline_mappe / stier.ONBOARDING_AKTIVE).exists()

    def ventende_aendringer(self) -> list[dict]:
        return self.datakilde.aendringslog.alle()

    def konflikter(self) -> list[dict]:
        return hent_json(self.datakilde.offline_mappe / KONFLIKTER)

    def offline_info(self) -> dict:
        return hent_json(self.datakilde.offline_mappe / OFFLINE_INFO, forventet=dict)

    ### ----- skift --------------------------------------------------------

    def gaa_offline(self) -> str:
        """Skifter til offline. Returnerer en besked om, hvor data kommer fra."""
        if self.offline:
            return "Programmet arbejder allerede offline."
        mappe = self.datakilde.offline_mappe
        mappe.mkdir(parents=True, exist_ok=True)
        if self.central_tilgaengelig():
            for filnavn in stier.DATAFILER:
                kilde = self.datakilde.central_mappe / filnavn
                if kilde.exists():
                    shutil.copy2(kilde, mappe / filnavn)
            gem_json({"kopieret": nu(), "fra": str(self.datakilde.central_mappe)},
                     mappe / OFFLINE_INFO)
            besked = "De centrale data er kopieret til denne pc."
        elif self.offline_kopi_findes():
            info = self.offline_info()
            besked = (f"Den centrale datamappe kan ikke nås. Der arbejdes videre på den "
                      f"lokale kopi fra {info.get('kopieret', 'ukendt tidspunkt')}.")
        else:
            raise OfflineFejl(
                "Den centrale datamappe kan ikke nås, og der findes ingen lokal kopi."
            )
        self.datakilde.aendringslog.ryd()
        self.datakilde.offline = True
        self.konfig.gem({**self.konfig.hent(), "offline": True})
        log.warning("Skiftet til offline-tilstand: %s", besked)
        return besked

    def gaa_online(self) -> SyncResultat:
        """Synkroniserer ventende ændringer og skifter til den centrale datakilde."""
        if not self.offline:
            return SyncResultat()
        if not self.central_tilgaengelig():
            raise OfflineFejl(
                f"Der er ikke forbindelse til den centrale datamappe "
                f"({self.datakilde.central_mappe}). Du arbejder fortsat offline."
            )
        resultat = self.synkroniser()
        self.datakilde.offline = False
        self.konfig.gem({**self.konfig.hent(), "offline": False})
        log.info("Online igen: %d ændringer synkroniseret, %d konflikter",
                 resultat.anvendt, len(resultat.konflikter))
        return resultat

    ### ----- synkronisering -------------------------------------------------

    def _centrale_repos(self) -> dict:
        central = Datakilde(self.datakilde.central_mappe, self.datakilde.offline_mappe)
        return {proces: JsonSagRepository(central, sagstype, aktiv, arkiv)
                for proces, (sagstype, aktiv, arkiv) in self.sagstyper.items()}

    def synkroniser(self) -> SyncResultat:
        repos = self._centrale_repos()
        resultat = SyncResultat()
        konflikt_sager = set()
        for post in self.ventende_aendringer():
            noegle = (post["proces"], post["sag_id"])
            repo = repos[post["proces"]]
            if noegle in konflikt_sager:
                resultat.konflikter.append(self._konflikt(post, repo, "Tidligere ændring i samme sag var i konflikt"))
                continue
            try:
                self._anvend(repo, post)
                resultat.anvendt += 1
            except KonfliktFejl as fejl:
                konflikt_sager.add(noegle)
                resultat.konflikter.append(self._konflikt(post, repo, str(fejl)))
        if resultat.konflikter:
            gem_json(self.konflikter() + resultat.konflikter,
                     self.datakilde.offline_mappe / KONFLIKTER)
        self.datakilde.aendringslog.ryd()
        return resultat

    @staticmethod
    def _konflikt(post: dict, repo: JsonSagRepository, aarsag: str) -> dict:
        central = repo.hent(post["sag_id"])
        return {**post, "aarsag": aarsag, "central": central.til_dict() if central else None}

    @staticmethod
    def _anvend(repo: JsonSagRepository, post: dict) -> None:
        op, basis = post["op"], int(post["basis_version"])
        if op == "slet":
            sag = repo.hent(post["sag_id"])
            if sag is None:
                return
            if sag.version != basis:
                raise KonfliktFejl("Sagen er ændret centralt, efter den blev slettet offline.")
            repo.slet(sag)
            return
        sag = repo.sagstype.fra_dict(post["data"])
        sag.version = basis
        {"gem": repo.gem, "arkiver": repo.arkiver, "aktiver": repo.aktiver}[op](sag)

    def loes_konflikt(self, index: int, brug_min: bool) -> None:
        """Brug min = overskriv den centrale udgave med den offline ændring."""
        if self.offline:
            raise OfflineFejl("Konflikter kan kun løses online.")
        konflikter = self.konflikter()
        post = konflikter.pop(index)
        if brug_min and post.get("data"):
            repo = self._centrale_repos()[post["proces"]]
            central = repo.hent(post["sag_id"])
            sag = repo.sagstype.fra_dict(post["data"])
            sag.version = central.version if central else 0
            sag.historik.tilfoej("Konflikt løst: offline-ændring brugt",
                                 post.get("aarsag", ""))
            repo.gem(sag)
            log.warning("Konflikt løst med offline-version for sag %s", post["sag_id"])
        gem_json(konflikter, self.datakilde.offline_mappe / KONFLIKTER)


class OnlineLagring:
    """Supabase-tilstand: databasen er den eneste datakilde – der er ingen offline.

    At arbejde på en lokal kopi uden versionskontrol mod databasen ville give
    forældede data og tabte ændringer. Mister programmet forbindelsen, får
    brugeren en tydelig fejl (OfflineFejl) og kan prøve igen.
    Samme metoder som LagringService, så UI'en ikke skal kende forskel.
    """

    understoetter_offline = False
    offline = False

    def __init__(self, kilde: str):
        self.kilde = kilde          # vises i UI'en, fx "Supabase (abc.supabase.co)"

    def central_tilgaengelig(self) -> bool:
        return True

    def offline_kopi_findes(self) -> bool:
        return False

    def ventende_aendringer(self) -> list[dict]:
        return []

    def konflikter(self) -> list[dict]:
        return []

    def offline_info(self) -> dict:
        return {}

    def gaa_offline(self) -> str:
        raise OfflineFejl(
            "IN-BASE arbejder direkte i den fælles database og kan ikke arbejde offline. "
            "Mister du forbindelsen, så vent og prøv igen – intet gemmes lokalt."
        )

    def gaa_online(self) -> SyncResultat:
        return SyncResultat()

    def loes_konflikt(self, index: int, brug_min: bool) -> None:
        raise OfflineFejl("Der er ingen offline-konflikter i databasetilstand.")
