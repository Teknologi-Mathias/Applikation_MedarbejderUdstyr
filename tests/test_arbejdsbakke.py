"""Arbejdsbakker, teamfiltre og nøgletal – samme statusser som arbejdssporene."""
import unittest
from datetime import date, timedelta

from app.domain import arbejdsspor as sp
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.services import arbejdsbakke as ab
from app.services import kontrolrum as kr
from app.services.action_center import KRITISK, action_center
from tests.hjaelp import dato

I_DAG = date.today()


def _sag(navn="Ole", dage=30):
    return OB(navn, stilling="FM", ansaettelsesdato=dato(dage), opgaver=[
        Opgave("Godkendt", noegle="godkendt", afdeling="HR", ansvarlig="ANNE",
               status=Opgave.UDFOERT, afsluttet=f"{I_DAG.isoformat()}T09:00:00"),
        Opgave("Kontrakt", noegle="kontrakt", afdeling="Administration",
               afhaenger_af=["godkendt"], status=Opgave.AFVENTER),
        Opgave("Telefon", noegle="telefon", afdeling="Administration", afhaenger_af=["kontrakt"]),
        Opgave("Opfølgning", noegle="opf", afdeling="Merch", ansvarlig="BO",
               frist=(I_DAG - timedelta(days=2)).isoformat()),
    ])


class ArbejdsbakkeTest(unittest.TestCase):
    def navne(self, visning, **kw):
        return [p.opgave.navn for p in ab.poster([_sag()], visning, I_DAG, **kw)]

    def test_visninger(self):
        self.assertEqual(self.navne(ab.MINE, brugernavn="bo"), ["Opfølgning"])
        self.assertEqual(self.navne(ab.MIN_AFDELING, afdelinger=["Administration"]),
                         ["Kontrakt", "Telefon"])
        self.assertEqual(self.navne(ab.IKKE_TILDELT), ["Kontrakt", "Telefon"])
        self.assertEqual(self.navne(ab.AFVENTER_ANDRE), ["Kontrakt"])
        self.assertEqual(self.navne(ab.FORSINKEDE), ["Opfølgning"])
        self.assertEqual(self.navne(ab.NYLIGT_AFSLUTTET), ["Godkendt"])

    def test_blokerede_er_med_men_sidst_og_med_aarsag(self):
        poster = ab.poster([_sag()], ab.MIN_AFDELING, I_DAG, afdelinger=["Administration"])
        self.assertEqual([p.blokeret for p in poster], [False, True])
        self.assertEqual(poster[1].aarsag, "Venter på: Kontrakt (Administration)")

    def test_merch_faar_kun_egne_opgaver(self):
        self.assertEqual(self.navne(ab.MIN_AFDELING, afdelinger=["Merch"]), ["Opfølgning"])


class TeamTest(unittest.TestCase):
    def test_filtre_og_noegletal(self):
        snart, senere = _sag("Snart", dage=3), _sag("Senere", dage=40)
        sager = [snart, senere]

        def hvem(filter_, **kw):
            return [s.navn for s in sager if ab.sag_matcher(s, filter_, I_DAG, **kw)]
        self.assertEqual(hvem(ab.KOMMENDE), ["Snart"])
        self.assertEqual(hvem(ab.BLOKEREDE), ["Snart"])
        self.assertEqual(hvem(ab.SAG_MINE, brugernavn="BO"), ["Snart", "Senere"])
        self.assertEqual(hvem(ab.MANGLER_BEKRAEFTELSE), ["Snart", "Senere"])
        tal = {t.navn: t.antal for t in ab.noegletal(sager, I_DAG)}
        self.assertEqual(tal["Aktive forløb"], 2)
        self.assertEqual(tal["Starter snart"], 1)
        self.assertEqual(tal["Forsinkede opgaver"], 2)
        # Kontrakten (ikke tildelt, kan udføres) tæller; den blokerede telefon gør ikke.
        self.assertEqual(tal["Uden ansvarlig"], 2)
        self.assertEqual(tal["Afventer andre"], 2)

    def test_naeste_handling_er_det_mest_presserende_spor(self):
        sag = _sag()
        for o in sag.opgaver:
            o.spor = {"godkendt": "hr", "kontrakt": "kontrakt", "telefon": "telefon",
                      "opf": "opfoelgning"}[o.noegle]
        self.assertEqual(ab.naeste_handling(sag, I_DAG).spor, "opfoelgning")


class KontrolrumTest(unittest.TestCase):
    def test_blokeret_og_forsinket_taeller_stadig_som_risiko(self):
        sag = _sag(dage=30)
        telefon = sag.opgaver[2]
        telefon.frist = (I_DAG - timedelta(days=3)).isoformat()
        self.assertEqual(sp.arbejdstilstand(sag, telefon), sp.BLOKERET)
        self.assertEqual(sp.tidsrisiko(telefon, I_DAG), sp.FORSINKET)
        self.assertIn("Telefon", [p.opgave.navn for p in ab.poster([sag], ab.FORSINKEDE, I_DAG)])
        alarm = next(a for a in action_center([sag], I_DAG) if a.opgave_id == telefon.id)
        self.assertEqual(alarm.niveau, KRITISK)
        self.assertIn("Venter på: Kontrakt", alarm.undertitel)
        self.assertEqual(sp.klarhed(sag, I_DAG).niveau, sp.RISIKO)
        tal = {t.noegle: t.antal for t in kr.overblik([sag], I_DAG)}
        self.assertEqual(tal[kr.FORSINKEDE], 2)                   # telefon + opfølgning
        haster = {h.opgave.id: h for h in kr.haster_nu([sag], I_DAG)}
        self.assertEqual(haster[telefon.id].handling, kr.AABN_FORUDSAETNING)
        self.assertEqual(haster[telefon.id].handling_opgave_id, sag.opgaver[1].id)

    def test_udstyrskoe_kun_ved_registreret_behov(self):
        sag = _sag()
        sag.opgaver[2].spor, sag.opgaver[2].betingelse = "telefon", "mobil"
        udstyr = lambda: next(k for k in kr.koeer([sag], I_DAG) if k.noegle == kr.UDSTYR)
        self.assertEqual(udstyr().poster, [])
        sag.behov.mobil, sag.behov.abonnement = True, "Kun data"
        self.assertIn("Mobil · Kun data", udstyr().poster[0].undertitel)

    def test_registreret_oplaeringstid_er_ikke_booket(self):
        sag = _sag()
        sag.opgaver.append(Opgave("Oplæringsvagt booket", noegle="oplaering_booket",
                                  spor="oplaering", planlagt=f"{dato(5)}T08:00:00"))
        koe = next(k for k in kr.koeer([sag], I_DAG) if k.noegle == kr.OPLAERING)
        self.assertIn("ikke bekræftet", koe.poster[0].undertitel)


if __name__ == "__main__":
    unittest.main()
