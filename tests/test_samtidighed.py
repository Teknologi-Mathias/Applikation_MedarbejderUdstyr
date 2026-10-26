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
        self.s.marker_opgave_udfoert(hr_udgave, self._id("kandidat_godkendt"))
        # Administrationens kopi er forældet, men ændrer andre opgaver.
        admin_udgave = self.s.saet_opgave_status(admin_udgave, self._id("oplaering_booket"),
                                                 Opgave.AFVENTER)
        self.assertEqual(admin_udgave.find_opgave(self._id("oplaering_booket")).status,
                         Opgave.AFVENTER)
        gemt = self.s.aendr_frist(admin_udgave, self._id("loennr"), dato(3))
        self.assertEqual(gemt.find_opgave(self._id("kandidat_godkendt")).status, Opgave.UDFOERT)
        self.assertEqual(gemt.find_opgave(self._id("loennr")).frist, dato(3))
        self.assertTrue(gemt.historik.er_intakt())
        handlinger = [h["handling"] for h in self.s.hent(self.sag.id).historik.haendelser()]
        self.assertIn("Kandidat godkendt: Ikke startet → Udført", handlinger)
        self.assertIn("Opgave ændret: Lønnr. tildelt", handlinger)

    def test_samme_felt_aendret_forskelligt_giver_tydelig_konflikt(self):
        a, b = self.s.hent(self.sag.id), self.s.hent(self.sag.id)
        self.s.aendr_frist(a, self._id("telefon"), dato(1))
        with self.assertRaises(KonfliktFejl) as fejl:
            self.s.aendr_frist(b, self._id("telefon"), dato(2))
        self.assertIn("frist", str(fejl.exception))
        self.assertEqual(self.s.hent(self.sag.id).find_opgave(self._id("telefon")).frist, dato(1))

    def test_samme_aendring_hos_begge_er_ingen_konflikt(self):
        a, b = self.s.hent(self.sag.id), self.s.hent(self.sag.id)
        self.s.marker_opgave_udfoert(a, self._id("kandidat_godkendt"))
        gemt = self.s.marker_opgave_udfoert(b, self._id("kandidat_godkendt"))
        self.assertEqual(gemt.find_opgave(self._id("kandidat_godkendt")).status, Opgave.UDFOERT)
