"""Central opdatering: valg af version (domæne), skemavagt (service) og download
med kontrolsum (infrastruktur, mod en lokal http-server – intet netværk)."""
import hashlib
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.domain import opdatering as op
from app.infrastructure import opdatering as filer
from app.repositories.fejl import DataFejl, KompatibilitetsFejl
from app.services.opdatering_service import OpdateringService

BRUGER = "11111111-2222-3333-4444-555555555555"


def udgivelse(version, kanal=op.STABIL, **felter):
    return op.Udgivelse(version=version, kanal=kanal, sti=f"IN-BASE-Setup-v{version}.exe",
                        sha256="0" * 64, stoerrelse=1, **felter)


class VersionsvalgTest(unittest.TestCase):
    def maal(self, aktuel, udgivelser, kanal=op.STABIL, skema=19):
        valgt = op.vaelg_maal(aktuel, udgivelser, BRUGER, kanal, skema)
        return valgt.version if valgt else None

    def test_nyeste_gyldige_og_kun_nyere(self):
        alle = [udgivelse("0.9.4"), udgivelse("0.10.0"), udgivelse("0.10.1", op.PILOT)]
        self.assertEqual(self.maal("0.9.4", alle), "0.10.0", "pilot er kun til pilotbrugere")
        self.assertEqual(self.maal("0.9.4", alle, op.PILOT), "0.10.1")
        self.assertIsNone(self.maal("0.10.0", alle))
        self.assertIsNone(self.maal("0.10.0", [udgivelse("0.10.0", min_skema=20)], skema=19))
        self.assertEqual(self.maal("0.9.4", [udgivelse("0.10.0", min_skema=20),
                                             udgivelse("0.9.9")], skema=19), "0.9.9")

    def test_udrulning_er_deterministisk(self):
        self.assertIsNone(self.maal("0.9.4", [udgivelse("0.10.0", udrulning=0)]))
        andel = [op.i_udrulning(f"bruger-{n}", "0.10.0", 30) for n in range(400)]
        self.assertTrue(0.2 < sum(andel) / len(andel) < 0.4)
        self.assertEqual(andel, [op.i_udrulning(f"bruger-{n}", "0.10.0", 30) for n in range(400)])

    def test_tilbagetrukket_version_gaar_tilbage_uden_loekke(self):
        alle = [udgivelse("0.10.0"), udgivelse("0.10.1", trukket_tilbage=True)]
        self.assertEqual(self.maal("0.10.1", alle), "0.10.0", "rollback")
        self.assertIsNone(self.maal("0.10.0", alle), "den tilbagetrukne installeres aldrig")
        krav = op.Krav(19)
        self.assertTrue(op.skal_tvinges("0.10.1", krav, None, alle))
        self.assertFalse(op.skal_tvinges("0.10.0", krav, None, alle))

    def test_minimum_og_tvungen_udgivelse(self):
        self.assertTrue(op.skal_tvinges("0.9.4", op.Krav(19, "0.10.0"), None))
        self.assertFalse(op.skal_tvinges("0.10.0", op.Krav(19, "0.10.0"), None))
        self.assertTrue(op.skal_tvinges("0.10.0", op.Krav(19), udgivelse("0.10.1", tvungen=True)))
        self.assertIsNone(op.skema_fejl(op.Krav(19), 19))
        self.assertIn("migreringer", op.skema_fejl(op.Krav(18), 19))


class FalskRepo:
    def __init__(self, krav=None, udgivelser=(), url=""):
        self._krav = krav or {"schema_version": 19, "min_client_version": "0.0.0"}
        self._udgivelser, self.url = list(udgivelser), url

    def krav(self):
        return self._krav

    def udgivelser(self):
        return self._udgivelser

    def download_url(self, sti):
        return self.url

    def rapporter(self, version):
        raise DataFejl("ingen forbindelse")


class Server:
    """Lokal http-server, der leverer data (og evt. afbryder midtvejs)."""

    def __init__(self, data: bytes, afbryd: bool = False):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data[:len(data) // 2] if afbryd else data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/fil.exe"

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ServiceOgDownloadTest(unittest.TestCase):
    DATA = b"IN-BASE installer " * 50_000

    def setUp(self):
        self.mappe = Path(tempfile.mkdtemp(prefix="inbase-opdatering-"))
        self.sha = hashlib.sha256(self.DATA).hexdigest()

    def tearDown(self):
        shutil.rmtree(self.mappe, ignore_errors=True)

    def service(self, repo, version="0.9.4"):
        return OpdateringService(repo, self.mappe, version=version, kraevet_skema=19,
                                 kan_installere=False)

    def test_skemavagt_og_find(self):
        with self.assertRaises(KompatibilitetsFejl):
            self.service(FalskRepo({"schema_version": 0})).kontroller_skema()
        status = self.service(FalskRepo(udgivelser=[udgivelse("0.10.0")])).find(
            {"id": BRUGER, "kanal": op.STABIL})
        self.assertEqual((status.maal.version, status.tvungen), ("0.10.0", False))
        self.service(FalskRepo()).rapporter()            # fejl stopper intet

    def test_download_kontrolleres_og_genbruges(self):
        server = Server(self.DATA)
        try:
            u = op.Udgivelse("0.10.0", op.STABIL, "x.exe", self.sha, len(self.DATA))
            service = self.service(FalskRepo(url=server.url))
            fremdrift = []
            fil = service.hent(u, lambda hentet, i_alt: fremdrift.append((hentet, i_alt)))
            self.assertEqual(fil.read_bytes(), self.DATA)
            self.assertEqual(fremdrift[-1], (len(self.DATA), len(self.DATA)))
            self.assertTrue(service.er_hentet(u))
            service.repo.url = "http://127.0.0.1:1/findes-ikke"
            self.assertEqual(service.hent(u), fil, "en kontrolleret fil hentes ikke igen")
        finally:
            server.stop()

    def test_forkert_kontrolsum_eller_afbrudt_download_efterlader_ingen_fil(self):
        for afbryd, sha in ((False, "f" * 64), (True, self.sha)):
            server = Server(self.DATA, afbryd=afbryd)
            try:
                u = op.Udgivelse("0.10.0", op.STABIL, "x.exe", sha, len(self.DATA))
                with self.subTest(afbryd=afbryd), self.assertRaises(DataFejl):
                    self.service(FalskRepo(url=server.url)).hent(u)
                self.assertEqual(list(self.mappe.iterdir()), [], "ingen halve eller forkerte filer")
            finally:
                server.stop()

    def test_ryd_gamle_beholder_den_aktuelle(self):
        for navn in ("IN-BASE-Setup-v0.9.0.exe", "IN-BASE-Setup-v0.10.0.exe", "x.exe.part",
                     "installer.log"):
            (self.mappe / navn).write_bytes(b"x")
        filer.ryd_gamle(self.mappe, {"IN-BASE-Setup-v0.10.0.exe"})
        self.assertEqual(sorted(p.name for p in self.mappe.iterdir()),
                         ["IN-BASE-Setup-v0.10.0.exe", "installer.log"])


if __name__ == "__main__":
    unittest.main()
