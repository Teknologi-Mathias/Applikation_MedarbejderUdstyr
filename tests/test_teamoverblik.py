"""Teamfiltre, nøgletal og Arbejdsoverblikkets kort – samme statusser som arbejdssporene."""
import unittest
from datetime import date, timedelta

from app.domain import arbejdsspor as sp
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.services import teamoverblik as tov
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


class TeamTest(unittest.TestCase):
    def test_filtre_og_noegletal(self):
        snart, senere = _sag("Snart", dage=3), _sag("Senere", dage=40)
        sager = [snart, senere]

        def hvem(filter_, **kw):
            return [s.navn for s in sager if tov.sag_matcher(s, filter_, I_DAG, **kw)]
        self.assertEqual(hvem(tov.KOMMENDE), ["Snart"])
        self.assertEqual(hvem(tov.BLOKEREDE), ["Snart"])
        self.assertEqual(hvem(tov.SAG_MINE, brugernavn="BO"), ["Snart", "Senere"])
        self.assertEqual(hvem(tov.MANGLER_BEKRAEFTELSE), ["Snart", "Senere"])
        tal = {t.navn: t.antal for t in tov.noegletal(sager, I_DAG)}
        self.assertEqual(tal["Aktive forløb"], 2)
        self.assertEqual(tal["Starter snart"], 1)
        self.assertEqual(tal["Forsinkede opgaver"], 2)
        self.assertEqual(tal["Uden ejer"], 0, "afdelingerne ejer opgaverne")
        self.assertEqual(tal["Afventer andre"], 2)

    def test_naeste_handling_er_det_mest_presserende_spor(self):
        sag = _sag()
        for o in sag.opgaver:
            o.spor = {"godkendt": "hr", "kontrakt": "kontrakt", "telefon": "telefon",
                      "opf": "opfoelgning"}[o.noegle]
        self.assertEqual(tov.naeste_handling(sag, I_DAG).spor, "opfoelgning")


class KontrolrumTest(unittest.TestCase):
    def test_blokeret_og_forsinket_taeller_stadig_som_risiko(self):
        sag = _sag(dage=30)
        telefon = sag.opgaver[2]
        telefon.frist = (I_DAG - timedelta(days=3)).isoformat()
        self.assertEqual(sp.arbejdstilstand(sag, telefon), sp.BLOKERET)
        self.assertEqual(sp.tidsrisiko(telefon, I_DAG), sp.FORSINKET)
        self.assertTrue(tov.sag_matcher(sag, tov.SAG_FORSINKEDE, I_DAG))
        alarm = next(a for a in action_center([sag], I_DAG) if a.opgave_id == telefon.id)
        self.assertEqual(alarm.niveau, KRITISK)
        self.assertIn("Venter på: Kontrakt", alarm.undertitel)
        self.assertEqual(sp.klarhed(sag, I_DAG).niveau, sp.RISIKO)
        tal = {t.noegle: t.antal for t in kr.overblik([sag], I_DAG)}
        self.assertEqual(tal[kr.FORSINKEDE], 1)                   # forløb (Teamoverblik-filteret)
        haster = {h.opgave.id: h for h in kr.haster_nu([sag], I_DAG)}
        self.assertEqual(haster[telefon.id].handling, kr.AABN_FORUDSAETNING)
        self.assertEqual(haster[telefon.id].handling_opgave_id, sag.opgaver[1].id)

    def test_udstyrskoe_kun_ved_registreret_behov(self):
        sag = _sag()
        sag.opgaver[2].spor, sag.opgaver[2].betingelse = "telefon", "mobil"
        udstyr = lambda: next(k for k in kr.koeer([sag], I_DAG) if k.noegle == kr.UDSTYR)
        self.assertEqual(udstyr().poster, [])
        sag.behov.mobil, sag.behov.abonnement = True, "Kun data"
        self.assertEqual([a.titel for a in udstyr().poster], ["Ole"])

    def test_en_raekke_pr_kandidat_med_den_vigtigste_opgave(self):
        sag = _sag()
        sag.opgaver += [
            Opgave("Oplæringsvagt booket", noegle="booket", spor="oplaering"),
            Opgave("Første oplæring", noegle="gennemfoert", spor="oplaering",
                   frist=(I_DAG - timedelta(days=1)).isoformat()),
        ]
        koe = next(k for k in kr.koeer([sag], I_DAG) if k.noegle == kr.OPLAERING)
        self.assertEqual(len(koe.poster), 1)
        raekke = koe.poster[0]
        self.assertEqual((raekke.titel, raekke.undertitel, raekke.badge),
                         ("Ole", "2 åbne opgaver", "Forsinket"))
        self.assertEqual(raekke.opgave_id, sag.opgaver[-1].id)    # åbner den forsinkede


if __name__ == "__main__":
    unittest.main()
