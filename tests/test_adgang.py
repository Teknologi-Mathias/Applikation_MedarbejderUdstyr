"""Moduladgang: regler (domæne), lagring (JSON) og låsen i hovedvinduet."""
import os
import unittest
from pathlib import Path

from app import session
from app.domain import adgang
from tests.hjaelp import TjenesteTest

MIGRERING_010 = (Path(__file__).resolve().parents[1]
                 / "app/infrastructure/database/migrations/010_moduladgang.sql")


class ReglerTest(unittest.TestCase):
    def test_standard_admin_og_valgte(self):
        bruger = {"rolle": "Bruger", "moduler": None}
        self.assertEqual(adgang.moduler_for(bruger), adgang.STANDARD, "som før: alt undtagen MDM")
        self.assertFalse(adgang.har_adgang(bruger, adgang.TELEFONER))
        self.assertTrue(adgang.har_adgang(bruger, None), "dashboard/indstillinger er altid åbne")
        self.assertEqual(adgang.moduler_for({"rolle": "Administrator", "moduler": []}),
                         tuple(adgang.MODULER))
        valgt = {"rolle": "Bruger", "moduler": ["telefoner"]}
        self.assertEqual(adgang.moduler_for(valgt), (adgang.TELEFONER,))
        self.assertEqual(adgang.modul_for_side("on_skabeloner"), adgang.ONBOARDING)
        self.assertIsNone(adgang.modul_for_side("dashboard"))

    def test_modulnavne_stemmer_med_migrering_010(self):
        sql = MIGRERING_010.read_text(encoding="utf-8")
        for modul in adgang.MODULER:
            self.assertIn(f"'{modul}'", sql)


class LagringTest(TjenesteTest):
    def test_administrator_saetter_moduler_og_de_foelger_login(self):
        self.t.auth.opret("HAFRA", "Hanne", "Bruger", "kode-12345")
        self.t.auth.saet_moduler("HAFRA", ["telefoner", "ukendt", "oensker"])
        bruger = self.t.auth.log_ind("HAFRA", "kode-12345")
        self.assertEqual(bruger["moduler"], ["oensker", "telefoner"], "kendte moduler, fast orden")
        session.log_ind(bruger)
        self.assertTrue(session.har_adgang(adgang.TELEFONER))
        self.assertFalse(session.har_adgang(adgang.ONBOARDING))


class HovedvindueTest(TjenesteTest):
    def test_laast_modul_vises_med_haengelaas_og_laast_side(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from app.ui.hovedvindue import LAAS, MainWindow
        self.t.auth.opret("HAFRA", "Hanne", "Bruger", "kode-12345")
        self.t.auth.saet_moduler("HAFRA", ["oensker"])
        session.log_ind(self.t.auth.log_ind("HAFRA", "kode-12345"))
        vindue = MainWindow(self.t)
        try:
            vindue.efter_log_paa()
            self.assertTrue(vindue.sidebar.knapper["on_aktive"].text().endswith(LAAS))
            self.assertFalse(vindue.sidebar.knapper["oensker"].text().endswith(LAAS))
            vindue.vis_side("on_aktive")
            self.assertIs(vindue.stak.currentWidget(), vindue.laast_side)
            self.assertEqual(vindue.data["onboarding"], ([], []), "låste moduler hentes ikke")
            vindue.vis_side("oensker")
            self.assertIs(vindue.stak.currentWidget(), vindue.oensker)
        finally:
            vindue.timer.stop()
            vindue.notifikationer.tray.hide()
            vindue.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
