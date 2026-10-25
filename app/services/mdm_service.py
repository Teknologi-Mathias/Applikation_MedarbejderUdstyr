"""Telefoner (MDM): registrering og klargøring af driftstelefoner – uden server.

Klargøringen sker lokalt: IN-BASE viser en QR-kode og serverer styrings-appen
fra pc'en (app/infrastructure/mdm). Telefonen låser og klargør sig selv og
melder tilbage. Supabase får kun én række pr. telefon, og der skrives kun ved
oprettelse, rettelser og når en telefon melder sig klargjort.

Kun brugere med modulet Telefoner (og administratorer) bruger det – håndhæves af
RLS i migrering 010; her gives blot en pæn besked først.
"""
import logging
import re
import secrets
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.domain import adgang
from app.domain import mdm_enhed as md
from app.domain.historik import nu
from app.domain.mdm_enhed import MdmEnhed
from app.infrastructure import stier
from app.infrastructure.mdm.qr import apk_kontrolsum, byg_qr_payload
from app.repositories.base import MdmRepository
from app.repositories.fejl import ValideringsFejl

log = logging.getLogger(__name__)

INGEN_ADGANG = "Du har ikke adgang til Telefoner. Kontakt en administrator."
APK = stier.ASSETS_MAPPE / "mdm" / "inbase-klargoering.apk"
# Standardværdier i klargøringsvinduet. Wi-Fi og baggrund forudfyldes altid med dem
# (kan ændres pr. klargøring); de øvrige felter huskes på denne pc.
STANDARD = {
    "wifi_ssid": "FLFL",
    "wifi_kode": "frodefrode",
    "baggrund": str(stier.ASSETS_MAPPE / "INSTORE_LOCK.png"),
    "kontakt": "Kontakt din IT-administrator (Mathias – +45 8764 6576)",
}
HUSKEDE = ("wifi_type", "fl_kilde", "fl_fil", "fl_link", "ekstra_apps", "kontakt")
INDSTILLINGER = HUSKEDE + ("wifi_ssid", "baggrund")
FL_FIL, FL_LINK = "fil", "link"        # hvor FL-UPDATE kommer fra
MAKS_APK = 200 * 1024 * 1024
PAKKENAVN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
# Sti på klargøringsserveren, når FL-UPDATE er valgt som fil på pc'en.
FL_UPDATE_STI = "/fl-update.apk"


def er_apk(start: bytes) -> bool:
    """En APK er en ZIP-fil: starter med "PK\\x03\\x04"."""
    return start[:4] == b"PK\x03\x04"


@dataclass
class Klargoering:
    """Én klargøring: telefonen, engangskoden og de valgte indstillinger."""
    enhed: MdmEnhed
    token: str
    wifi_ssid: str = ""
    wifi_kode: str = ""
    wifi_type: str = "WPA"
    fl_update: str = ""                # APK-fil på pc'en eller https-link
    baggrund: str = ""                 # sti til billede på pc'en ("" = intet)
    ekstra_apps: str = ""              # kommaseparerede pakkenavne
    mail: bool = False                 # firma-mail (IMAP) i Gmail-appen
    kontakt: str = ""                  # låseskærm og spærrede funktioner
    nulstillingskode: str = field(default_factory=lambda: f"{secrets.randbelow(10**8):08d}")
    apk: Path = field(default=APK)
    # Problemer, der ikke stopper klargøringen (fx manglende FL-UPDATE) – vises ved QR-koden.
    advarsler: list[str] = field(default_factory=list)

    @property
    def fl_update_fil(self) -> Optional[Path]:
        """FL-UPDATE som fil på pc'en (serveres af klargøringsserveren) – ellers None."""
        if not self.fl_update or self.fl_update.startswith(("https://", "http://")):
            return None
        return Path(self.fl_update)

    def qr_tekst(self, server: str) -> str:
        # Standardlisten over tilladte apps (Kontakter, Kamera, Ur …) ligger i styrings-appen
        # (Klargoering.STANDARD_TILLADTE) – her sendes kun de ekstra, så QR-koden er let at scanne.
        ekstra = {
            "server": server, "token": self.token, "enhed_id": self.enhed.id,
            "navn": self.enhed.navn,
            "fl_update_url": server + FL_UPDATE_STI if self.fl_update_fil else self.fl_update,
            "baggrund": "1" if self.baggrund else "0", "mail": "1" if self.mail else "0",
            "nulstillingskode": self.nulstillingskode, "kontakt": self.kontakt,
            "tilladte": ",".join(p.strip() for p in self.ekstra_apps.split(",") if p.strip()),
        }
        return byg_qr_payload(server, apk_kontrolsum(self.apk), ekstra, self.wifi_ssid,
                              self.wifi_kode, self.wifi_type)


def valider(enhed: MdmEnhed, andre: list[MdmEnhed] = ()) -> None:
    """andre: de øvrige telefoner (enhedsnavnet skal være unikt)."""
    if not enhed.navn:
        raise ValideringsFejl("Angiv telefonens enhedsnavn fra ERP, fx ISM589.")
    if not md.NAVN_MOENSTER.match(enhed.navn):
        raise ValideringsFejl(f"Enhedsnavnet \"{enhed.navn}\" er ugyldigt. Brug 2-{md.MAKS_NAVN} "
                              "bogstaver, tal eller bindestreg, fx ISM589.")
    if any(a.navn == enhed.navn and a.id != enhed.id for a in andre):
        raise ValideringsFejl(f"Der findes allerede en telefon med enhedsnavnet {enhed.navn}.")
    tlf = enhed.telefonnummer.replace(" ", "").replace("+", "")
    if tlf and not tlf.isdigit():
        raise ValideringsFejl("Telefonnummeret må kun indeholde tal, mellemrum og +.")


class MdmService:
    def __init__(self, repo: MdmRepository, lokal=None,
                 aktuel_bruger: Callable[[], Optional[dict]] = lambda: None):
        """lokal: JsonLokalFil til de huskede klargøringsindstillinger (eller None)."""
        self.repo = repo
        self.lokal = lokal
        self._aktuel_bruger = aktuel_bruger

    ### ----- adgang ---------------------------------------------------------

    def har_adgang(self) -> bool:
        """Administratorer og brugere med modulet Telefoner (app/domain/adgang.py)."""
        return adgang.har_adgang(self._aktuel_bruger(), adgang.TELEFONER)

    def _kraev_admin(self) -> None:
        if not self.har_adgang():
            raise ValideringsFejl(INGEN_ADGANG)

    ### ----- telefoner ------------------------------------------------------

    def hent_alle(self) -> list[MdmEnhed]:
        return sorted(self.repo.hent_alle(), key=lambda e: e.navn)

    @staticmethod
    def _rens(data: dict) -> dict:
        rene = {k: str(data.get(k) or "").strip() for k in md.INFOFELTER if k in data}
        if "navn" in rene:
            rene["navn"] = md.normaliser_navn(rene["navn"])
        return rene

    def opret(self, data: dict) -> MdmEnhed:
        self._kraev_admin()
        enhed = MdmEnhed(**self._rens({k: data.get(k, "") for k in md.INFOFELTER}),
                         id=str(uuid.uuid4()))
        valider(enhed, self.repo.hent_alle())
        ny = self.repo.opret(enhed)
        log.info("Telefon %s oprettet", ny.navn)
        return ny

    def opdater_info(self, enhed: MdmEnhed, data: dict) -> MdmEnhed:
        self._kraev_admin()
        rene = {k: v for k, v in self._rens(data).items() if v != getattr(enhed, k)}
        if not rene:
            return enhed
        ny = MdmEnhed.fra_dict({**enhed.til_dict(), **rene})
        valider(ny, self.repo.hent_alle())
        self.repo.opdater([{"id": enhed.id, **rene}])
        return ny

    def marker_udgaaet(self, enhed: MdmEnhed) -> None:
        self._kraev_admin()
        self.repo.opdater([{"id": enhed.id, "status": md.UDGAAET}])

    def slet(self, enhed: MdmEnhed) -> None:
        self._kraev_admin()
        self.repo.slet(enhed.id)

    ### ----- klargøring -----------------------------------------------------

    def klargoering_mangler(self) -> str:
        return "" if APK.is_file() else (
            f"Styrings-appen mangler ({APK}). Byg den med scripts\\byg_klargoering_apk.ps1.")

    def reservekode(self) -> str:
        """Kode til telefoner klargjort uden egen nulstillingskode (styrings-app v1)."""
        self._kraev_admin()
        fil = APK.with_name("reservekode.txt")
        return fil.read_text(encoding="utf-8").strip() if fil.is_file() else ""

    def huskede_indstillinger(self) -> dict:
        """Startværdier i klargøringsvinduet: standardværdierne + det, der huskes på pc'en."""
        data = self.lokal.hent() if self.lokal else {}
        start = {k: str(data.get(k, "")) for k in HUSKEDE}
        start.update(wifi_ssid=STANDARD["wifi_ssid"], wifi_kode=STANDARD["wifi_kode"],
                     baggrund=STANDARD["baggrund"] if Path(STANDARD["baggrund"]).is_file() else "",
                     kontakt=start["kontakt"] or STANDARD["kontakt"])
        return start

    def ny_klargoering(self, enhed: MdmEnhed, indstillinger: dict) -> Klargoering:
        """indstillinger: wifi_ssid, wifi_kode, wifi_type, fl_kilde (fil/link), fl_fil, fl_link,
        baggrund, ekstra_apps, kontakt, mail.

        Kun manglende adgang/styrings-app stopper klargøringen. Fejl i FL-UPDATE, baggrund og
        ekstra apps bliver til advarsler – så QR-koden altid kan vises og telefonen testes."""
        self._kraev_admin()
        mangler = self.klargoering_mangler()
        if mangler:
            raise ValideringsFejl(mangler)
        v = {k: str(indstillinger.get(k) or "").strip() for k in INDSTILLINGER}
        v["kontakt"] = v["kontakt"][:120]
        v["fl_kilde"] = FL_LINK if v["fl_kilde"] == FL_LINK else FL_FIL
        advarsler = []
        try:
            fl = self._fl_update(v)
        except ValideringsFejl as fejl:
            advarsler.append(f"{fejl}\nTelefonen klargøres uden FL-UPDATE.")
            fl = ""
        apps = [p for p in v["ekstra_apps"].replace(" ", "").split(",") if p]
        ugyldige = [p for p in apps if not PAKKENAVN.match(p)]
        if ugyldige:
            advarsler.append(
                f"\"{', '.join(ugyldige)}\" er ikke et pakkenavn og springes over. Ekstra apps "
                "angives som pakkenavne, fx com.google.android.apps.photos (Google Fotos).")
        baggrund = v["baggrund"]
        if baggrund and not Path(baggrund).is_file():
            advarsler.append(f"Baggrundsbilledet findes ikke og springes over: {baggrund}")
            baggrund = ""
        if self.lokal:
            self.lokal.gem({k: v[k] for k in HUSKEDE})
        # Kort engangskode (16 tegn) – den gælder kun på det lokale net, mens vinduet er
        # åbent, og hvert tegn gør QR-koden tættere og sværere at scanne.
        return Klargoering(enhed, secrets.token_urlsafe(12), v["wifi_ssid"],
                           str(indstillinger.get("wifi_kode") or ""), v["wifi_type"] or "WPA",
                           fl, baggrund, ",".join(p for p in apps if p not in ugyldige),
                           bool(indstillinger.get("mail")), v["kontakt"], advarsler=advarsler)

    def _fl_update(self, v: dict) -> str:
        """Sti til FL-UPDATE på pc'en (linket hentes først) – ValideringsFejl ved problemer."""
        if v["fl_kilde"] == FL_LINK:
            # Linket hentes og kontrolleres her – telefonen får filen fra pc'en.
            return str(self._hent_link(v["fl_link"]))
        fl = v["fl_fil"]
        if not fl:
            raise ValideringsFejl("Ingen FL-UPDATE.apk valgt.")
        if not Path(fl).is_file():
            raise ValideringsFejl(f"FL-UPDATE-filen findes ikke: {fl}")
        if not er_apk(Path(fl).read_bytes()[:4]):
            raise ValideringsFejl(f"Filen er ikke en Android-app (APK): {fl}")
        return fl

    def _hent_link(self, link: str) -> Path:
        """Henter FL-UPDATE fra linket til en lokal fil og kontrollerer, at det er en APK."""
        if not link.startswith(("https://", "http://")):
            raise ValideringsFejl("Skriv linket til FL-UPDATE.apk (skal starte med https://).")
        try:
            with urllib.request.urlopen(link, timeout=30) as svar:
                data = svar.read(MAKS_APK + 1)
        except (OSError, ValueError) as fejl:
            raise ValideringsFejl(f"FL-UPDATE kunne ikke hentes fra {link} ({fejl}).") from fejl
        if not er_apk(data[:4]):
            raise ValideringsFejl(
                f"Linket giver ikke en APK-fil, men fx en hjemmeside: {link}\nBrug det direkte "
                "link til FL-UPDATE.apk – eller hent filen og vælg \"APK-fil på pc'en\".")
        if len(data) > MAKS_APK:
            raise ValideringsFejl("Filen fra linket er for stor til at være FL-UPDATE.")
        fil = stier.LOKAL_MAPPE / "fl-update-hentet.apk"
        fil.parent.mkdir(parents=True, exist_ok=True)
        fil.write_bytes(data)
        log.info("FL-UPDATE hentet fra %s (%s KB)", link, len(data) // 1024)
        return fil

    def registrer_klargjort(self, klargoering: Klargoering, rapport: dict) -> MdmEnhed:
        """Telefonens rapport (efter tjek af engangskoden i serveren) -> én skrivning."""
        if str(rapport.get("enhed_id")) != klargoering.enhed.id:
            raise ValideringsFejl("Rapporten kom fra en anden telefon end den, der klargøres.")
        felter = {k: str(rapport.get(k) or "")[:100] for k in md.RAPPORTFELTER}
        # Koden gemmes først, når telefonen har bekræftet – så den altid passer til telefonen.
        felter.update(status=md.KLARGJORT, klargjort=nu(),
                      nulstillingskode=klargoering.nulstillingskode)
        self.repo.opdater([{"id": klargoering.enhed.id, **felter}])
        log.info("Telefon %s klargjort (%s %s), fejl: %s", klargoering.enhed.navn,
                 felter["producent"], felter["model"], rapport.get("fejl") or "ingen")
        return MdmEnhed.fra_dict({**klargoering.enhed.til_dict(), **felter})
