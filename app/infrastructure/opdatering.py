"""Hentning og start af en ny version (filer og processer – ingen forretningsregler).

- hent_fil(): streamer installeren til "<navn>.part", kontrollerer SHA-256 og
  omdøber først derefter. Forkert kontrolsum eller afbrudt download efterlader
  ingen fil – og den installerede version røres aldrig.
- start_installer(): starter Inno-installeren stille og uafhængigt af IN-BASE,
  som derefter lukker sig selv. Installeren lukker resterende processer
  (/CLOSEAPPLICATIONS), udskifter filerne og starter IN-BASE igen
  (/OPDATERING=1, se installer/IN-BASE.iss). Installerens log skrives i
  Opdateringer-mappen til fejlfinding.
"""
import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

_BLOK = 256 * 1024
_TIMEOUT = httpx.Timeout(30.0, read=60.0)


class OpdateringsFejl(Exception):
    """Opdateringen kunne ikke hentes eller kontrolleres."""


def sha256_fil(sti: Path) -> str:
    h = hashlib.sha256()
    with open(sti, "rb") as fil:
        for blok in iter(lambda: fil.read(_BLOK), b""):
            h.update(blok)
    return h.hexdigest()


def hent_fil(url: str, maal: Path, sha256: str,
             fremdrift: Optional[Callable[[int, int], None]] = None) -> Path:
    """Henter url til maal og kontrollerer kontrolsummen. fremdrift(hentet, i_alt)."""
    sha256 = sha256.lower()
    maal.parent.mkdir(parents=True, exist_ok=True)
    delvis = maal.with_name(maal.name + ".part")
    h = hashlib.sha256()
    try:
        with httpx.stream("GET", url, timeout=_TIMEOUT, follow_redirects=True) as svar:
            svar.raise_for_status()
            i_alt, hentet = int(svar.headers.get("Content-Length") or 0), 0
            with open(delvis, "wb") as fil:
                for blok in svar.iter_bytes(_BLOK):
                    fil.write(blok)
                    h.update(blok)
                    hentet += len(blok)
                    if fremdrift:
                        fremdrift(hentet, i_alt)
        if h.hexdigest() != sha256:
            log.error("Forkert kontrolsum for %s: %s (forventet %s)", maal.name, h.hexdigest(), sha256)
            raise OpdateringsFejl("Den hentede opdatering har en forkert kontrolsum og er slettet. "
                                  "Den nuværende version kører videre.")
        os.replace(delvis, maal)
        log.info("Opdatering hentet og kontrolleret: %s", maal)
        return maal
    except httpx.HTTPError as fejl:
        log.warning("Opdateringen kunne ikke hentes", exc_info=True)
        raise OpdateringsFejl(f"Opdateringen kunne ikke hentes ({fejl}). Der prøves igen senere.") \
            from fejl
    finally:
        delvis.unlink(missing_ok=True)


def start_installer(installer: Path, logfil: Path) -> None:
    """Starter installeren stille i sin egen proces (IN-BASE lukker bagefter)."""
    argumenter = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                  "/CLOSEAPPLICATIONS", "/OPDATERING=1", f"/LOG={logfil}"]
    flag = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform == "win32" else 0)
    log.info("Starter installeren: %s", " ".join(argumenter))
    subprocess.Popen(argumenter, creationflags=flag, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def exe_version(sti: Path) -> str | None:
    """Versionen indbygget i en Windows-exe ("0.9.5" fra filversion 0.9.5.0) – None, hvis
    den ikke kan læses (ikke Windows, ingen versionsinfo). Inno Setup skriver
    AppVersion ind i installeren (VersionInfoVersion i installer/IN-BASE.iss)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _FastInfo(ctypes.Structure):          # VS_FIXEDFILEINFO (de første felter)
            _fields_ = [(navn, wintypes.DWORD) for navn in (
                "signatur", "strukturversion", "fil_ms", "fil_ls", "produkt_ms", "produkt_ls")]

        api = ctypes.windll.version
        stoerrelse = api.GetFileVersionInfoSizeW(str(sti), None)
        if not stoerrelse:
            return None
        data = ctypes.create_string_buffer(stoerrelse)
        if not api.GetFileVersionInfoW(str(sti), 0, stoerrelse, data):
            return None
        peger, laengde = ctypes.c_void_p(), wintypes.UINT()
        if not api.VerQueryValueW(data, "\\", ctypes.byref(peger), ctypes.byref(laengde)):
            return None
        info = ctypes.cast(peger, ctypes.POINTER(_FastInfo)).contents
        return f"{info.fil_ms >> 16}.{info.fil_ms & 0xFFFF}.{info.fil_ls >> 16}"
    except (AttributeError, OSError, ValueError):
        log.warning("Versionen kunne ikke læses fra %s", sti, exc_info=True)
        return None


def ryd_gamle(mappe: Path, behold: set[str]) -> None:
    """Sletter hentede installere (og halve downloads), undtagen filnavnene i behold."""
    if not mappe.is_dir():
        return
    for fil in mappe.iterdir():
        if fil.is_file() and fil.name not in behold and fil.suffix in (".exe", ".part"):
            try:
                fil.unlink()
            except OSError:
                log.warning("Kunne ikke slette %s", fil, exc_info=True)
