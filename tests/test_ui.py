"""Røgtest af brugerfladen (offscreen): vinduet bygges, alle sider vises,
dialoger åbnes, tema skiftes og centrale handlinger virker via controllerne."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from app import session  # noqa: E402
from app.domain.onboarding import OnboardingForloeb as OB  # noqa: E402
from app.ui import action_liste as al  # noqa: E402
from app.ui.hovedvindue import STRUKTUR, MainWindow  # noqa: E402
from app.ui.onboarding_dialog import OnboardingDialog  # noqa: E402
from app.ui.sag_dialog import SagDialog  # noqa: E402
from app.ui.theme import FARVER, anvend_tema  # noqa: E402
from tests.hjaelp import TjenesteTest  # noqa: E402

_app = QApplication.instance() or QApplication([])


class UiTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self._gemt = (QMessageBox.question, QMessageBox.warning, QMessageBox.information,
                      QMessageBox.critical, QInputDialog.getItem)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.critical = staticmethod(lambda *a, **k: self.fail(f"Fejlboks: {a[2]}"))
        QInputDialog.getItem = staticmethod(lambda *a, **k: ("tester", True))
        self.off = self.ny_offboarding(dage=-10)
        self.on = self.ny_onboarding()
        session.log_ind(self.t.auth.log_ind("admin", "admin"))
        self.vindue = MainWindow(self.t)
        self.vindue.efter_log_paa()

    def tearDown(self):
        (QMessageBox.question, QMessageBox.warning, QMessageBox.information,
         QMessageBox.critical, QInputDialog.getItem) = self._gemt
        self.vindue.timer.stop()
        self.vindue.notifikationer.tray.hide()
        self.vindue.deleteLater()
        # Slet vinduet nu – ellers styler hvert temaskift alle tidligere testvinduer.
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _app.processEvents()
        anvend_tema(_app, "lilla")
        super().tearDown()

    def test_alle_sider_kan_vises(self):
        for _, punkter in STRUKTUR:
            for noegle, _ in punkter:
                self.vindue.vis_side(noegle)
                _app.processEvents()
        self.assertEqual(self.vindue.sider["on_aktive"].tabel.rowCount(), 1)
        self.assertEqual(self.vindue.sider["off_aktive"].tabel.rowCount(), 1)
        self.assertGreater(self.vindue.dashboard.action.liste.count(), 0)

    def test_onboarding_og_offboarding_er_separate_hovedpunkter(self):
        sektioner = [s for s, _ in STRUKTUR if s]
        self.assertEqual(sektioner, ["Onboarding", "Offboarding"])

    def test_sagsvindue_viser_milepaele_og_laaste_opgaver(self):
        dialog = SagDialog(self.vindue, self.on, ["tester"])
        dialog.show()
        _app.processEvents()
        raekker = [dialog.raekke_layout.itemAt(i).widget()
                   for i in range(dialog.raekke_layout.count())]
        laaste = [r for r in raekker if getattr(r, "laast", False)]
        self.assertTrue(laaste)
        self.assertFalse(laaste[0].status_input.isEnabled())
        dialog.close()

    def test_action_center_handling_markerer_opgave_udfoert(self):
        opgave = self.off.aabne_opgaver()[0]
        self.vindue.ctrl["offboarding"].action_handling(al.UDFOERT, self.off.id, opgave.id)
        sag = self.t.offboarding.hent(self.off.id)
        self.assertTrue(sag.find_opgave(opgave.id).afsluttet)

    def test_tildel_ansvarlig_fra_action_center(self):
        self.vindue.ctrl["onboarding"].action_handling(al.ANSVARLIG, self.on.id, "")
        self.assertEqual(self.t.onboarding.hent(self.on.id).ansvarlig, "tester")

    def test_temaskift(self):
        lilla = FARVER["bg"]
        self.vindue.skift_tema("lys")
        self.assertNotEqual(FARVER["bg"], lilla)
        self.vindue.skift_tema("lilla")
        self.assertEqual(FARVER["bg"], lilla)

    def test_offline_skift_fra_indstillinger(self):
        panel = self.vindue.indstillinger.generelt
        panel._skift_lagring()
        self.assertTrue(self.t.datakilde.offline)
        self.assertIn("OFFLINE", self.vindue.sidebar.lagring_label.text())
        panel._skift_lagring()
        self.assertFalse(self.t.datakilde.offline)

    def test_bruger_rolle_skjuler_admin_funktioner(self):
        self.t.auth.opret("lise", "Lise", "Bruger", "hemmelig")
        session.log_ind(self.t.auth.log_ind("lise", "hemmelig"))
        self.vindue.anvend_rolle()
        self.assertTrue(self.vindue.on_slet.isHidden())
        self.assertFalse(self.vindue.sider["on_skabeloner"].redigerbar)

    def test_onboardingdialog_filtrerer_skabeloner_efter_stilling(self):
        skabeloner = self.t.skabeloner.sagsskabeloner(OB.PROCES)
        dialog = OnboardingDialog(self.vindue, None, skabeloner, ["Nord"], ["tester"])
        dialog.stilling_input.setCurrentText("FM")
        self.assertIn("FM/DM", dialog.skabelon_input.itemText(0))
        dialog.stilling_input.setCurrentText("Ad Hoc")
        self.assertIn("standard", dialog.skabelon_input.itemText(0))


if __name__ == "__main__":
    unittest.main()
