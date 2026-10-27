"""Midlertidig webserver på pc'en, mens QR-vinduet er åbent.

Telefonen (på samme Wi-Fi) henter herfra:
  GET  /inbase-klargoering.apk   styrings-appen (kontrolsummen står i QR-koden)
  GET  /baggrund                 baggrundsbilledet (valgfrit)
  GET  /fl-update.apk            FL-UPDATE, når den er valgt som fil på pc'en (valgfrit)
  POST /api/klargjort            telefonens rapport, når den er færdig
                                 (kræver headeren X-Inbase-Token = engangskoden)

Serveren kører kun, mens vinduet er åbent, og stoppes, når det lukkes. Første
gang spørger Windows Firewall, om IN-BASE må modtage forbindelser – svar Ja
(privat netværk).
"""
import json
import logging
import mimetypes
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional

from app.infrastructure.mdm.qr import APK_STI

log = logging.getLogger(__name__)

MAKS_RAPPORT = 64 * 1024


def lokal_ip() -> str:
    """pc'ens IP på det lokale net (sender intet – vælger kun den udgående netværkskort)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def netvaerk() -> list[tuple[str, str]]:
    """pc'ens aktive netværk som (navn, IP) – Wi-Fi først.

    En bærbar med både netværksstik og Wi-Fi har en IP på hvert net. Telefonen er på
    Wi-Fi, så QR-koden skal pege på pc'ens Wi-Fi-IP – ikke den, Windows bruger som
    standard (ofte stikket)."""
    from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

    F = QNetworkInterface.InterfaceFlag
    standard = lokal_ip()
    fundne = []
    for kort in QNetworkInterface.allInterfaces():
        flag = kort.flags()
        if not (flag & F.IsUp and flag & F.IsRunning) or flag & F.IsLoopBack:
            continue
        for adr in kort.addressEntries():
            ip = adr.ip()
            # 169.254.x.x: kortet har ingen rigtig forbindelse.
            if ip.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol \
                    or ip.isLinkLocal():
                continue
            wifi = kort.type() == QNetworkInterface.InterfaceType.Wifi
            fundne.append((not wifi, ip.toString() != standard,
                           kort.humanReadableName(), ip.toString()))
    fundne.sort()
    return [(navn, ip) for *_, navn, ip in fundne] or [("Standard", standard)]


class KlargoeringsServer:
    def __init__(self, apk: Path, token: str, paa_rapport: Callable[[dict], None],
                 baggrund: Optional[Path] = None, fl_update: Optional[Path] = None,
                 port: int = 8765, vaert: str = "",
                 paa_hentning: Optional[Callable[[str], None]] = None):
        """paa_rapport og paa_hentning (stien til en fil, telefonen har hentet) kaldes fra
        serverens tråd – brugerfladen skal selv skifte tråd."""
        self.apk = apk
        self.token = token
        self.paa_rapport = paa_rapport
        self.paa_hentning = paa_hentning
        self.baggrund = baggrund
        self.fl_update = fl_update
        self._port = port
        self._vaert = vaert
        self._server = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self._vaert or lokal_ip()}:{self.port}"

    def start(self) -> str:
        if self._server is None:
            self._server = ThreadingHTTPServer(("0.0.0.0", self._port), self._handler())
            self._server.daemon_threads = True
            threading.Thread(target=self._server.serve_forever, name="mdm-server",
                             daemon=True).start()
            log.info("Klargøringsserver startet på %s", self.url)
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            log.info("Klargøringsserver stoppet")

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                log.info("Telefon %s: %s", self.client_address[0], fmt % args)

            def _fil(self, fil: Optional[Path], type_: str) -> None:
                if fil is None or not fil.is_file():
                    self.send_error(404)
                    return
                data = fil.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", type_)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                if server.paa_hentning:
                    server.paa_hentning(self.path)

            def do_GET(self):
                if self.path == "/":
                    # Fejlfinding: åbn http://<pc>:8765/ i en browser på samme Wi-Fi.
                    tekst = "IN-BASE klargøringsserver kører.\n" + "\n".join(
                        f"{sti}  {'findes' if fil and fil.is_file() else 'MANGLER'}"
                        for sti, fil in ((APK_STI, server.apk), ("/baggrund", server.baggrund),
                                         ("/fl-update.apk", server.fl_update)))
                    data = tekst.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                elif self.path == APK_STI:
                    self._fil(server.apk, "application/vnd.android.package-archive")
                elif self.path == "/fl-update.apk":
                    self._fil(server.fl_update, "application/vnd.android.package-archive")
                elif self.path == "/baggrund":
                    fil = server.baggrund
                    self._fil(fil, (mimetypes.guess_type(fil.name)[0] if fil else None)
                              or "application/octet-stream")
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path != "/api/klargjort":
                    self.send_error(404)
                    return
                if self.headers.get("X-Inbase-Token") != server.token:
                    self.send_error(403)
                    return
                laengde = int(self.headers.get("Content-Length") or 0)
                if not 0 < laengde <= MAKS_RAPPORT:
                    self.send_error(400)
                    return
                try:
                    rapport = json.loads(self.rfile.read(laengde).decode("utf-8"))
                except ValueError:
                    self.send_error(400)
                    return
                if not isinstance(rapport, dict):
                    self.send_error(400)
                    return
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                server.paa_rapport(rapport)

        return Handler
