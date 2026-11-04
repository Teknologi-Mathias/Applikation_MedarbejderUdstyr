"""Telefoner (MDM): driftstelefoner, der klargøres direkte fra IN-BASE.

Telefonen identificeres ved sit enhedsnavn fra virksomhedens ERP (fx ISM589)
– ikke ved en medarbejder. Tildeling til medarbejdere sker i ERP.

Forløb: telefonen oprettes (Afventer klargøring) → QR-koden scannes, og
styrings-appen låser og klargør telefonen → den melder tilbage med model,
serienr. og IMEI (Klargjort). Udgået sættes manuelt, når telefonen tages ud.

En telefon, der fjernes fra listen, slettes ikke, men arkiveres (Telefoner → Arkiv),
så nulstillingskoden mm. bevares og telefonen kan gendannes.

Find telefon (migrering 024): IN-BASE sætter find_anmodet, og telefonen svarer med én
position ved sit næste tjek (skærmen tændes, nettet kommer tilbage, eller én gang i timen).
Lås skærmlåsen op (migrering 025) går samme vej: telefonen sætter en midlertidig PIN, nemlig
skærmlåskoden (aendringskode(..., SKAERMLAAS)).

Statusserne svarer til check-betingelsen i migrering 008 – ændres de her,
skal de også ændres dér.
"""
import hashlib
import re
from dataclasses import dataclass, field, fields

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
# Felter, der gemmes ved ændringer (svarer til inbase_mdm_update_devices i migrering 025).
GEMTE_FELTER = INFOFELTER + RAPPORTFELTER + ("status", "klargjort", "nulstillingskode", "mail",
                                            "arkiveret", "find_anmodet", "laas_op_anmodet")

# Ændringskoder: én kode pr. telefon og handling, tastes i telefonens administrator-menu.
CHROME = "chrome"          # supportkoden: vis/skjul Chrome
MAIL_TIL = "mail:til"
MAIL_FRA = "mail:fra"
SKAERMLAAS = "skaermlaas"  # godkend et skift af skærmlåsen (ellers registreres det)


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
    mail: bool = False              # firma-mail (IMAP) i Gmail-appen
    arkiveret: str = ""             # tidspunkt, telefonen blev fjernet fra listen ("" = aktiv)
    find_anmodet: str = ""          # Find telefon: tidspunkt for anmodningen ("" = ingen)
    senest_set: str = ""            # telefonens seneste tjek (højst én gang i timen)
    # Seneste svar på Find telefon: {lat, lng, noejagtighed, batteri, tid, modtaget} eller {fejl, …}
    position: dict = field(default_factory=dict)
    laas_op_anmodet: str = ""       # Lås skærmlåsen op: tidspunkt for anmodningen ("" = ingen)
    laas_op_klar: bool = False      # telefonens nulstillingsnøgle er aktiv (meldt af telefonen)
    laas_op_svar: dict = field(default_factory=dict)   # seneste svar: {ok, fejl, modtaget}
    app_version: str = ""           # styrings-appens version, meldt af telefonen (migrering 026)
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


def aendringskode(nulstillingskode: str, handling: str) -> str:
    """6-cifret kode til én handling (CHROME, MAIL_TIL, MAIL_FRA, SKAERMLAAS) i
    administrator-menuen.

    Udledes af nulstillingskoden – samme beregning som AdminActivity.aendringskode på
    telefonen – så den ikke skal gemmes, og nulstillingskoden ikke kan regnes baglæns."""
    if not nulstillingskode:
        return ""
    h = hashlib.sha256(f"{handling}:{nulstillingskode}".encode("utf-8")).digest()
    return f"{int.from_bytes(h[:4], 'big') % 10**6:06d}"


def sporingsnoegle(nulstillingskode: str) -> str:
    """Nøglen, telefonen bruger til sit tjek (Find telefon) – samme beregning som
    Sporing.noegle på telefonen og inbase_mdm_phone_checkin i migrering 024."""
    if not nulstillingskode:
        return ""
    return hashlib.sha256(f"sporing:{nulstillingskode}".encode("utf-8")).hexdigest()


def kortlink(position: dict) -> str:
    """Google Maps-link til positionen ("" uden koordinater)."""
    if position.get("lat") is None or position.get("lng") is None:
        return ""
    return f"https://maps.google.com/?q={position['lat']},{position['lng']}"


def supportkode(nulstillingskode: str) -> str:
    """Kode til brugeren: viser/skjuler Chrome i administrator-menuen (*#*#46227#*#*)."""
    return aendringskode(nulstillingskode, CHROME)


def normaliser_navn(navn: str) -> str:
    """" ism589 " -> "ISM589"."""
    return str(navn or "").strip().upper()
