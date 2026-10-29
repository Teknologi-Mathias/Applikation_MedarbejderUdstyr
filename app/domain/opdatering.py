"""Central opdatering: hvilken version skal klienten have? (ren logik, ingen I/O)

Udgivelserne kommer fra app_releases (migrering 019) og udgives med
tools/udgiv_version.py. Reglerne:

- Kun udgivelser, der ikke er trukket tilbage, og hvis skemakrav databasen
  opfylder, kan installeres.
- Pilotudgivelser gælder kun brugere med opdateringskanal pilot. Stabile
  udgivelser rulles gradvist ud: brugerens andel (0-99) beregnes ud fra bruger-id
  og version, så samme bruger altid får samme svar.
- Normalt vælges den nyeste gyldige version, der er NYERE end den aktuelle.
- Er den aktuelle version trukket tilbage, vælges den nyeste gyldige – også hvis
  den er ældre (rollback). Kun i det tilfælde må der gås tilbage, så der aldrig
  opstår en løkke.
- Under mindste tilladte version (min_klient_version) eller på en tilbagetrukket
  version skal klienten opdateres, før den må arbejde videre.
"""
import hashlib
from dataclasses import dataclass
from typing import Iterable, Optional

from app import version_tupel

STABIL, PILOT = "stabil", "pilot"
KANALER = (STABIL, PILOT)


@dataclass(frozen=True)
class Udgivelse:
    version: str
    kanal: str
    sti: str                    # stien i Storage-bucketten "releases"
    sha256: str
    stoerrelse: int
    min_skema: int = 0
    tvungen: bool = False
    noter: str = ""
    udrulning: int = 100        # procent af stabil-brugerne
    trukket_tilbage: bool = False
    commit: str = ""
    oprettet: str = ""
    oprettet_af: str = ""

    @property
    def tupel(self) -> tuple[int, int, int]:
        return version_tupel(self.version)


@dataclass(frozen=True)
class Krav:
    """Databasens krav til klienten (RPC inbase_client_requirements)."""
    skema: int
    min_klient: str = "0.0.0"

    @classmethod
    def fra_dict(cls, data: dict) -> "Krav":
        return cls(int(data.get("schema_version") or 0),
                   str(data.get("min_client_version") or "0.0.0"))


def skema_fejl(krav: Krav, kraevet_skema: int) -> Optional[str]:
    """Forklaring, hvis databasen er for gammel til denne klient – ellers None."""
    if krav.skema >= kraevet_skema:
        return None
    return (f"Databasen har skemaversion {krav.skema}, men denne version af IN-BASE kræver "
            f"version {kraevet_skema}.\n\nEn administrator skal køre de manglende migreringer "
            "(docs/SUPABASE_OPSAETNING.md), før programmet kan bruges. Intet er gemt.")


def under_minimum(aktuel: str, krav: Krav) -> bool:
    return version_tupel(aktuel) < version_tupel(krav.min_klient)


def i_udrulning(bruger_id: str, version: str, procent: int) -> bool:
    """Er brugeren med i udrulningen af versionen? Samme svar hver gang."""
    if procent >= 100:
        return True
    if procent <= 0:
        return False
    andel = int(hashlib.sha256(f"{bruger_id}:{version}".encode("utf-8")).hexdigest()[:8], 16) % 100
    return andel < procent


def _synlig(udgivelse: Udgivelse, kanal: str) -> bool:
    # Administratorer ser alle rækker (RLS) – kanalen afgør, hvad de selv får.
    return udgivelse.kanal == STABIL or kanal == PILOT


def _gyldig(udgivelse: Udgivelse, bruger_id: str, skema: int) -> bool:
    return (not udgivelse.trukket_tilbage and udgivelse.min_skema <= skema
            and (udgivelse.kanal == PILOT
                 or i_udrulning(bruger_id, udgivelse.version, udgivelse.udrulning)))


def er_trukket_tilbage(version: str, udgivelser: Iterable[Udgivelse]) -> bool:
    return any(u.version == version and u.trukket_tilbage for u in udgivelser)


def vaelg_maal(aktuel: str, udgivelser: Iterable[Udgivelse], bruger_id: str, kanal: str,
               skema: int) -> Optional[Udgivelse]:
    """Den version, klienten skal installere – eller None (bliv på den aktuelle)."""
    alle = list(udgivelser)
    gyldige = sorted((u for u in alle if _synlig(u, kanal) and _gyldig(u, bruger_id, skema)),
                     key=lambda u: u.tupel)
    if not gyldige:
        return None
    nyeste, nu = gyldige[-1], version_tupel(aktuel)
    if nyeste.tupel > nu:
        return nyeste
    if er_trukket_tilbage(aktuel, alle) and nyeste.tupel != nu:
        return nyeste          # rollback til den nyeste gyldige
    return None


def skal_tvinges(aktuel: str, krav: Krav, maal: Optional[Udgivelse],
                 udgivelser: Iterable[Udgivelse] = ()) -> bool:
    """Skal opdateringen ske, før brugeren må arbejde videre?"""
    return (under_minimum(aktuel, krav) or er_trukket_tilbage(aktuel, udgivelser)
            or (maal is not None and maal.tvungen))
