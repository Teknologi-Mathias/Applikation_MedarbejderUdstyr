"""Tidslinje for en afviklingssag: hændelser der kun kan tilføjes, ikke ændres.

Hver hændelse gemmer en hash af den forrige hændelse. Ændres eller slettes en
hændelse direkte i JSON-filen, brydes kæden, og tidslinjen viser en advarsel.
Det gør ændringer synlige – men forhindrer dem ikke.
"""
import getpass
import hashlib
import json
from datetime import datetime

from app import session

FELTER = ("tid", "bruger", "handling", "kommentar", "reference")


def nuvaerende_bruger():
    """Den bruger, der er logget ind i IN-BASE (ellers Windows-brugernavnet)."""
    logget_ind = session.brugernavn()
    if logget_ind:
        return logget_ind
    try:
        return getpass.getuser()
    except Exception:
        return "ukendt"


def _beregn_hash(forrige_hash, haendelse):
    indhold = json.dumps(
        {felt: haendelse.get(felt, "") for felt in FELTER},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256((forrige_hash + indhold).encode("utf-8")).hexdigest()


class Historik:
    def __init__(self, haendelser=None):
        self._haendelser = [dict(h) for h in haendelser or [] if isinstance(h, dict)]

    def tilfoej(self, handling, kommentar="", reference="", bruger=None, tid=None):
        haendelse = {
            "tid": tid or datetime.now().isoformat(timespec="seconds"),
            "bruger": bruger or nuvaerende_bruger(),
            "handling": str(handling),
            "kommentar": str(kommentar or ""),
            "reference": str(reference or ""),
        }
        forrige = self._haendelser[-1].get("hash", "") if self._haendelser else ""
        haendelse["hash"] = _beregn_hash(forrige, haendelse)
        self._haendelser.append(haendelse)

    def haendelser(self):
        """Kopier af hændelserne (ældste først), så de ikke kan ændres udefra."""
        return [dict(h) for h in self._haendelser]

    def er_intakt(self):
        forrige = ""
        for haendelse in self._haendelser:
            if haendelse.get("hash") != _beregn_hash(forrige, haendelse):
                return False
            forrige = haendelse["hash"]
        return True

    def til_liste(self):
        return self.haendelser()

    def __len__(self):
        return len(self._haendelser)


### ----- automatisk registrering af ændringer -------------------------------

_STAMDATA = (
    ("navn", "Navn"),
    ("loennr", "Lønnr."),
    ("fratraedelsesdato", "Sidste arbejdsdag"),
    ("email", "E-mail"),
    ("tracking_link", "Tracking-link"),
    ("kommentar", "Kommentar"),
)


def registrer_aendringer(gammel, ny):
    """Skriver forskellene mellem to udgaver af en medarbejder i ny.historik."""
    aendret = [
        f"{label}: {getattr(gammel, felt) or '–'} → {getattr(ny, felt) or '–'}"
        for felt, label in _STAMDATA
        if getattr(gammel, felt) != getattr(ny, felt)
    ]
    if aendret:
        ny.historik.tilfoej("Stamdata ændret", "; ".join(aendret))

    if (gammel.status_manuel, gammel.status_begrundelse) != (
        ny.status_manuel, ny.status_begrundelse
    ):
        if ny.status_manuel:
            ny.historik.tilfoej(
                f"Status låst manuelt: {ny.status_manuel}", ny.status_begrundelse
            )
        else:
            ny.historik.tilfoej("Manuel status fjernet", "Status beregnes igen ud fra opgaverne")

    gamle = {o.id: o for o in gammel.opgaver}
    nye = {o.id: o for o in ny.opgaver}
    for opgave_id, opgave in nye.items():
        foer = gamle.get(opgave_id)
        if foer is None:
            ny.historik.tilfoej(f"Opgave tilføjet: {opgave.navn}", reference=opgave_id)
            continue
        if foer.status != opgave.status:
            kommentar = opgave.begrundelse if opgave.status == "Undtaget" else ""
            ny.historik.tilfoej(
                f"{opgave.navn}: {foer.status} → {opgave.status}", kommentar, opgave_id
            )
        andet = [
            label for felt, label in (
                ("navn", "navn"), ("ansvarlig", "ansvarlig"), ("frist", "frist"),
                ("udstyr", "udstyr"), ("naeste_handling", "næste handling"),
                ("obligatorisk", "obligatorisk"),
            )
            if getattr(foer, felt) != getattr(opgave, felt)
        ]
        if andet:
            ny.historik.tilfoej(
                f"Opgave ændret: {opgave.navn}", "Ændret: " + ", ".join(andet), opgave_id
            )
    for opgave_id, opgave in gamle.items():
        if opgave_id not in nye:
            ny.historik.tilfoej(f"Opgave slettet: {opgave.navn}", reference=opgave_id)
