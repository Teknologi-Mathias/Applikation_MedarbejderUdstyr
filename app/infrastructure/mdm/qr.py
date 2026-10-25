"""QR-koden til Android-klargøring (fabriksnulstillet telefon: tryk 6 gange på velkomstskærmen).

QR-koden fortæller opsætningsguiden, hvor styrings-appen hentes (IN-BASE's
midlertidige server), dens kontrolsum, Wi-Fi, sprog og tidszone. Ekstra-data
til appen (enhedsnavn, FL-UPDATE-link …) ligger i ADMIN_EXTRAS_BUNDLE – se
android/app/src/main/java/dk/instore/inbase/klargoering/Klargoering.java.
"""
import base64
import hashlib
import json
from pathlib import Path

from app.repositories.fejl import DataFejl

KOMPONENT = "dk.instore.inbase.klargoering/.AdminReceiver"
APK_STI = "/inbase-klargoering.apk"
_E = "android.app.extra."


def apk_kontrolsum(apk: Path) -> str:
    """SHA-256 af APK-filen, base64url uden '=' (PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM)."""
    return base64.urlsafe_b64encode(hashlib.sha256(apk.read_bytes()).digest()).decode().rstrip("=")


def byg_qr_payload(server: str, kontrolsum: str, ekstra: dict, wifi_ssid: str = "",
                   wifi_kode: str = "", wifi_type: str = "WPA", sprog: str = "da_DK",
                   tidszone: str = "Europe/Copenhagen") -> str:
    """server: "http://192.168.1.20:8765". ekstra: tekstværdier til styrings-appen."""
    data = {
        _E + "PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": KOMPONENT,
        _E + "PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": server + APK_STI,
        _E + "PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM": kontrolsum,
        # Systemapps beholdes; styrings-appen skjuler selv det, der ikke skal bruges
        # (så Motorolas egne Telefon- og SMS-apps ikke slås fra).
        _E + "PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
        _E + "PROVISIONING_LOCALE": sprog,
        _E + "PROVISIONING_TIME_ZONE": tidszone,
        _E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE": {k: str(v) for k, v in ekstra.items()},
    }
    if wifi_ssid:
        data[_E + "PROVISIONING_WIFI_SSID"] = wifi_ssid
        data[_E + "PROVISIONING_WIFI_SECURITY_TYPE"] = wifi_type
        if wifi_type != "NONE":
            data[_E + "PROVISIONING_WIFI_PASSWORD"] = wifi_kode
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def qr_matrix(tekst: str) -> list[list[bool]]:
    """QR-kodens moduler (True = sort), inkl. hvid kant."""
    try:
        import qrcode
    except ImportError as fejl:
        raise DataFejl("Pakken 'qrcode' mangler – kør: pip install -r requirements.txt") from fejl
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=4)
    qr.add_data(tekst)
    qr.make(fit=True)
    return qr.get_matrix()
