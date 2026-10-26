"""Parallelle arbejdsspor: afhængigheder, sporstatus og klarhed til opstart."""
import unittest
from datetime import date, timedelta

from app.domain import afhaengighed
from app.domain import arbejdsspor as sp
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.repositories.fejl import ValideringsFejl
from tests.hjaelp import TjenesteTest, dato


FULDT_BEHOV = {"polo": {"valgt": True, "stoerrelse": "M", "antal": 2},
               "fleece": {"valgt": True, "stoerrelse": "L", "antal": 1},
               "mobil": True, "abonnement": "Tale og data", "email": True, "firmabil": True}


def _forloeb(dage=30):
    return OB("Ole", stilling="FM", ansaettelsesdato=dato(dage), opgaver=[
        Opgave("Godkendt", noegle="godkendt", spor="hr", afdeling="HR"),
        Opgave("Kontrakt", noegle="kontrakt", spor="kontrakt", afdeling="Administration",
               afhaenger_af=["godkendt"]),
        Opgave("Telefon", noegle="telefon", spor="telefon", afhaenger_af=["kontrakt"]),
        Opgave("Polo", noegle="polo", spor="toej", afhaenger_af=["kontrakt"]),
        Opgave("Oplæringsvagt", noegle="booket", spor="oplaering", afhaenger_af=["godkendt"]),
    ])


class AfhaengighedTest(unittest.TestCase):
    def test_kun_egne_forudsaetninger_blokerer(self):
        f = _forloeb()
        telefon, booket = f.opgaver[2], f.opgaver[4]
        self.assertTrue(f.er_blokeret(telefon))
        self.assertEqual(f.blokeringsaarsag(f.opgaver[1]), "Venter på: Godkendt (HR)")
        f.opgaver[0].saet_status(Opgave.UDFOERT)
        # Oplæringsvagten venter ikke på kontrakten – telefonen gør.
        self.assertFalse(f.er_blokeret(booket))
        self.assertTrue(f.er_blokeret(telefon))
        f.opgaver[1].saet_status(Opgave.UDFOERT)
        self.assertFalse(f.er_blokeret(telefon))

    def test_undtaget_forudsaetning_blokerer_ikke(self):
        f = _forloeb()
        f.opgaver[0].saet_status(Opgave.UNDTAGET)
        self.assertFalse(f.er_blokeret(f.opgaver[1]))

    def test_cirkel_ukendt_noegle_og_dublet_afvises(self):
        cirkel = [{"navn": "A", "noegle": "a", "afhaenger_af": ["b"]},
                  {"navn": "B", "noegle": "b", "afhaenger_af": ["a"]}]
        self.assertIn("Cirkulær afhængighed: A → B → A.", afhaengighed.find_fejl(cirkel))
        fejl = afhaengighed.find_fejl([{"navn": "A", "noegle": "a", "afhaenger_af": ["x"]},
                                       {"navn": "B", "noegle": "a"}])
        self.assertEqual(len(fejl), 2)
        self.assertEqual(afhaengighed.find_fejl(_forloeb().opgaver), [])


class SporStatusTest(unittest.TestCase):
    def test_spor_har_hver_sin_status(self):
        f = _forloeb()
        i_dag = date.today()
        for o in f.opgaver[:2]:
            o.saet_status(Opgave.UDFOERT)
        f.opgaver[3].saet_status(Opgave.I_GANG)
        f.opgaver[4].frist = (i_dag - timedelta(days=1)).isoformat()
        status = {s.spor: s.status for s in sp.alle_spor(f, i_dag)}
        self.assertEqual(status, {"hr": sp.FAERDIG, "kontrakt": sp.FAERDIG, "telefon": sp.KLAR,
                                  "toej": sp.I_GANG, "oplaering": sp.FORSINKET})

    def test_blokeret_spor_viser_aarsag_og_ikke_relevant(self):
        f = _forloeb()
        telefon = sp.spor_status(f, "telefon", date.today())
        self.assertEqual((telefon.status, telefon.tekst),
                         (sp.BLOKERET, "Venter på: Kontrakt (Administration)"))
        f.opgaver[3].saet_status(Opgave.UNDTAGET)
        self.assertEqual(sp.spor_status(f, "toej", date.today()).status, sp.IKKE_RELEVANT)


class KlarhedTest(unittest.TestCase):
    def test_niveauer(self):
        i_dag = date.today()
        self.assertEqual(sp.klarhed(_forloeb(30), i_dag).niveau, sp.PAA_PLAN)
        self.assertEqual(sp.klarhed(_forloeb(3), i_dag).niveau, sp.OPSTART_BLOKERET)
        f = _forloeb(3)
        for o in f.opgaver[:2]:
            o.saet_status(Opgave.UDFOERT)
        self.assertEqual(sp.klarhed(f, i_dag).niveau, sp.RISIKO)
        for o in f.opgaver:
            o.saet_status(Opgave.UDFOERT)
        self.assertEqual(sp.klarhed(f, i_dag).niveau, sp.KLAR_TIL_OPSTART)

    def test_opgaver_efter_startdagen_taeller_ikke(self):
        f = _forloeb(3)
        for o in f.opgaver:
            o.saet_status(Opgave.UDFOERT)
        f.opgaver.append(Opgave("Opfølgning", frist=dato(10)))
        self.assertEqual(sp.klarhed(f, date.today()).niveau, sp.KLAR_TIL_OPSTART)


class StandardskabelonTest(TjenesteTest):
    def test_kontrakt_laaser_udstyr_men_ikke_oplaeringsvagt(self):
        sag = self.ny_onboarding(behov=FULDT_BEHOV)
        efter = {o.noegle: o for o in sag.opgaver}
        self.assertEqual(efter["kontrakt"].afdeling, "Administration")
        self.assertTrue(sag.er_blokeret(efter["telefon"]))
        sag = self.t.onboarding.marker_opgave_udfoert(sag, efter["kandidat_godkendt"].id)
        efter = {o.noegle: o for o in sag.opgaver}
        self.assertFalse(sag.er_blokeret(efter["oplaering_booket"]))
        with self.assertRaises(ValideringsFejl):
            self.t.onboarding.marker_opgave_udfoert(sag, efter["polo"].id)
        # Felterne overlever lagringen.
        gemt = self.t.onboarding.hent(sag.id).find_opgave(efter["polo"].id)
        self.assertEqual((gemt.spor, gemt.betingelse, gemt.afhaenger_af),
                         ("toej", "polo", ["kontrakt"]))

    def test_skabelon_med_cirkel_kan_ikke_gemmes(self):
        skabelon = self.t.skabeloner.sagsskabeloner("onboarding")[0]
        skabelon["opgaver"][0]["afhaenger_af"] = ["opfoelgning"]
        skabelon["opgaver"][-1]["afhaenger_af"] = ["kandidat_godkendt"]
        with self.assertRaises(ValideringsFejl):
            self.t.skabeloner.gem("sager", skabelon)


if __name__ == "__main__":
    unittest.main()
