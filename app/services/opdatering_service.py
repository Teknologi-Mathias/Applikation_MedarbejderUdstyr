"""Central opdatering af klienten. Reglerne står i app/domain/opdatering.py.

- kontroller_skema(): kaldes ved opstart (før log på). Er databasen ældre end
  KRAEVET_SKEMA, kastes KompatibilitetsFejl – programmet må ikke skrive, fordi
  nye felter ellers forsvinder lydløst.
- find(): efter log på og hver 4. time (hovedvinduet). Hvilken version brugeren
  skal have, og om opdateringen er tvungen.
- hent(): henter og kontrollerer installeren (i baggrunden); en allerede hentet
  og kontrolleret fil genbruges.
- installer(): starter installeren – kun i den installerede app (ikke fra kildekoden).
- Udgivelse (administratorer, Indstillinger → Opdateringer og tools/udgiv_version.py):
  kontroller_pakke() → udgiv() (pilot) → frigiv() (stabil) / tilbagetraek() /
  saet_minimum() / ryd().
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app import KRAEVET_SKEMA, __version__, version_tupel
from app.domain import opdatering as op
from app.infrastructure import opdatering as filer
from app.infrastructure import stier
from app.repositories.base import OpdateringRepository
from app.repositories.fejl import DataFejl, KompatibilitetsFejl, ValideringsFejl

log = logging.getLogger(__name__)


MAKS_STOERRELSE = 50 * 1024 * 1024        # Supabase Free: højst 50 MB pr. fil
_FILNAVN = re.compile(r"^IN-BASE-Setup-v(\d+\.\d+\.\d+)\.exe$", re.IGNORECASE)


@dataclass(frozen=True)
class Pakke:
    """En kontrolleret installer, klar til at blive udgivet (kontroller_pakke)."""
    sti: Path
    version: str
    sha256: str
    stoerrelse: int
    kraevet_skema: int
    commit: str = ""
    advarsler: tuple = ()


@dataclass(frozen=True)
class Status:
    krav: op.Krav
    maal: Optional[op.Udgivelse]       # None = ingen opdatering
    tvungen: bool


class OpdateringService:
    def __init__(self, repo: OpdateringRepository, mappe: Path, version: str = __version__,
                 kraevet_skema: int = KRAEVET_SKEMA, kan_installere: bool = stier.ER_FROSSET):
        self.repo = repo
        self.mappe = mappe
        self.version = version
        self.kraevet_skema = kraevet_skema
        self.kan_installere = kan_installere

    def kontroller_skema(self) -> op.Krav:
        krav = op.Krav.fra_dict(self.repo.krav())
        fejl = op.skema_fejl(krav, self.kraevet_skema)
        if fejl:
            log.error("Skemaversion %s < krævet %s", krav.skema, self.kraevet_skema)
            raise KompatibilitetsFejl(fejl)
        return krav

    def find(self, bruger: dict) -> Status:
        krav = self.kontroller_skema()
        udgivelser = self.repo.udgivelser()
        maal = op.vaelg_maal(self.version, udgivelser, str(bruger.get("id", "")),
                             bruger.get("kanal") or op.STABIL, krav.skema)
        tvungen = op.skal_tvinges(self.version, krav, maal, udgivelser)
        if maal or tvungen:
            log.info("Opdatering: aktuel %s, mål %s, tvungen %s", self.version,
                     maal.version if maal else "ingen", tvungen)
        return Status(krav, maal, tvungen)

    def filsti(self, udgivelse: op.Udgivelse) -> Path:
        return self.mappe / f"IN-BASE-Setup-v{udgivelse.version}.exe"

    def er_hentet(self, udgivelse: op.Udgivelse) -> bool:
        fil = self.filsti(udgivelse)
        return fil.is_file() and filer.sha256_fil(fil) == udgivelse.sha256

    def hent(self, udgivelse: op.Udgivelse,
             fremdrift: Optional[Callable[[int, int], None]] = None) -> Path:
        maal = self.filsti(udgivelse)
        if not self.er_hentet(udgivelse):
            try:
                filer.hent_fil(self.repo.download_url(udgivelse.sti), maal, udgivelse.sha256,
                               fremdrift)
            except filer.OpdateringsFejl as fejl:
                raise DataFejl(str(fejl)) from fejl
        filer.ryd_gamle(self.mappe, {maal.name})
        return maal

    def installer(self, installer: Path) -> None:
        if not self.kan_installere:
            raise ValideringsFejl("Opdateringer installeres kun i den installerede app – "
                                  "ikke når IN-BASE køres fra kildekoden.")
        filer.start_installer(installer, self.mappe / "installer.log")

    def rapporter(self) -> None:
        """Melder den kørende version (Indstillinger → Brugere). Fejl stopper intet."""
        try:
            self.repo.rapporter(self.version)
        except DataFejl:
            log.warning("Programversionen kunne ikke meldes", exc_info=True)

    ### ----- udgivelse (kun administratorer – RLS håndhæver det) ---------------
    # Bruges af Indstillinger → Opdateringer og tools/udgiv_version.py.

    def udgivelser(self) -> list[op.Udgivelse]:
        """Alle udgivelser, nyeste først (administratorer ser også pilot og tilbagetrukne)."""
        return sorted(self.repo.udgivelser(), key=lambda u: u.tupel, reverse=True)

    def krav(self) -> op.Krav:
        return op.Krav.fra_dict(self.repo.krav())

    def kontroller_pakke(self, fil: Path) -> Pakke:
        """Tjekker en installer, før den udgives. ValideringsFejl med forklaringen.

        Filnavn og størrelse (Supabase Free: 50 MB), versionen inde i exe-filen,
        kontrolsum og følgefil fra buildet (.sha256/.json), at versionen er nyere end
        alt udgivet, og at databasen har det skema, pakken kræver."""
        fil = Path(fil)
        match = _FILNAVN.match(fil.name)
        if not match or not fil.is_file():
            raise ValideringsFejl("Det er ikke en IN-BASE-installer. Træk filen "
                                  "IN-BASE-Setup-v<version>.exe fra release-mappen hertil.")
        version = match.group(1)
        stoerrelse = fil.stat().st_size
        if stoerrelse > MAKS_STOERRELSE:
            raise ValideringsFejl(f"Installeren fylder {stoerrelse / 1024 / 1024:.1f} MB – højst "
                                  "50 MB (Supabase Free). Se 'Pakkestørrelse' i docs/RELEASE.md.")
        indbygget = filer.exe_version(fil)
        if indbygget is not None and indbygget != version:
            raise ValideringsFejl(f"Filnavnet siger version {version}, men installeren er bygget "
                                  f"som {indbygget}. Byg igen i stedet for at omdøbe filen.")
        sha256 = filer.sha256_fil(fil)
        kontrol = fil.with_name(fil.name + ".sha256")
        if kontrol.is_file() and not kontrol.read_text(encoding="utf-8").strip().lower() \
                .startswith(sha256):
            raise ValideringsFejl(f"Kontrolsummen i {kontrol.name} passer ikke med installeren – "
                                  "filen er ændret efter buildet.")
        advarsler, kraevet, commit = [], self.kraevet_skema, ""
        info = fil.with_name(fil.name + ".json")
        if info.is_file():
            try:
                data = json.loads(info.read_text(encoding="utf-8"))
            except ValueError as fejl:
                raise ValideringsFejl(f"{info.name} kan ikke læses ({fejl}).") from fejl
            if data.get("version") != version or data.get("sha256", sha256) != sha256:
                raise ValideringsFejl(f"{info.name} hører ikke til denne installer.")
            kraevet, commit = int(data.get("kraevet_skema") or kraevet), str(data.get("commit") or "")
        else:
            advarsler.append(f"Ingen {info.name} fra buildet: skemakravet sættes til "
                             f"{kraevet} (denne versions krav), og commit er ukendt.")
        if not commit or commit.endswith("+ucommittet"):
            advarsler.append("Bygget uden et rent commit – kan ikke genskabes fra git.")
        udgivne = self.repo.udgivelser()
        if any(u.version == version for u in udgivne):
            raise ValideringsFejl(f"Version {version} er allerede udgivet.")
        nyeste = max(udgivne, key=lambda u: u.tupel, default=None)
        if nyeste is not None and version_tupel(version) <= nyeste.tupel:
            raise ValideringsFejl(f"Version {version} er ikke nyere end den senest udgivne "
                                  f"({nyeste.version}). Ret versionsnummeret og byg igen – "
                                  "en dårlig version stoppes med 'Træk tilbage'.")
        skema = self.krav().skema
        if skema < kraevet:
            raise ValideringsFejl(f"Version {version} kræver databaseskema {kraevet}, men databasen "
                                  f"har {skema}. Kør de manglende migreringer først "
                                  "(docs/SUPABASE_OPSAETNING.md) – ellers kan klienterne ikke starte.")
        return Pakke(fil, version, sha256, stoerrelse, kraevet, commit, tuple(advarsler))

    def udgiv(self, pakke: Pakke, noter: str = "", tvungen: bool = False) -> op.Udgivelse:
        """Uploader installeren og registrerer den som PILOT (ingen fil uden registrering)."""
        udgivelse = op.Udgivelse(
            version=pakke.version, kanal=op.PILOT, sti=pakke.sti.name, sha256=pakke.sha256,
            stoerrelse=pakke.stoerrelse, min_skema=pakke.kraevet_skema, tvungen=tvungen,
            noter=(noter or "").strip(), commit=pakke.commit)
        self.repo.upload(udgivelse.sti, pakke.sti.read_bytes())
        try:
            self.repo.opret(udgivelse)
        except Exception:
            self.repo.slet_fil(udgivelse.sti)
            raise
        log.info("Version %s udgivet til pilot (%s bytes, commit %s)", udgivelse.version,
                 udgivelse.stoerrelse, udgivelse.commit or "ukendt")
        return udgivelse

    def frigiv(self, version: str, procent: int = 100) -> None:
        if not 0 < int(procent) <= 100:
            raise ValideringsFejl("Andelen skal være mellem 1 og 100 %.")
        self.repo.opdater(version, kanal=op.STABIL, udrulning=int(procent))
        log.info("Version %s frigivet som stabil til %s %%", version, procent)

    def tilbagetraek(self, version: str, fortryd: bool = False) -> None:
        self.repo.opdater(version, trukket_tilbage=not fortryd)
        log.info("Version %s %s", version, "gyldig igen" if fortryd else "trukket tilbage")

    def saet_minimum(self, version: str) -> None:
        try:
            version_tupel(version)
        except ValueError as fejl:
            raise ValideringsFejl(str(fejl)) from fejl
        self.repo.saet_minimum(version)
        log.info("Mindste klientversion sat til %s", version)

    def ryd(self, behold: int = 5) -> list[str]:
        """Sletter gamle installere fra Storage – aldrig de `behold` nyeste eller den nyeste
        stabile. Tilbagetrukne beholder rækken (så klienter ser tilbagetrækningen)."""
        alle = self.udgivelser()
        stabile = [u for u in alle if u.kanal == op.STABIL and not u.trukket_tilbage]
        beskyt = {u.version for u in alle[:max(behold, 1)]} | {u.version for u in stabile[:1]}
        resultat = []
        for u in alle:
            if u.version in beskyt:
                continue
            self.repo.slet_fil(u.sti)
            if u.trukket_tilbage:
                resultat.append(f"{u.version}: installeren er slettet (rækken bevares)")
            else:
                self.repo.slet(u.version)
                resultat.append(f"{u.version}: slettet")
        return resultat
