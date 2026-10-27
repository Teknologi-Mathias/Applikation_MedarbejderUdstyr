"""Redning af en låst telefon uden browser: lever IN-BASE Klargøring via Wi-Fi-login.

Bruges, når USB, Bluetooth og den indbyggede opdatering alle er lukkede, og telefonens
egen nulstillingskode er gået tabt. Serverer den nyeste APK (v5+ med masterkode), så
telefonen kan opdateres og derefter nulstilles med masterkoden. Androids indbyggede
Wi-Fi-login-browser (captive portal) er ikke skjult og kan hente filer.

    python tools/mdm_redning.py

På telefonen: Wi-Fi → netværket → Rediger → Avanceret → Proxy: Manuel,
værtsnavn = pc'ens IP, port = 8765. Telefonen tror så, at nettet kræver login,
og viser "Log ind på netværk" – tryk på den, og hent opdateringen.
Se docs/MDM_OPSAETNING.md. Stop med Ctrl+C.
"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.mdm.lokal_server import lokal_ip  # noqa: E402

PORT = 8765
APK = Path(__file__).resolve().parents[1] / "assets" / "mdm" / "inbase-klargoering.apk"
IP = lokal_ip()
FORSIDE = f"""<!doctype html><html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>IN-BASE</title></head>
<body style="font-family:sans-serif;padding:24px;font-size:18px">
<h2>IN-BASE – opdatering af telefonen</h2>
<p><a href="http://{IP}:{PORT}/inbase-klargoering.apk"
 style="display:inline-block;padding:16px 24px;background:#6b3fa0;color:#fff;border-radius:8px;
 text-decoration:none">Hent IN-BASE Klargøring</a></p>
<p>Når den er hentet: tryk på notifikationen, tillad installation og vælg <b>Opdater</b>.<br>
Tast derefter <b>*#*#46227#*#*</b> i Telefon-appen og indtast koden.</p>
</body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"Telefon {self.client_address[0]}: {fmt % args}")

    def _send(self, kode: int, type_: str = "", data: bytes = b"", ekstra: dict = None):
        self.send_response(kode)
        if type_:
            self.send_header("Content-Type", type_)
        for k, v in (ekstra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        sti = self.path
        if sti.startswith("http://"):                      # forespørgsel via proxy
            dele = urlsplit(sti)
            if dele.hostname not in (IP, "127.0.0.1", "localhost"):
                # Androids forbindelsestjek (generate_204) → omdiriger = "kræver login"
                self._send(302, ekstra={"Location": f"http://{IP}:{PORT}/"})
                return
            sti = dele.path or "/"
        if sti == "/inbase-klargoering.apk":
            self._send(200, "application/vnd.android.package-archive", APK.read_bytes(),
                       {"Content-Disposition": 'attachment; filename="inbase-klargoering.apk"'})
        else:
            self._send(200, "text/html; charset=utf-8", FORSIDE)

    def do_CONNECT(self):
        self.send_error(502)                               # ingen https gennem "proxyen"


def main() -> int:
    if not APK.is_file():
        print(f"Mangler {APK} – byg den med scripts\\byg_klargoering_apk.ps1")
        return 1
    print(f"Redningsserver kører. Sæt telefonens Wi-Fi-proxy til:\n"
          f"  Værtsnavn: {IP}\n  Port:      {PORT}\nStop med Ctrl+C.")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
