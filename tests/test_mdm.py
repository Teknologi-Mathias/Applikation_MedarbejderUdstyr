"""Telefoner (MDM): QR-kode, lokal klargøringsserver og MdmService (JSON-lagring)."""
import io
import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app import session
from app.domain import mdm_enhed as md
from app.infrastructure.mdm.lokal_server import KlargoeringsServer
from app.infrastructure.mdm.qr import KOMPONENT, apk_kontrolsum, byg_qr_payload
from app.repositories.fejl import ValideringsFejl
from app.repositories.json.opsaetning_repository import JsonLokalFil
from app.services.mdm_service import MdmService
from tests.hjaelp import TjenesteTest

MIGRERINGER = Path(__file__).resolve().parents[1] / "app/infrastructure/database/migrations"
MIGRERING_008 = MIGRERINGER / "008_mdm_lokal_klargoering.sql"
MIGRERING_012 = MIGRERINGER / "012_mdm_mail_og_signering.sql"
E = "android.app.extra."
APK_DATA = b"PK falsk apk"


class QrTest(unittest.TestCase):
    def test_qr_peger_paa_pc_og_har_kontrolsum_wifi_og_ekstra(self):
        data = json.loads(byg_qr_payload("http://192.168.1.20:8765", "abc", {"navn": "ISM589"},
                                         "Hjemme", "kode123"))
        self.assertEqual(data[E + "PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"], KOMPONENT)
        self.assertEqual(data[E + "PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"],
                         "http://192.168.1.20:8765/inbase-klargoering.apk")
        self.assertEqual(data[E + "PROVISIONING_WIFI_PASSWORD"], "kode123")
        self.assertEqual(data[E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE"], {"navn": "ISM589"})
        self.assertNotIn(E + "PROVISIONING_WIFI_SSID", json.loads(byg_qr_payload("http://x", "a", {})))

    def test_kontrolsum_er_base64url_uden_padding(self):
        fil = Path(__file__)
        self.assertRegex(apk_kontrolsum(fil), r"^[A-Za-z0-9_-]{43}$")


class ServerTest(unittest.TestCase):
    def test_apk_hentes_og_kun_rigtig_token_kan_melde_tilbage(self):
        modtaget = []
        server = KlargoeringsServer(Path(__file__), "hemmelig", modtaget.append, port=0,
                                    vaert="127.0.0.1", fl_update=MIGRERING_008)
        url = server.start()
        try:
            with urllib.request.urlopen(url + "/inbase-klargoering.apk", timeout=5) as svar:
                self.assertEqual(svar.read(), Path(__file__).read_bytes())
            with urllib.request.urlopen(url + "/fl-update.apk", timeout=5) as svar:
                self.assertEqual(svar.read(), MIGRERING_008.read_bytes())

            def post(token):
                anm = urllib.request.Request(url + "/api/klargjort", data=b'{"enhed_id": "x"}',
                                             headers={"X-Inbase-Token": token}, method="POST")
                return urllib.request.urlopen(anm, timeout=5).status

            with self.assertRaises(urllib.error.HTTPError):
                post("forkert")
            self.assertEqual(modtaget, [])
            self.assertEqual(post("hemmelig"), 200)
            self.assertEqual(modtaget, [{"enhed_id": "x"}])
        finally:
            server.stop()


class MdmServiceTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.lokal = JsonLokalFil(self.lokal / "mdm.json")
        self.s = MdmService(self.t.mdm.repo, self.lokal, session.bruger)

    def test_enhedsnavn_normaliseres_valideres_og_er_unikt(self):
        self.assertEqual(self.s.opret({"navn": " ism589 "}).navn, "ISM589")
        for data in ({"navn": ""}, {"navn": "ISM 1"}, {"navn": "Ole Hansen"}, {"navn": "ism589"},
                     {"navn": "ISM2", "telefonnummer": "12ab"}):
            with self.subTest(data), self.assertRaises(ValideringsFejl):
                self.s.opret(data)
        session.log_ind({"brugernavn": "HAFRA", "navn": "H", "rolle": "Bruger"})
        with self.assertRaises(ValideringsFejl):
            self.s.opret({"navn": "ISM3"})

    def test_mail_kan_slaas_til_og_fra_efter_klargoering(self):
        enhed = self.s.opret({"navn": "ISM589"})
        self.assertFalse(enhed.mail)
        self.assertTrue(self.s.saet_mail(enhed, True).mail)
        self.assertTrue(self.s.hent_alle()[0].mail)
        self.s.saet_mail(enhed, False)
        self.assertFalse(self.s.hent_alle()[0].mail)
        session.log_ind({"brugernavn": "HAFRA", "navn": "H", "rolle": "Bruger"})
        with self.assertRaises(ValideringsFejl):
            self.s.saet_mail(enhed, True)

    @unittest.skipUnless(Path("assets/mdm/inbase-klargoering.apk").is_file(), "APK ikke bygget")
    def test_klargoering_husker_indstillinger_og_registrerer_rapport(self):
        enhed = self.s.opret({"navn": "ISM589"})
        # Fejl i FL-UPDATE/ekstra apps stopper ikke QR-koden – de bliver til advarsler.
        uden = self.s.ny_klargoering(enhed, {"wifi_ssid": "Hjemme", "ekstra_apps": "Foto"})
        self.assertEqual(len(uden.advarsler), 2)
        ekstra = json.loads(uden.qr_tekst("http://pc:8765"))[E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE"]
        self.assertEqual((ekstra["fl_update_url"], ekstra["tilladte"]), ("", ""))
        fil = self.central / "FL-UPDATE.apk"
        fil.write_bytes(APK_DATA)
        k = self.s.ny_klargoering(enhed, {"wifi_ssid": "Hjemme", "wifi_kode": "hemmelig",
                                          "fl_kilde": "fil", "fl_fil": str(fil), "mail": True})
        self.assertEqual((k.fl_update_fil, k.advarsler), (fil, []))
        # Link: IN-BASE henter selv filen og afviser alt, der ikke er en APK (fx en forside).
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"<html>forside")):
            forside = self.s.ny_klargoering(enhed, {"fl_kilde": "link",
                                                    "fl_link": "https://mx.fl-it.net"})
        self.assertIsNone(forside.fl_update_fil)
        self.assertIn("ikke en APK", forside.advarsler[0])
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(APK_DATA)),                 mock.patch("app.infrastructure.stier.LOKAL_MAPPE", self.central):
            link = self.s.ny_klargoering(enhed, {"wifi_ssid": "Hjemme", "fl_kilde": "link",
                                                 "fl_link": "https://mx.fl-it.net/FL-UPDATE.apk"})
        self.assertEqual(link.fl_update_fil.read_bytes(), APK_DATA, "pc'en serverer den hentede fil")
        ekstra = json.loads(k.qr_tekst("http://pc:8765"))[E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE"]
        self.assertEqual((ekstra["fl_update_url"], ekstra["mail"]),
                         ("http://pc:8765/fl-update.apk", "1"), "filen serveres fra pc'en")
        self.assertEqual((ekstra["navn"], ekstra["enhed_id"], ekstra["token"]),
                         ("ISM589", enhed.id, k.token))
        self.assertEqual(ekstra["tilladte"], "", "standardlisten ligger i styrings-appen")
        husket = self.s.huskede_indstillinger()
        self.assertEqual((husket["wifi_ssid"], husket["wifi_kode"]), ("FLFL", "frodefrode"),
                         "Wi-Fi forudfyldes altid med standarden")
        self.assertTrue(husket["baggrund"].endswith("INSTORE_LOCK.png"))
        self.assertIn("+45 8764 6576", husket["kontakt"])
        self.assertNotIn("hemmelig", json.dumps(self.lokal.hent()), "Wi-Fi-koden huskes ikke")

        with self.assertRaises(ValideringsFejl):
            self.s.registrer_klargjort(k, {"enhed_id": "en-anden"})
        self.s.registrer_klargjort(k, {"enhed_id": enhed.id, "producent": "motorola",
                                       "model": "moto g54", "serienummer": "ZY22", "imei": "35"})
        gemt = self.s.hent_alle()[0]
        self.assertEqual((gemt.status, gemt.model, gemt.serienummer), (md.KLARGJORT, "moto g54", "ZY22"))
        self.assertTrue(gemt.klargjort)
        self.assertEqual(gemt.nulstillingskode, k.nulstillingskode)
        self.assertTrue(gemt.mail, "mail-valget fra klargøringen gemmes")
        self.assertRegex(k.nulstillingskode, r"^\d{8}$")
        # Skal give samme kode som AdminActivity.supportkode på telefonen.
        self.assertEqual(md.supportkode("12345678"), "483606")
        self.assertNotEqual(md.supportkode(k.nulstillingskode), k.nulstillingskode[:6])
        self.assertEqual(ekstra["nulstillingskode"], k.nulstillingskode)


class AendringskodeTest(unittest.TestCase):
    def test_koder_pr_handling_og_supportkoden_er_uaendret(self):
        # Samme værdi som før ændringskoderne – telefoner med v3 bruger den stadig.
        self.assertEqual(md.supportkode("12345678"), "483606")
        self.assertEqual(md.aendringskode("12345678", md.CHROME), "483606")
        koder = {md.aendringskode("12345678", h) for h in (md.CHROME, md.MAIL_TIL, md.MAIL_FRA)}
        self.assertEqual(len(koder), 3)
        self.assertNotEqual(md.aendringskode("87654321", md.MAIL_TIL),
                            md.aendringskode("12345678", md.MAIL_TIL), "koden gælder én telefon")
        self.assertEqual(md.aendringskode("", md.MAIL_TIL), "")


class DomaeneOgDatabaseStemmerOverensTest(unittest.TestCase):
    """Statusser (008) og gemte felter (012) står i domænet OG i migreringerne."""

    def test_statusser_og_felter(self):
        from app.repositories.supabase.mapping import MDM_FELTER
        sql = MIGRERING_008.read_text(encoding="utf-8")
        for status in md.STATUSSER:
            self.assertIn(f"'{status}'", sql)
        sql_012 = MIGRERING_012.read_text(encoding="utf-8")
        tilladte = set(re.findall(r"'([a-z_]+)'", sql_012.split("if v_key not in (")[1].split(")")[0]))
        kolonner = {k for n, k, _ in MDM_FELTER if n in md.GEMTE_FELTER}
        self.assertEqual(kolonner, tilladte - {"id"})


if __name__ == "__main__":
    unittest.main()
