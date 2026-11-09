"""Telefoner (MDM): QR-kode, lokal klargøringsserver og MdmService (JSON-lagring)."""
import csv
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
MIGRERING_025 = MIGRERINGER / "025_mdm_laas_op.sql"
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
                                    vaert="127.0.0.1", fl_update=MIGRERING_008,
                                    ekstra_apk=[MIGRERING_025])
        url = server.start()
        try:
            with urllib.request.urlopen(url + "/inbase-klargoering.apk", timeout=5) as svar:
                self.assertEqual(svar.read(), Path(__file__).read_bytes())
            with urllib.request.urlopen(url + "/fl-update.apk", timeout=5) as svar:
                self.assertEqual(svar.read(), MIGRERING_008.read_bytes())
            with urllib.request.urlopen(url + "/ekstra-1.apk", timeout=5) as svar:
                self.assertEqual(svar.read(), MIGRERING_025.read_bytes())
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + "/ekstra-2.apk", timeout=5)

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

    def test_fjernet_telefon_arkiveres_med_koden_og_kan_gendannes_og_eksporteres(self):
        enhed = self.s.opret({"navn": "ISM589"})
        self.s.repo.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        self.s.arkiver(enhed)
        self.assertEqual(self.s.hent_alle(), [])
        arkiveret = self.s.hent_arkiverede()[0]
        self.assertEqual(arkiveret.nulstillingskode, "01234567", "koden bevares")
        with self.assertRaisesRegex(ValideringsFejl, "Arkiv"):
            self.s.opret({"navn": "ISM589"})
        sti = self.central / "telefoner.csv"
        self.assertEqual(self.s.eksporter_csv(sti), 1)
        raekke = list(csv.reader(sti.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))[1]
        self.assertEqual(raekke[0], "ISM589")
        self.assertIn('="01234567"', raekke, "Excel må ikke fjerne foranstillede nuller")
        self.assertIn(f'="{md.supportkode("01234567")}"', raekke)
        self.s.gendan(enhed)
        self.assertEqual([e.navn for e in self.s.hent_alle()], ["ISM589"])
        with self.assertRaises(ValideringsFejl, msg="kun arkiverede kan slettes"):
            self.s.slet(self.s.hent_alle()[0])

    def test_find_telefon_anmodes_og_kan_annulleres(self):
        enhed = self.s.opret({"navn": "ISM589"})
        with self.assertRaisesRegex(ValideringsFejl, "ikke klargjort"):
            self.s.find_telefon(enhed)
        self.s.repo.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        enhed = self.s.hent(enhed)
        self.assertTrue(self.s.find_telefon(enhed).find_anmodet)
        self.assertTrue(self.s.hent(enhed).find_anmodet)
        self.s.annuller_find(enhed)
        self.assertEqual(self.s.hent(enhed).find_anmodet, "")
        session.log_ind({"brugernavn": "HAFRA", "navn": "H", "rolle": "Bruger"})
        with self.assertRaises(ValideringsFejl):
            self.s.find_telefon(enhed)

    def test_laas_op_anmodes_og_kan_annulleres(self):
        enhed = self.s.opret({"navn": "ISM589"})
        with self.assertRaisesRegex(ValideringsFejl, "nulstillingskode"):
            self.s.laas_op(enhed)
        self.s.repo.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        enhed = self.s.hent(enhed)
        self.assertTrue(self.s.laas_op(enhed).laas_op_anmodet)
        self.assertTrue(self.s.hent(enhed).laas_op_anmodet)
        self.assertEqual(self.s.hent(enhed).find_anmodet, "", "uafhængig af Find telefon")
        self.s.annuller_laas_op(enhed)
        self.assertEqual(self.s.hent(enhed).laas_op_anmodet, "")

    def test_appens_version_laeses_fra_byggets_metadata(self):
        fil = self.central / "inbase-klargoering.json"
        fil.write_text(json.dumps({"elements": [{"versionCode": 8, "versionName": "8.0"}]}),
                       encoding="utf-8")
        with mock.patch("app.services.mdm_service.APP_VERSION", fil):
            self.assertEqual(self.s.app_paa_pc(), {"version_kode": 8, "version": "8.0"})
        with mock.patch("app.services.mdm_service.APP_VERSION", fil.with_name("findes-ikke.json")):
            self.assertEqual(self.s.app_paa_pc(), {})
        self.assertEqual(self.s.app_udgivet(), {}, "JSON-lagring: intet udgivet")

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


    @unittest.skipUnless(Path("assets/mdm/inbase-klargoering.apk").is_file(), "APK ikke bygget")
    def test_ekstra_apk_valideres_huskes_og_kun_antallet_er_i_qr_koden(self):
        enhed = self.s.opret({"navn": "ISM589"})
        apps = [self.central / "a.apk", self.central / "b.apk"]
        for fil in apps:
            fil.write_bytes(APK_DATA)
        ikke_apk = self.central / "tekst.apk"
        ikke_apk.write_bytes(b"hej")
        k = self.s.ny_klargoering(enhed, {"ekstra_apk": "\n".join(
            [str(apps[0]), str(apps[1]), str(apps[0]), str(ikke_apk), "C:/findes/ikke.apk"])})
        self.assertEqual(k.ekstra_apk, apps, "dubletter og fejl springes over")
        self.assertEqual(len(k.advarsler), 3, "ikke-APK, manglende fil og FL-UPDATE")
        ekstra = json.loads(k.qr_tekst("http://pc:8765"))[E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE"]
        self.assertEqual(ekstra["ekstra_apk"], "2")
        self.assertEqual(self.s.huskede_indstillinger()["ekstra_apk"].splitlines(),
                         [str(f) for f in apps])
        uden = self.s.ny_klargoering(enhed, {})
        ekstra = json.loads(uden.qr_tekst("http://pc:8765"))[E + "PROVISIONING_ADMIN_EXTRAS_BUNDLE"]
        self.assertNotIn("ekstra_apk", ekstra)


class AendringskodeTest(unittest.TestCase):
    def test_koder_pr_handling_og_supportkoden_er_uaendret(self):
        # Samme værdi som før ændringskoderne – telefoner med v3 bruger den stadig.
        self.assertEqual(md.supportkode("12345678"), "483606")
        self.assertEqual(md.aendringskode("12345678", md.CHROME), "483606")
        koder = {md.aendringskode("12345678", h)
                 for h in (md.CHROME, md.MAIL_TIL, md.MAIL_FRA, md.SKAERMLAAS)}
        self.assertEqual(len(koder), 4)
        self.assertNotEqual(md.aendringskode("87654321", md.MAIL_TIL),
                            md.aendringskode("12345678", md.MAIL_TIL), "koden gælder én telefon")
        self.assertEqual(md.aendringskode("", md.MAIL_TIL), "")


class SporingTest(unittest.TestCase):
    def test_noegle_og_kortlink(self):
        # Samme testvektor som Sporing.noegle på telefonen og sha256 i migrering 024.
        self.assertEqual(md.sporingsnoegle("12345678"),
                         "6e5f471a19d0bd2dac8f96c75a6411fc47c2e1398ff86252bb452991ef59de02")
        self.assertEqual(md.sporingsnoegle(""), "")
        self.assertEqual(md.kortlink({"lat": 55.86, "lng": 9.84}), "https://maps.google.com/?q=55.86,9.84")
        self.assertEqual(md.kortlink({"fejl": "Ingen GPS"}), "")

    def test_position_fra_databasen_faar_lokal_tid(self):
        from app.repositories.supabase.mapping import mdm_fra_raekke
        enhed = mdm_fra_raekke({"name": "ISM589", "location": {
            "lat": 55.86, "lng": 9.84, "modtaget": "2026-11-04T13:32:10+00:00"}})
        self.assertEqual(enhed.position["lat"], 55.86)
        self.assertNotIn("+", enhed.position["modtaget"])
        self.assertEqual(mdm_fra_raekke({"name": "ISM589"}).position, {})


class DomaeneOgDatabaseStemmerOverensTest(unittest.TestCase):
    """Statusser (008) og gemte felter (025) står i domænet OG i migreringerne."""

    def test_statusser_og_felter(self):
        from app.repositories.supabase.mapping import MDM_FELTER
        sql = MIGRERING_008.read_text(encoding="utf-8")
        for status in md.STATUSSER:
            self.assertIn(f"'{status}'", sql)
        sql_025 = MIGRERING_025.read_text(encoding="utf-8")
        tilladte = set(re.findall(r"'([a-z_]+)'", sql_025.split("if v_key not in (")[1].split(")")[0]))
        kolonner = {k for n, k, _ in MDM_FELTER if n in md.GEMTE_FELTER}
        self.assertEqual(kolonner, tilladte - {"id"})


if __name__ == "__main__":
    unittest.main()
