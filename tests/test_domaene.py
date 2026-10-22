"""Domæneregler: statusberegning, milepæle, gamle dataformater og tidslinje."""
import hashlib
import json
import unittest

from app.domain.historik import FELTER, Historik
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from tests.hjaelp import dato


class OffboardingStatusTest(unittest.TestCase):
    def setUp(self):
        self.m = Medarbejder("1", "A", dato(), opgaver=[
            Opgave("Er lukket i NAV?"),
            Opgave("Modtag telefon", udstyr="Telefon"),
        ])

    def test_status_foelger_opgaverne(self):
        self.assertEqual(self.m.status, Medarbejder.STATUS_AFVENTER)
        self.m.opgaver[1].saet_status(Opgave.UDFOERT)
        # Udstyr modtaget, men systemadgang stadig åben -> noget mangler stadig.
        self.assertEqual(self.m.status, Medarbejder.STATUS_DELVIST)
        self.m.opgaver[0].saet_status(Opgave.UNDTAGET)
        self.assertEqual(self.m.status, Medarbejder.STATUS_AFVIKLET)

    def test_afsluttet_tidspunkt_registreres(self):
        opgave = self.m.opgaver[1]
        opgave.saet_status(Opgave.UDFOERT)
        self.assertTrue(opgave.afsluttet_tid)
        opgave.saet_status(Opgave.I_GANG)
        self.assertEqual(opgave.afsluttet_tid, "")

    def test_manglende_udstyr(self):
        self.assertEqual(self.m.manglende_udstyr(), ["Telefon"])


class GammeltFormatTest(unittest.TestCase):
    def test_v050_udstyr_bliver_til_opgaver_og_status_bevares(self):
        m = Medarbejder.fra_dict({
            "loennr": "9", "navn": "G", "status": "Afventer Udstyr", "fratraedelsesdato": dato(),
            "udstyr": {"telefon": {"har": True, "afleveret": True}, "andet": {"har": True}},
            "andet_beskrivelse": "Nøgler",
        })
        self.assertEqual([(o.udstyr, o.status) for o in m.opgaver],
                         [("Telefon og SIM-kort", "Udført"), ("Nøgler", "Ikke startet")])
        self.assertEqual(m.status, "Afventer Udstyr")      # låst, ikke ændret
        self.assertTrue(m.id and m.person_id)
        self.assertEqual(m.historik.haendelser()[0]["handling"], "Overført fra tidligere version")

    def test_v054_opgaver_uden_udstyrsfelt_faar_det_udledt(self):
        m = Medarbejder.fra_dict({"loennr": "1", "navn": "X", "fratraedelsesdato": dato(),
                                  "opgaver": [{"navn": "Modtag tøj"}], "historik": []})
        self.assertEqual(m.opgaver[0].udstyr, "Tøj")


class HistorikTest(unittest.TestCase):
    def test_gamle_haendelser_har_uaendret_hash(self):
        """Hændelser uden data skal hashes som i V0.6 (eksisterende kæder er intakte)."""
        h = Historik()
        h.tilfoej("Notat", "tekst", bruger="x", tid="2026-01-01T10:00:00")
        haendelse = h.haendelser()[0]
        gammel = hashlib.sha256(json.dumps(
            {f: haendelse.get(f, "") for f in FELTER}, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        self.assertEqual(haendelse["hash"], gammel)

    def test_manipulation_opdages(self):
        h = Historik()
        h.tilfoej("A", data={"type": "status", "fra": "x", "til": "y"})
        h.tilfoej("B")
        self.assertTrue(h.er_intakt())
        data = h.haendelser()
        data[0]["data"]["til"] = "z"
        self.assertFalse(Historik(data).er_intakt())


class OnboardingMilepaelTest(unittest.TestCase):
    def setUp(self):
        self.f = OB("Ole", stilling="FM", ansaettelsesdato=dato(), opgaver=[
            Opgave("Godkendt", milepael="kandidat"),
            Opgave("Kontrakt", milepael="kontrakt"),
            Opgave("Oplæring", milepael="oplaering"),
            Opgave("Job", milepael="jobs"),
        ])

    def test_status_foelger_milepaele_og_laaser_senere_opgaver(self):
        self.assertEqual(self.f.status, OB.STATUS_KANDIDAT)
        self.assertTrue(self.f.er_laast(self.f.opgaver[2]))
        self.assertEqual([o.navn for o in self.f.aabne_opgaver()], ["Godkendt"])
        for opgave, forventet in zip(self.f.opgaver, OB.FREMDRIFT[1:]):
            opgave.saet_status(Opgave.UDFOERT)
            self.assertEqual(self.f.status, forventet)

    def test_overstyring_kraeves_ved_spring(self):
        self.assertTrue(self.f.kraever_overstyring(OB.STATUS_AKTIV))
        self.assertFalse(self.f.kraever_overstyring(OB.STATUS_KANDIDAT))
        self.assertEqual(self.f.mangler_for(OB.STATUS_OPLAERING), ["Godkendt", "Kontrakt"])

    def test_kandidat_kraever_ikke_loennr(self):
        self.assertEqual(self.f.loennr, "")
        self.assertEqual(OB.fra_dict(self.f.til_dict()).til_dict(), self.f.til_dict())


if __name__ == "__main__":
    unittest.main()
