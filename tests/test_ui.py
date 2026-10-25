"""Røgtest af brugerfladen (offscreen): vinduet bygges, alle sider vises,
dialoger åbnes, tema skiftes og centrale handlinger virker via controllerne."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from unittest import mock  # noqa: E402

from app import session  # noqa: E402
from app.domain import indmelding as im  # noqa: E402
from app.domain.onboarding import OnboardingForloeb as OB  # noqa: E402
from app.repositories.fejl import SessionUdloebetFejl  # noqa: E402
from app.ui import action_liste as al  # noqa: E402
from app.ui.hovedvindue import STRUKTUR, MainWindow  # noqa: E402
from app.ui.indmelding_dialog import IndmeldingDialog, NyIndmeldingDialog  # noqa: E402
from app.ui.onboarding_dialog import OnboardingDialog  # noqa: E402
from app.ui.sag_dialog import SagDialog  # noqa: E402
from app.ui.theme import FARVER, anvend_tema  # noqa: E402
from tests.hjaelp import ADMIN, ADMIN_KODE, TjenesteTest  # noqa: E402

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
        session.log_ind(self.t.auth.log_ind(ADMIN, ADMIN_KODE))
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
        self.assertEqual(len(sektioner), 2)
        self.assertTrue(sektioner[0].startswith("Onboarding"))
        self.assertTrue(sektioner[1].startswith("Offboarding"))

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
        # Skabeloner og Organisation er åbne; Brugere og Data & sikkerhed er kun for admin.
        self.assertTrue(self.vindue.sider["on_skabeloner"].redigerbar)
        ind = self.vindue.indstillinger
        synlige = {navn for i, (_, navn, _, _) in enumerate(ind._paneler)
                   if ind.faner.isTabVisible(i)}
        self.assertEqual(synlige, {"Generelt", "Påmindelser", "Organisation"})

    def ny_indmelding(self, titel="Eksport fejler"):
        return self.t.indmeldinger.opret({"titel": titel, "kategori": "Fejlmelding",
                                          "beskrivelse": "Excel-eksporten giver en fejlbesked"})

    def test_oensker_er_selvstaendigt_menupunkt_med_soegning_og_filtre(self):
        self.assertIn(("oensker", "Ønsker & Udvikling"),
                      [p for sektion, punkter in STRUKTUR if sektion is None for p in punkter])
        self.ny_indmelding()
        self.ny_indmelding("Automatisk rykker")
        self.vindue.vis_side("oensker")
        side = self.vindue.oensker
        self.assertEqual(side.tabel.rowCount(), 2)
        synlige = lambda: [r for r in range(side.tabel.rowCount()) if not side.tabel.isRowHidden(r)]
        side.soegefelt.setText("excel-eksporten")      # står kun i beskrivelsen
        self.assertEqual(len(synlige()), 2)
        side.soegefelt.setText("rykker")
        self.assertEqual(len(synlige()), 1)
        side.soegefelt.clear()
        status_filter = side.filter_felter[1]
        status_filter.setCurrentText(im.UDGIVET)
        self.assertEqual(synlige(), [])
        status_filter.setCurrentIndex(0)
        visning = side.filter_felter[0]
        visning.setCurrentText("Mine indmeldinger")
        self.assertEqual(len(synlige()), 2)

    def test_ny_indmelding_dialog_validerer_og_opretter(self):
        dialog = NyIndmeldingDialog(self.vindue, self.t.indmeldinger)
        dialog.accept()
        self.assertIn("titel", dialog.fejl_label.text().lower())
        self.assertIsNone(dialog.indmelding)
        dialog.felter["titel"].setText("Ny rapport")
        dialog.felter["beskrivelse"].setPlainText("Antal aktive forløb pr. område")
        dialog.kategori_input.setCurrentText("Data og ERP")
        dialog.accept()
        self.assertEqual(dialog.indmelding.kategori, "Data og ERP")
        self.assertEqual(dialog.indmelding.indsender, ADMIN)

    def test_indmeldingsdialog_administrator_behandler_og_kommenterer(self):
        ind = self.ny_indmelding()
        dialog = IndmeldingDialog(self.vindue, self.t.indmeldinger,
                                  self.t.indmeldinger.detaljer(ind.id), [ADMIN])
        dialog.status_input.setCurrentText(im.TIL_VURDERING)
        dialog.prioritet_input.setCurrentText(im.HOEJ)
        dialog.ansvarlig_input.setCurrentText(ADMIN)
        dialog._gem()
        self.assertTrue(dialog.aendret)
        gemt = self.t.indmeldinger.hent(ind.id)
        self.assertEqual((gemt.status, gemt.prioritet, gemt.ansvarlig),
                         (im.TIL_VURDERING, im.HOEJ, ADMIN))
        dialog.kommentar_input.setPlainText("Vi kigger på det")
        dialog._tilfoej_kommentar()
        self.assertEqual(len(dialog.detaljer.kommentarer), 1)
        self.assertEqual(dialog.historik_tabel.rowCount(), 4)   # oprettet + 3 ændringer
        dialog.close()

    def test_indmeldingsdialog_for_almindelig_bruger_er_skrivebeskyttet(self):
        ind = self.ny_indmelding()
        self.t.auth.opret("lise", "Lise", "Bruger", "hemmelig")
        session.log_ind(self.t.auth.log_ind("lise", "hemmelig"))
        dialog = IndmeldingDialog(self.vindue, self.t.indmeldinger,
                                  self.t.indmeldinger.detaljer(ind.id), [ADMIN])
        self.assertFalse(dialog.status_input.isEnabled())
        self.assertTrue(dialog.felter["titel"].isReadOnly(), "ikke lises egen indmelding")
        self.assertFalse(dialog.intern_input.isVisibleTo(dialog))
        self.assertFalse(dialog.gem_knap.isVisibleTo(dialog))
        dialog.close()

    def test_udloebet_session_logger_ud_kontrolleret(self):
        class AnnulleretLogin:
            def __init__(self, *_a, **_k):
                self.bruger = None

            def exec(self):
                return False

        with mock.patch.object(self.t.auth, "kontroller_session",
                               side_effect=SessionUdloebetFejl("Din session er udløbet.")), \
                mock.patch("app.ui.hovedvindue.LoginDialog", AnnulleretLogin), \
                mock.patch.object(self.vindue, "afslut") as afslut:
            self.vindue._minut_tik()
            _app.processEvents()                 # log ud sker, når handlingen er færdig
        self.assertIsNone(session.bruger())
        self.assertFalse(self.vindue.timer.isActive())
        self.assertEqual(self.vindue.sider["off_aktive"].tabel.rowCount(), 0, "data er fjernet")
        afslut.assert_called_once()

    def test_onboardingdialog_filtrerer_skabeloner_efter_stilling(self):
        skabeloner = self.t.skabeloner.sagsskabeloner(OB.PROCES)
        dialog = OnboardingDialog(self.vindue, None, skabeloner, ["Nord"], ["tester"])
        dialog.stilling_input.setCurrentText("FM")
        self.assertIn("FM/DM", dialog.skabelon_input.itemText(0))
        dialog.stilling_input.setCurrentText("Ad Hoc")
        self.assertIn("standard", dialog.skabelon_input.itemText(0))


if __name__ == "__main__":
    unittest.main()
