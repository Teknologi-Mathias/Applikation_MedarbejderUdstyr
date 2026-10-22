"""Tidslinje for en sag: hændelser der kun kan tilføjes, ikke ændres.

Hver hændelse gemmer en hash af den forrige hændelse. Ændres eller slettes en
hændelse direkte i datafilen, brydes kæden, og tidslinjen viser en advarsel.
Det gør ændringer synlige – men forhindrer dem ikke. (I PostgreSQL bør
audit_events være insert-only via RLS; se docs/ARKITEKTUR.md.)

En hændelse kan have struktureret "data", fx {"type": "status", "fra": ...,
"til": ...}. Rapporterne bygger på disse data. Hændelser uden data hashes
præcis som før, så eksisterende tidslinjer forbliver intakte.
"""
import getpass
import hashlib
import json
from datetime import datetime
from typing import Callable, Optional

FELTER = ("tid", "bruger", "handling", "kommentar", "reference")

# Hvem udfører handlingen? Sættes af applikationen efter log på
# (app/bootstrap.py), så domænet ikke afhænger af brugerfladen.
_brugerkilde: Callable[[], Optional[str]] = lambda: None


def saet_brugerkilde(kilde: Callable[[], Optional[str]]) -> None:
    global _brugerkilde
    _brugerkilde = kilde


def nuvaerende_bruger() -> str:
    """Den bruger, der er logget ind i IN-BASE (ellers Windows-brugernavnet)."""
    logget_ind = _brugerkilde()
    if logget_ind:
        return logget_ind
    try:
        return getpass.getuser()
    except Exception:
        return "ukendt"


def nu() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _beregn_hash(forrige_hash: str, haendelse: dict) -> str:
    indhold = {felt: haendelse.get(felt, "") for felt in FELTER}
    if haendelse.get("data"):
        indhold["data"] = haendelse["data"]
    tekst = json.dumps(indhold, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((forrige_hash + tekst).encode("utf-8")).hexdigest()


class Historik:
    def __init__(self, haendelser=None):
        self._haendelser = [dict(h) for h in haendelser or [] if isinstance(h, dict)]

    def tilfoej(self, handling, kommentar="", reference="", bruger=None, tid=None,
                data: Optional[dict] = None) -> None:
        haendelse = {
            "tid": tid or nu(),
            "bruger": bruger or nuvaerende_bruger(),
            "handling": str(handling),
            "kommentar": str(kommentar or ""),
            "reference": str(reference or ""),
        }
        if data:
            haendelse["data"] = dict(data)
        forrige = self._haendelser[-1].get("hash", "") if self._haendelser else ""
        haendelse["hash"] = _beregn_hash(forrige, haendelse)
        self._haendelser.append(haendelse)

    def haendelser(self) -> list:
        """Kopier af hændelserne (ældste først), så de ikke kan ændres udefra."""
        return [dict(h) for h in self._haendelser]

    def af_type(self, type_: str) -> list:
        return [h for h in self.haendelser() if (h.get("data") or {}).get("type") == type_]

    def sidste_tid(self) -> Optional[datetime]:
        for haendelse in reversed(self._haendelser):
            try:
                return datetime.fromisoformat(haendelse.get("tid", ""))
            except ValueError:
                continue
        return None

    def er_intakt(self) -> bool:
        forrige = ""
        for haendelse in self._haendelser:
            if haendelse.get("hash") != _beregn_hash(forrige, haendelse):
                return False
            forrige = haendelse["hash"]
        return True

    def til_liste(self) -> list:
        return self.haendelser()

    def __len__(self) -> int:
        return len(self._haendelser)
