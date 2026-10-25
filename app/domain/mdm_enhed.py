"""Telefoner (MDM): driftstelefoner, der klargøres direkte fra IN-BASE.

Telefonen identificeres ved sit enhedsnavn fra virksomhedens ERP (fx ISM589)
– ikke ved en medarbejder. Tildeling til medarbejdere sker i ERP.

Forløb: telefonen oprettes (Afventer klargøring) → QR-koden scannes, og
styrings-appen låser og klargør telefonen → den melder tilbage med model,
serienr. og IMEI (Klargjort). Udgået sættes manuelt, når telefonen tages ud.

Statusserne svarer til check-betingelsen i migrering 008 – ændres de her,
skal de også ændres dér.
"""
import re
from dataclasses import dataclass, fields

AFVENTER = "Afventer klargøring"
KLARGJORT = "Klargjort"
UDGAAET = "Udgået"
STATUSSER = (AFVENTER, KLARGJORT, UDGAAET)

# Enhedsnavn fra ERP: store bogstaver, tal og bindestreg, 2-20 tegn (fx ISM589).
# Samme regel som check-betingelsen i migrering 007.
MAKS_NAVN = 20
NAVN_MOENSTER = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,19}$")

# Felter, som administratoren selv retter.
INFOFELTER = ("navn", "telefonnummer", "note")
# Felter, som telefonen melder tilbage ved klargøring.
RAPPORTFELTER = ("producent", "model", "serienummer", "imei", "android_version")
# Felter, der gemmes ved ændringer (svarer til inbase_mdm_update_devices i migrering 009).
GEMTE_FELTER = INFOFELTER + RAPPORTFELTER + ("status", "klargjort", "nulstillingskode")


@dataclass
class MdmEnhed:
    navn: str                       # enhedsnavn fra ERP, fx "ISM589" (unikt)
    telefonnummer: str = ""
    note: str = ""
    status: str = AFVENTER
    producent: str = ""
    model: str = ""
    serienummer: str = ""
    imei: str = ""
    android_version: str = ""
    klargjort: str = ""             # tidspunkt for seneste klargøring
    nulstillingskode: str = ""      # *#*#46227#*#* på telefonen → fabriksnulstilling
    oprettet_af: str = ""
    id: str = ""
    oprettet: str = ""
    opdateret: str = ""

    @property
    def visningsmodel(self) -> str:
        return " ".join(x for x in (self.producent, self.model) if x)

    def til_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def fra_dict(cls, data: dict) -> "MdmEnhed":
        navne = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in navne})


def normaliser_navn(navn: str) -> str:
    """" ism589 " -> "ISM589"."""
    return str(navn or "").strip().upper()
