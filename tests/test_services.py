"""Forretningsregler i services: arbejdsgange, Action Center, rapporter, auth m.m."""
import unittest
from datetime import date, timedelta

from app.bootstrap import byg_tjenester
from app.domain import skabelon as sk
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.domain.rykker import Rykker
from app.repositories.fejl import ValideringsFejl
from app.services import action_center
from app.services.rapport_service import Filter
from tests.hjaelp import TjenesteTest, dato


class OffboardingServiceTest(TjenesteTest):
    def test_opret_fra_skabelon_registrerer_skabelonversion(self):
        sag = self.ny_offboarding()
        self.assertEqual(len(sag.opgaver), 5)
        self.assertEqual(sag.skabelon["version"], 1)
        self.assertEqual(sag.historik.haendelser()[0]["data"]["type"], "oprettet")

    def test_statusskift_logges_struktureret(self):
        sag = self.ny_offboarding()
        sag = self.t.offboarding.marker_opgave_udfoert(sag, sag.opgaver[1].id)
        skift = sag.historik.af_type("status")
        self.assertEqual((skift[-1]["data"]["fra"], skift[-1]["data"]["til"]),
                         ("Afventer Udstyr", "Delvist afleveret"))

    def test_manuel_status_kraever_begrundelse(self):
        sag = self.ny_offboarding()
        with self.assertRaises(ValideringsFejl):
            self.t.offboarding.saet_manuel_status(sag, "Afviklet", "")
        sag = self.t.offboarding.saet_manuel_status(sag, "Afviklet", "Aftalt med HR")
        self.assertEqual(sag.status, "Afviklet")

    def test_loennr_skal_vaere_unikt(self):
        self.ny_offboarding(loennr="77")
        with self.assertRaises(ValideringsFejl):
            self.ny_offboarding(loennr="77")

    def test_rykker_registreres_og_markeres_sendt(self):
        sag = self.ny_offboarding()
        sag = self.t.offboarding.registrer_rykker(sag, Rykker("x", "Første påmindelse", "e", dato(7)))
        sag = self.t.offboarding.marker_rykker_sendt(sag, sag.rykkere[0].id)
        self.assertTrue(sag.rykkere[0].sendt)
        mail = self.t.skabeloner.relevant_mailskabelon(sag)
        self.assertEqual(mail["kategori"], "Anden rykker")


class OnboardingServiceTest(TjenesteTest):
    def test_kandidat_uden_loennr_og_fm_skabelon(self):
        f = self.ny_onboarding(stilling="FM")
        self.assertEqual(f.loennr, "")
        self.assertEqual(f.status, OB.STATUS_KANDIDAT)
        self.assertIn("Introduktion til ledelsesopgaver", [o.navn for o in f.opgaver])

    def test_laast_opgave_kan_ikke_markeres_udfoert(self):
        f = self.ny_onboarding()
        laast = next(o for o in f.opgaver if o.milepael == "jobs")
        with self.assertRaises(ValideringsFejl):
            self.t.onboarding.marker_opgave_udfoert(f, laast.id)

    def test_milepaele_driver_status(self):
        f = self.ny_onboarding()
        for milepael in ("kandidat", "kontrakt"):
            for o in [o for o in f.opgaver if o.milepael == milepael]:
                f = self.t.onboarding.marker_opgave_udfoert(f, o.id)
        self.assertEqual(f.status, OB.STATUS_OPLAERING)

    def test_kritisk_overstyring_kraever_begrundelse_og_logges(self):
        f = self.ny_onboarding()
        with self.assertRaises(ValideringsFejl):
            self.t.onboarding.saet_manuel_status(f, OB.STATUS_AKTIV, "")
        f = self.t.onboarding.saet_manuel_status(f, OB.STATUS_AKTIV, "Startede akut")
        overstyring = f.historik.af_type("overstyring")[0]
        self.assertIn("Kandidat godkendt", overstyring["data"]["mangler"])
        self.assertEqual(f.status, OB.STATUS_AKTIV)

    def test_annullering_arkiverer(self):
        f = self.ny_onboarding()
        with self.assertRaises(ValideringsFejl):
            self.t.onboarding.annuller(f, "")
        self.t.onboarding.annuller(f, "Takkede nej")
        self.assertEqual(self.t.onboarding.hent_aktive(), [])
        self.assertEqual(self.t.onboarding.hent_arkiverede()[0].status, OB.STATUS_ANNULLERET)


class ActionCenterTest(TjenesteTest):
    def test_alarmer_paa_tvaers_af_moduler(self):
        self.ny_offboarding(dage=-10)                     # opgaver over frist
        f = self.ny_onboarding()
        f = self.t.onboarding.tildel_ansvarlig(f, "tester")
        alarmer = action_center.action_center(
            self.t.offboarding.hent_aktive() + self.t.onboarding.hent_aktive(), date.today())
        self.assertEqual(alarmer[0].niveau, action_center.KRITISK)
        self.assertEqual({a.modul for a in alarmer}, {"offboarding", "onboarding"})
        self.assertTrue(all(a.sag_id for a in alarmer))

    def test_stillestaaende_og_klar_til_afslutning(self):
        sag = self.ny_offboarding(dage=5)
        gammel = (date.today() - timedelta(days=30)).isoformat() + "T08:00:00"
        sag.historik._haendelser[-1]["tid"] = gammel
        typer = {a.badge for a in action_center.action_center([sag], date.today())}
        self.assertIn("Stillestående", typer)
        for o in sag.opgaver:
            o.saet_status(Opgave.UDFOERT)
        typer = {a.badge for a in action_center.action_center([sag], date.today())}
        self.assertIn("Afslut", typer)

    def test_samme_haendelse_giver_ikke_dubletter(self):
        sag = self.ny_offboarding()
        a1 = action_center.action_center([sag], date.today())
        a2 = action_center.action_center([sag], date.today())
        self.assertEqual(len(a1), len(a2))


class PaamindelseTest(TjenesteTest):
    def test_vises_kun_en_gang_pr_dag_ogsaa_efter_genstart(self):
        self.ny_offboarding(dage=-10)
        skabeloner = [s for s in self.t.skabeloner.aktive(sk.PAAMINDELSE)
                      if s["regel"] == "opgave_forsinket"]
        sager = self.t.offboarding.hent_aktive()
        foerste = self.t.paamindelser.nye_paamindelser(skabeloner, sager, date.today())
        self.assertEqual(len(foerste), 1)
        genstartet = byg_tjenester(self.central, self.lokal)
        self.assertEqual(genstartet.paamindelser.nye_paamindelser(skabeloner, sager, date.today()), [])
        i_morgen = date.today() + timedelta(days=1)
        self.assertEqual(len(genstartet.paamindelser.nye_paamindelser(skabeloner, sager, i_morgen)), 1)


class RapportTest(TjenesteTest):
    def test_maalinger_har_n_og_mangler_data_aerligt(self):
        f = self.ny_onboarding(stilling="DM")
        rapport = self.t.rapporter.beregn([f], Filter(), date.today())
        maal = {m.navn: m for m in rapport.maalinger}
        self.assertIsNone(maal["Kandidat → kontrakt bekræftet"].vaerdi)
        self.assertEqual(maal["Åbne forløb"].vaerdi, "1")
        for milepael in ("kandidat", "kontrakt"):
            for o in [o for o in f.opgaver if o.milepael == milepael]:
                f = self.t.onboarding.marker_opgave_udfoert(f, o.id)
        rapport = self.t.rapporter.beregn([f], Filter(stilling="DM"), date.today())
        maal = {m.navn: m for m in rapport.maalinger}
        self.assertEqual(maal["Kandidat → kontrakt bekræftet"].n, 1)
        self.assertEqual(self.t.rapporter.beregn([f], Filter(stilling="FM"), date.today())
                         .maalinger[-3].vaerdi, "0")


class AuthTest(TjenesteTest):
    def test_log_ind_og_skift_egen_kode(self):
        self.assertIsNotNone(self.t.auth.log_ind("admin", "admin"))
        with self.assertRaises(ValideringsFejl):
            self.t.auth.skift_egen_kode("admin", "forkert", "nykode1", "nykode1")
        with self.assertRaises(ValideringsFejl):
            self.t.auth.skift_egen_kode("admin", "admin", "kort", "kort")
        with self.assertRaises(ValideringsFejl):
            self.t.auth.skift_egen_kode("admin", "admin", "nykode1", "nykode2")
        self.t.auth.skift_egen_kode("admin", "admin", "nykode1", "nykode1")
        self.assertIsNone(self.t.auth.log_ind("admin", "admin"))
        self.assertIsNotNone(self.t.auth.log_ind("admin", "nykode1"))
        tekst = (self.central / "brugere.json").read_text("utf-8")
        self.assertNotIn("nykode1", tekst)

    def test_sidste_administrator_kan_ikke_slettes(self):
        self.t.auth.opret("lise", "Lise", "Bruger", "hemmelig")
        with self.assertRaises(ValideringsFejl):
            self.t.auth.slet("admin", "lise")


class SkabelonVersionTest(TjenesteTest):
    def test_aendring_giver_ny_version_og_paavirker_ikke_igangvaerende(self):
        sag = self.ny_offboarding()
        skab = next(s for s in self.t.skabeloner.sagsskabeloner("offboarding")
                    if s["navn"] == "Standard")
        skab["opgaver"] = skab["opgaver"] + [{"navn": "Ny opgave", "frist_dage": 1}]
        gemt = self.t.skabeloner.gem(sk.SAG, skab)
        self.assertEqual(gemt["version"], 2)
        self.assertEqual(gemt["versioner"][-1]["version"], 1)
        self.assertEqual(len(self.t.offboarding.hent(sag.id).opgaver), 5)


class BackupTest(TjenesteTest):
    def test_ny_installation_uden_sager_kan_tage_backup(self):
        info = self.t.backup.daglig_backup()
        self.assertTrue(self.t.backup.test_backup(info.sti)[0])

    def test_backup_test_og_gendan(self):
        self.ny_offboarding()
        self.ny_onboarding()
        info = self.t.backup.tag_backup("test")
        ok, besked = self.t.backup.test_backup(info.sti)
        self.assertTrue(ok, besked)
        self.t.offboarding.slet(self.t.offboarding.hent_aktive()[0])
        self.t.backup.gendan(info.sti)
        self.assertEqual(len(self.t.offboarding.hent_aktive()), 1)
        (info.sti / "medarbejdere.json").write_text("[]", "utf-8")
        self.assertFalse(self.t.backup.test_backup(info.sti)[0])


if __name__ == "__main__":
    unittest.main()
