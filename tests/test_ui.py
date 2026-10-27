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
from app.ui.hovedvindue import ALLE_SIDER, OMRAADER, MainWindow  # noqa: E402
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
        for noegle in ALLE_SIDER:
            self.vindue.vis_side(noegle)
            _app.processEvents()
        self.assertEqual(self.vindue.sider["on_aktive"].tabel.rowCount(), 1)
        self.assertEqual(self.vindue.sider["off_aktive"].tabel.rowCount(), 1)
        self.assertGreater(self.vindue.dashboard.action.liste.count(), 0)

    def test_hovedomraader_til_venstre_og_undersider_som_faner(self):
        omraader = {noegle: sider for noegle, _, _, sider in OMRAADER}
        self.assertEqual([n for n, _, _, s in OMRAADER if len(s) > 1],
                         ["onboarding", "offboarding", "telefoner"])
        self.vindue.vis_omraade("onboarding")
        self.assertFalse(self.vindue.fane_ramme.isHidden())
        self.assertEqual(self.vindue.faner.count(), len(omraader["onboarding"]))
        self.vindue.faner.setCurrentIndex(2)                   # Aktive forløb
        self.assertIs(self.vindue.stak.currentWidget(), self.vindue.sider["on_aktive"])
        self.vindue.vis_omraade("overblik")
        self.assertTrue(self.vindue.fane_ramme.isHidden(), "én side = ingen faner")
        self.vindue.vis_omraade("onboarding")                  # husker sidste underside
        self.assertIs(self.vindue.stak.currentWidget(), self.vindue.sider["on_aktive"])
        self.vindue.sidebar.indstillinger_knap.click()        # tandhjulet ved brugeren
        self.assertIs(self.vindue.stak.currentWidget(), self.vindue.indstillinger)

    def test_dashboard_kort_aabner_den_filtrerede_liste(self):
        kort = self.vindue.dashboard.kort
        self.assertEqual(kort["starter_snart"].vaerdi.text(), "1")   # onboarding om 7 dage
        self.assertGreater(int(kort["forsinkede"].vaerdi.text()), 0)  # offboarding -10 dage
        kort["forsinkede"].klikket.emit("forsinkede")
        self.assertIs(self.vindue.stak.currentWidget(), self.vindue.arbejdsbakke)
        self.assertEqual(self.vindue.arbejdsbakke.visning(), "forsinkede")
        kort["i_risiko"].klikket.emit("i_risiko")
        self.assertIs(self.vindue.stak.currentWidget(), self.vindue.teamoverblik)
        self.assertEqual(self.vindue.teamoverblik.filter_input.currentData(), "risiko")

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
        self.assertIn(("oensker", [("oensker", "Ønsker & Udvikling")]),
                      [(n, s) for n, _, _, s in OMRAADER])
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

    def test_onboardingdialog_vaelger_den_ene_skabelon_automatisk(self):
        skabeloner = self.t.skabeloner.sagsskabeloner(OB.PROCES)
        dialog = OnboardingDialog(self.vindue, None, skabeloner, ["Nord"], ["tester"])
        for stilling in ("FM", "Ad Hoc"):
            dialog.stilling_input.setCurrentText(stilling)
            self.assertTrue(dialog.skabelon_input.isHidden())
            self.assertEqual(dialog.skabelon_label.text(), "Onboarding (v1)")

    def test_skabelon_editor_bevarer_arbejdsspor_og_afviser_cirkler(self):
        from app.ui.skabelon_dialoger import SagSkabelonDialog
        skabelon = self.t.skabeloner.sagsskabeloner(OB.PROCES)[0]
        dialog = SagSkabelonDialog(self.vindue, skabelon)
        dialog.accept()
        self.assertEqual(dialog.skabelon["opgaver"], skabelon["opgaver"])
        dialog = SagSkabelonDialog(self.vindue, skabelon)
        dialog.tabel.item(0, 4).setText("opfoelgning")       # Afhænger af
        dialog.accept()
        self.assertIn("Cirkulær", dialog.fejl_label.text())

    def test_hr_formular_laaser_udstyr_efter_stilling_og_valg(self):
        dialog = OnboardingDialog(self.vindue, None, [], ["Nord"], ["tester"])
        dialog.stilling_input.setCurrentText("FM")
        dialog.bil_input.setChecked(True)
        dialog.mobil_input.setChecked(True)
        self.assertTrue(dialog.abonnement_input.isEnabled())
        self.assertEqual(dialog.abonnement_input.count(), 3)
        dialog.stilling_input.setCurrentText("Ad Hoc")
        self.assertFalse(dialog.bil_input.isEnabled() or dialog.bil_input.isChecked())
        self.assertEqual(dialog.abonnement_input.currentData(), "Kun data")
        polo, stoerrelse, _ = dialog.toej["polo"]
        polo.setChecked(True)
        self.assertEqual(dialog.hent_behov().valider("Ad Hoc"), ["Vælg en størrelse til polo."])
        stoerrelse.setCurrentText("M")
        dialog.navn_input.setText("Ny Medarbejder")
        dialog.accept()
        data = dialog.hent_data()
        self.assertEqual(data["behov"]["polo"], {"valgt": True, "stoerrelse": "M", "antal": 1})
        self.assertEqual(data["oplaering_planlagt"], "")

    def test_opret_kandidat_profil_og_flow_efter_gem(self):
        self.t.indstillinger.opdater(udstyrsprofiler={
            "FM": {"polo": {"valgt": True, "antal": 2}, "mobil": True,
                   "abonnement": "Tale og data"}})
        profiler = self.t.indstillinger.udstyrsprofiler()
        skabeloner = self.t.skabeloner.sagsskabeloner(OB.PROCES)
        dialog = OnboardingDialog(self.vindue, None, skabeloner, ["Nord"], ["tester"], profiler)
        self.assertEqual(dialog.stilling(), "", "ingen stilling er forvalgt")
        self.assertFalse(dialog.planlaegning.isVisibleTo(dialog), "senere planlægning er foldet")
        self.assertFalse(dialog.ansvarlig_input.isVisibleTo(dialog), "ingen koordinator")
        self.assertTrue(dialog.loennr_input.isVisibleTo(dialog), "HR tildeler lønnr. (ERP)")
        dialog.navn_input.setText("Kim Kandidat")
        dialog.accept()
        self.assertIn("stillingskategori", dialog.fejl_label.text())
        dialog.stilling_input.setCurrentText("FM")
        polo, stoerrelse, antal = dialog.toej["polo"]
        self.assertTrue(polo.isChecked() and antal.value() == 2 and dialog.mobil_input.isChecked())
        self.assertTrue(dialog.skabelon_input.isHidden(), "én skabelon vælges automatisk")
        dialog.accept()                                           # størrelsen kan vente
        data = dialog.hent_data()
        self.assertEqual((data["ansaettelsesdato"], data["behov"]["polo"]["stoerrelse"]), ("", ""))
        self.assertEqual(data["skabelon"]["navn"], "Onboarding")

        with mock.patch("app.ui.modul_controller.OnboardingDialog") as Dialog, \
                mock.patch("app.ui.modul_controller.SagDialog") as SagVindue:
            Dialog.return_value.exec.return_value = True
            Dialog.return_value.hent_data.return_value = data
            self.vindue.ctrl["onboarding"].opret()
        SagVindue.assert_not_called()
        side = self.vindue.sider["on_aktive"]
        self.assertIs(self.vindue.stak.currentWidget(), side)
        valgt = self.t.onboarding.hent(side.valgt_id())
        self.assertEqual((valgt.navn, valgt.ansaettelsesdato), ("Kim Kandidat", ""))
        self.assertIn("er oprettet", side.besked.text())


if __name__ == "__main__":
    unittest.main()
