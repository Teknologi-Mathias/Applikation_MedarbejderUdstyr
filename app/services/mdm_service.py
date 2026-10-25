"""Telefoner (MDM): registrering og klargøring af driftstelefoner – uden server.

Klargøringen sker lokalt: IN-BASE viser en QR-kode og serverer styrings-appen
fra pc'en (app/infrastructure/mdm). Telefonen låser og klargør sig selv og
melder tilbage. Supabase får kun én række pr. telefon, og der skrives kun ved
oprettelse, rettelser og når en telefon melder sig klargjort.

Kun administratorer bruger modulet (håndhæves af RLS i migrering 007/008; her
gives blot en pæn besked først).
"""
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.domain import mdm_enhed as md
from app.domain.historik import nu
from app.domain.mdm_enhed import MdmEnhed
from app.infrastructure import stier
from app.infrastructure.mdm.qr import apk_kontrolsum, byg_qr_payload
from app.repositories.base import MdmRepository
from app.repositories.fejl import ValideringsFejl
from app.services.auth_service import ROLLE_ADMIN

log = logging.getLogger(__name__)

KUN_ADMIN = "Kun administratorer kan administrere telefoner."
APK = stier.ASSETS_MAPPE / "mdm" / "inbase-klargoering.apk"
# Klargøringsindstillinger, som huskes på denne pc (aldrig Wi-Fi-koden).
HUSKEDE = ("wifi_ssid", "wifi_type", "fl_kilde", "fl_fil", "fl_link", "baggrund", "ekstra_apps")
FL_FIL, FL_LINK = "fil", "link"        # hvor FL-UPDATE kommer fra
# Sti på klargøringsserveren, når FL-UPDATE er valgt som fil på pc'en.
FL_UPDATE_STI = "/fl-update.apk"


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
    nulstillingskode: str = field(default_factory=lambda: f"{secrets.randbelow(10**8):08d}")
    apk: Path = field(default=APK)

    @property
    def fl_update_fil(self) -> Optional[Path]:
        """FL-UPDATE som fil på pc'en (serveres af klargøringsserveren) – ellers None."""
        return None if self.fl_update.startswith(("https://", "http://")) else Path(self.fl_update)

    def qr_tekst(self, server: str) -> str:
        # Standardlisten over tilladte apps (Kontakter, Kamera, Ur …) ligger i styrings-appen
        # (Klargoering.STANDARD_TILLADTE) – her sendes kun de ekstra, så QR-koden er let at scanne.
        ekstra = {
            "server": server, "token": self.token, "enhed_id": self.enhed.id,
            "navn": self.enhed.navn,
            "fl_update_url": server + FL_UPDATE_STI if self.fl_update_fil else self.fl_update,
            "baggrund": "1" if self.baggrund else "0", "mail": "1" if self.mail else "0",
            "nulstillingskode": self.nulstillingskode,
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

    def er_administrator(self) -> bool:
        bruger = self._aktuel_bruger()
        return bool(bruger) and bruger.get("rolle") == ROLLE_ADMIN

    def _kraev_admin(self) -> None:
        if not self.er_administrator():
            raise ValideringsFejl(KUN_ADMIN)

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
        data = self.lokal.hent() if self.lokal else {}
        return {k: str(data.get(k, "")) for k in HUSKEDE}

    def ny_klargoering(self, enhed: MdmEnhed, indstillinger: dict) -> Klargoering:
        """indstillinger: wifi_ssid, wifi_kode, wifi_type, fl_kilde (fil/link), fl_fil, fl_link,
        baggrund, ekstra_apps, mail."""
        self._kraev_admin()
        mangler = self.klargoering_mangler()
        if mangler:
            raise ValideringsFejl(mangler)
        v = {k: str(indstillinger.get(k) or "").strip() for k in HUSKEDE}
        v["fl_kilde"] = FL_LINK if v["fl_kilde"] == FL_LINK else FL_FIL
        if v["fl_kilde"] == FL_FIL:
            fl = v["fl_fil"]
            if not fl:
                raise ValideringsFejl("Vælg FL-UPDATE.apk på pc'en (eller skift til link).")
            if not (Path(fl).is_file() and fl.lower().endswith(".apk")):
                raise ValideringsFejl(f"FL-UPDATE-filen findes ikke eller er ikke en .apk: {fl}")
        else:
            fl = v["fl_link"]
            if not fl.startswith(("https://", "http://")):
                raise ValideringsFejl("Skriv linket til FL-UPDATE.apk (skal starte med https://).")
        if v["baggrund"] and not Path(v["baggrund"]).is_file():
            raise ValideringsFejl(f"Baggrundsbilledet findes ikke: {v['baggrund']}")
        if self.lokal:
            self.lokal.gem(v)
        return Klargoering(enhed, secrets.token_urlsafe(24), v["wifi_ssid"],
                           str(indstillinger.get("wifi_kode") or ""), v["wifi_type"] or "WPA",
                           fl, v["baggrund"], v["ekstra_apps"], bool(indstillinger.get("mail")))

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
