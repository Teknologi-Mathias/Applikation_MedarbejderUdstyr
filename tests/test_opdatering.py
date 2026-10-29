"""Central opdatering: valg af version (domæne), skemavagt (service) og download
med kontrolsum (infrastruktur, mod en lokal http-server – intet netværk)."""
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.domain import opdatering as op
from app.infrastructure import opdatering as filer
from app.repositories.fejl import DataFejl, KompatibilitetsFejl, ValideringsFejl
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

    # Udgivelse (registrerer kaldene).
    def upload(self, sti, data):
        self.uploadet = (sti, len(data))

    def opret(self, udgivelse):
        if getattr(self, "opret_fejler", False):
            raise DataFejl("Du har ikke rettighed til at registrere versionen.")
        self._udgivelser.append(udgivelse)

    def slet_fil(self, sti):
        self.slettede_filer = getattr(self, "slettede_filer", []) + [sti]

    def slet(self, version):
        self._udgivelser = [u for u in self._udgivelser if u.version != version]

    def opdater(self, version, **felter):
        self.opdateret = (version, felter)

    def saet_minimum(self, version):
        self.minimum = version


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


class UdgivelseTest(unittest.TestCase):
    """Indstillinger → Opdateringer / tools/udgiv_version.py: kontrol og udgivelse."""

    def setUp(self):
        self.mappe = Path(tempfile.mkdtemp(prefix="inbase-udgiv-"))
        self.repo = FalskRepo(udgivelser=[udgivelse("0.9.5")])
        self.service = OpdateringService(self.repo, self.mappe / "hentet", version="0.9.5",
                                         kraevet_skema=19, kan_installere=False)

    def tearDown(self):
        shutil.rmtree(self.mappe, ignore_errors=True)

    def pakke(self, navn="IN-BASE-Setup-v0.10.0.exe", data=b"installer", info=None):
        fil = self.mappe / navn
        fil.write_bytes(data)
        if info is not None:
            fil.with_name(navn + ".json").write_text(json.dumps(info), encoding="utf-8")
        return fil

    def afvist(self, fil, tekst):
        with self.assertRaises(ValideringsFejl) as fejl:
            self.service.kontroller_pakke(fil)
        self.assertIn(tekst, str(fejl.exception))

    def test_gyldig_pakke_med_foelgefil_fra_buildet(self):
        sha = hashlib.sha256(b"installer").hexdigest()
        fil = self.pakke(info={"version": "0.10.0", "kraevet_skema": 19, "commit": "abc1234",
                               "sha256": sha})
        pakke = self.service.kontroller_pakke(fil)
        self.assertEqual((pakke.version, pakke.sha256, pakke.commit, pakke.advarsler),
                         ("0.10.0", sha, "abc1234", ()))
        udgivet = self.service.udgiv(pakke, " Nyt ", tvungen=True)
        self.assertEqual((udgivet.kanal, udgivet.noter, udgivet.tvungen, udgivet.min_skema),
                         (op.PILOT, "Nyt", True, 19))
        self.assertEqual(self.repo.uploadet, ("IN-BASE-Setup-v0.10.0.exe", 9))

    def test_uden_foelgefil_advares_der(self):
        pakke = self.service.kontroller_pakke(self.pakke())
        self.assertEqual(len(pakke.advarsler), 2)        # ingen .json + intet rent commit

    def test_afviser_forkerte_pakker(self):
        self.afvist(self.pakke("IN-BASE.exe"), "ikke en IN-BASE-installer")
        self.afvist(self.pakke("IN-BASE-Setup-v0.9.5.exe"), "allerede udgivet")
        self.afvist(self.pakke("IN-BASE-Setup-v0.9.4.exe"), "ikke nyere")
        self.afvist(self.pakke(info={"version": "0.10.0", "kraevet_skema": 20}), "skema 20")
        self.afvist(self.pakke(info={"version": "0.10.1"}), "hører ikke til")
        fil = self.pakke()
        fil.with_name(fil.name + ".sha256").write_text("0" * 64, encoding="utf-8")
        self.afvist(fil, "Kontrolsummen")

    def test_afviser_forkert_version_i_exe_filen_og_for_stor_pakke(self):
        fil = self.pakke()
        with mock.patch("app.infrastructure.opdatering.exe_version", return_value="0.9.9"):
            self.afvist(fil, "bygget som 0.9.9")
        with open(fil, "wb") as stor:
            stor.truncate(50 * 1024 * 1024 + 1)
        self.afvist(fil, "50 MB")

    def test_ingen_fil_uden_registrering(self):
        self.repo.opret_fejler = True
        with self.assertRaises(DataFejl):
            self.service.udgiv(self.service.kontroller_pakke(self.pakke()))
        self.assertEqual(self.repo.slettede_filer, ["IN-BASE-Setup-v0.10.0.exe"])

    def test_frigiv_minimum_og_ryd(self):
        self.service.frigiv("0.9.5", 50)
        self.assertEqual(self.repo.opdateret, ("0.9.5", {"kanal": op.STABIL, "udrulning": 50}))
        with self.assertRaises(ValideringsFejl):
            self.service.frigiv("0.9.5", 0)
        with self.assertRaises(ValideringsFejl):
            self.service.saet_minimum("1.0")
        self.repo._udgivelser = [udgivelse(f"0.9.{n}") for n in range(8)] + [
            udgivelse("0.9.8", trukket_tilbage=True)]
        resultat = self.service.ryd(behold=5)
        self.assertEqual(len(resultat), 4)                  # 0.9.0-0.9.3
        self.assertEqual({u.version for u in self.repo.udgivelser()},
                         {"0.9.4", "0.9.5", "0.9.6", "0.9.7", "0.9.8"})


class OpdateringPanelTest(unittest.TestCase):
    """Siden i Indstillinger: træk en pakke ind, se den kontrolleret, og listen."""

    def test_vaelg_fil_og_liste(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication
        from app.ui import opdatering_side as side
        QApplication.instance() or QApplication([])
        mappe = Path(tempfile.mkdtemp(prefix="inbase-panel-"))
        try:
            repo = FalskRepo(udgivelser=[udgivelse("0.9.5", noter="Rettelser")])
            service = OpdateringService(repo, mappe, version="0.9.5", kraevet_skema=19)
            panel = side.OpdateringPanel(SimpleNamespace(opdatering=service))
            panel.opdater()
            self.assertEqual(panel.tabel.rowCount(), 1)
            self.assertIn("skema 19", panel.krav_label.text())
            fil = mappe / "IN-BASE-Setup-v0.10.0.exe"
            fil.write_bytes(b"installer")
            panel.vaelg_fil(str(fil))
            self.assertTrue(panel.udgiv_knap.isEnabled())
            self.assertIn("version 0.10.0", panel.pakke_label.text())
            self.assertEqual(side._installer([QUrl.fromLocalFile("x.txt"),
                                              QUrl.fromLocalFile(str(fil))]), str(fil).replace("\\", "/"))
        finally:
            shutil.rmtree(mappe, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
