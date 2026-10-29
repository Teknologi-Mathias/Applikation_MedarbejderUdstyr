"""Flere brugere på samme sag: uafhængige ændringer flettes, reelle konflikter afvises."""
from app.domain.opgave import Opgave
from app.repositories.fejl import KonfliktFejl
from app.services.onboarding_service import opgave_med_noegle
from tests.hjaelp import TjenesteTest, dato


class SamtidighedTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.sag = self.ny_onboarding(behov={"mobil": True, "abonnement": "Kun data"})
        self.s = self.t.onboarding

    def _id(self, noegle):
        return opgave_med_noegle(self.sag, noegle).id

    def test_to_brugere_paa_forskellige_opgaver_flettes(self):
        hr_udgave, admin_udgave = self.s.hent(self.sag.id), self.s.hent(self.sag.id)
        self.s.marker_opgave_udfoert(hr_udgave, self._id("oplaering_booket"))
        # Administrationens kopi er forældet, men ændrer andre opgaver.
        admin_udgave = self.s.aendr_frist(admin_udgave, self._id("kontrakt"), dato(2))
        self.assertEqual(admin_udgave.find_opgave(self._id("kontrakt")).frist, dato(2))
        gemt = self.s.aendr_frist(admin_udgave, self._id("opfoelgning"), dato(3))
        self.assertEqual(gemt.find_opgave(self._id("oplaering_booket")).status, Opgave.UDFOERT)
        self.assertEqual(gemt.find_opgave(self._id("opfoelgning")).frist, dato(3))
        self.assertTrue(gemt.historik.er_intakt())
        handlinger = [h["handling"] for h in self.s.hent(self.sag.id).historik.haendelser()]
        self.assertIn("Oplæringsdag fastlagt: Ikke startet → Udført", handlinger)
        self.assertIn("Opgave ændret: Opfølgningssamtale (1 uge efter start)", handlinger)

    def test_samme_felt_aendret_forskelligt_giver_tydelig_konflikt(self):
        a, b = self.s.hent(self.sag.id), self.s.hent(self.sag.id)
        self.s.aendr_frist(a, self._id("oplaering_booket"), dato(1))
        with self.assertRaises(KonfliktFejl) as fejl:
            self.s.aendr_frist(b, self._id("oplaering_booket"), dato(2))
        self.assertIn("frist", str(fejl.exception))
        self.assertEqual(self.s.hent(self.sag.id).find_opgave(self._id("oplaering_booket")).frist,
                         dato(1))

    def test_samme_aendring_hos_begge_er_ingen_konflikt(self):
        a, b = self.s.hent(self.sag.id), self.s.hent(self.sag.id)
        self.s.marker_opgave_udfoert(a, self._id("oplaering_booket"))
        gemt = self.s.marker_opgave_udfoert(b, self._id("oplaering_booket"))
        self.assertEqual(gemt.find_opgave(self._id("oplaering_booket")).status, Opgave.UDFOERT)
