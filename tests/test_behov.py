"""HR's behovsregistrering: validering, betingede opgaver og oplæringsvagt."""
import unittest

from app.domain.behov import Behov, Toej
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.repositories.fejl import ValideringsFejl
from app.services import workflow
from app.services.onboarding_service import opgave_med_noegle
from tests.hjaelp import TjenesteTest


class BehovValideringTest(unittest.TestCase):
    def test_stillinger_er_de_fire_kendte(self):
        self.assertEqual(set(OB.STILLINGER), {"Ad Hoc", "FM", "Afløser", "DM"})

    def test_toej_kombinationer_og_storrelse_antal(self):
        for polo, fleece in ((True, False), (False, True), (True, True), (False, False)):
            b = Behov(polo=Toej(polo, "M", 2), fleece=Toej(fleece, "XL", 1))
            self.assertEqual(b.valider("FM"), [])
            self.assertEqual(b.betingelse_opfyldt("toej"), polo or fleece)
        self.assertEqual(len(Behov(polo=Toej(True, "", 2)).valider("FM")), 1)
        self.assertEqual(len(Behov(fleece=Toej(True, "M", 6)).valider("FM")), 1)
        self.assertEqual(len(Behov(fleece=Toej(True, "M", 0)).valider("FM")), 1)
        # Fravalgt tøj gemmer ingen størrelse/antal.
        self.assertEqual(Behov(polo=Toej(False, "M", 3)).til_dict()["polo"],
                         {"valgt": False, "stoerrelse": "", "antal": 0})

    def test_mobil_abonnement_og_udvidet_udstyr_efter_stilling(self):
        self.assertEqual(Behov(mobil=True, abonnement="Tale og data").valider("Afløser"), [])
        self.assertEqual(Behov(mobil=True, abonnement="Kun data").valider("Ad Hoc"), [])
        self.assertTrue(Behov(mobil=True, abonnement="Tale og data").valider("Ad Hoc"))
        self.assertTrue(Behov(mobil=True).valider("FM"))
        self.assertEqual(Behov(mobil=False, abonnement="Kun data").til_dict()["abonnement"], "")
        self.assertEqual(Behov(email=True, firmabil=True).valider("DM"), [])
        self.assertEqual(len(Behov(email=True, firmabil=True).valider("Ad Hoc")), 2)


class BetingedeOpgaverTest(TjenesteTest):
    def test_kun_valgte_behov_giver_relevante_opgaver(self):
        sag = self.ny_onboarding(behov={"polo": {"valgt": True, "stoerrelse": "S", "antal": 1},
                                        "mobil": True, "abonnement": "Kun data"})
        status = {o.noegle: o.status for o in sag.opgaver if o.betingelse}
        self.assertEqual(status["polo"], Opgave.IKKE_STARTET)
        self.assertEqual(status["telefon"], Opgave.IKKE_STARTET)
        for noegle in ("fleece", "email", "firmabil"):
            self.assertEqual(status[noegle], Opgave.UNDTAGET)
        self.assertEqual(opgave_med_noegle(sag, "firmabil").begrundelse, workflow.IKKE_VALGT)

    def test_aendret_behov_genaabner_men_overskriver_ikke_paabegyndt(self):
        sag = self.ny_onboarding(behov={"mobil": True, "abonnement": "Kun data"})
        telefon = opgave_med_noegle(sag, "telefon")
        ny = sag.kopi()
        ny.find_opgave(telefon.id).saet_status(Opgave.I_GANG)
        sag = self.t.onboarding.gem_aendret(sag, ny)
        sag = self.t.onboarding.rediger(sag, {"behov": {"firmabil": True, "mobil": False}})
        self.assertEqual(opgave_med_noegle(sag, "firmabil").status, Opgave.IKKE_STARTET)
        self.assertEqual(opgave_med_noegle(sag, "telefon").status, Opgave.I_GANG)
        self.assertEqual(len(workflow.uoverensstemmelser(sag, sag.behov)), 1)
        behov = [h for h in sag.historik.haendelser() if h["handling"] == "Behov ændret"]
        self.assertIn("Firmabil: nej → ja", behov[-1]["kommentar"])

    def test_ugyldigt_behov_afvises(self):
        with self.assertRaises(ValideringsFejl):
            self.ny_onboarding(stilling="Ad Hoc", behov={"firmabil": True})


class OplaeringTest(TjenesteTest):
    def test_tidspunkt_afslutter_ikke_bookingen(self):
        sag = self.ny_onboarding(oplaering_planlagt="2026-12-01T08:00:00")
        booket = opgave_med_noegle(sag, "oplaering_booket")
        self.assertEqual((booket.planlagt, booket.status),
                         ("2026-12-01T08:00:00", Opgave.IKKE_STARTET))
        sag = self.t.onboarding.rediger(sag, {"oplaering_booking": "Afventer bekræftelse"})
        self.assertEqual(opgave_med_noegle(sag, "oplaering_booket").status, Opgave.AFVENTER)
        sag = self.t.onboarding.rediger(sag, {"oplaering_planlagt": "2026-12-02T09:00:00"})
        booket = opgave_med_noegle(sag, "oplaering_booket")
        self.assertEqual((booket.planlagt, booket.status),
                         ("2026-12-02T09:00:00", Opgave.AFVENTER))
        self.assertEqual(opgave_med_noegle(sag, "oplaering_gennemfoert").status,
                         Opgave.IKKE_STARTET)

    def test_behov_afklaret_markerer_hr_opgaven(self):
        sag = self.ny_onboarding(behov_afklaret=True)
        self.assertEqual(opgave_med_noegle(sag, "behov_registreret").status, Opgave.UDFOERT)


if __name__ == "__main__":
    unittest.main()
