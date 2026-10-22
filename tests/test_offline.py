"""Offline-drift: lokal kopi, ændringslog, synkronisering og konflikter."""
import unittest

from app.bootstrap import byg_tjenester
from app.domain import skabelon as sk
from app.repositories.fejl import OfflineFejl
from tests.hjaelp import TjenesteTest


class OfflineTest(TjenesteTest):
    def test_aendringer_offline_synkroniseres(self):
        sag = self.ny_offboarding()
        self.t.lagring.gaa_offline()
        self.assertTrue(self.t.datakilde.offline)
        sag = self.t.offboarding.hent(sag.id)
        self.t.offboarding.tilfoej_notat(sag, "skrevet offline")
        ny = self.t.offboarding.opret(self.t.offboarding.ny_sag(
            {"loennr": "999", "navn": "Ny offline", "fratraedelsesdato": sag.fratraedelsesdato}), None)
        self.assertEqual(len(self.t.lagring.ventende_aendringer()), 2)

        # Den centrale mappe er ikke ændret endnu.
        central = byg_tjenester(self.central, self._tmp / "anden-pc")
        self.assertEqual(len(central.offboarding.hent_aktive()), 1)

        resultat = self.t.lagring.gaa_online()
        self.assertEqual((resultat.anvendt, resultat.konflikter), (2, []))
        self.assertFalse(self.t.datakilde.offline)
        navne = {s.navn for s in central.offboarding.hent_aktive()}
        self.assertEqual(navne, {"Mette Jensen", "Ny offline"})
        self.assertIsNotNone(central.offboarding.hent(ny.id))

    def test_konflikt_overskriver_ikke_kollegaens_aendring(self):
        sag = self.ny_offboarding()
        self.t.lagring.gaa_offline()
        self.t.offboarding.tilfoej_notat(self.t.offboarding.hent(sag.id), "min offline-ændring")

        kollega = byg_tjenester(self.central, self._tmp / "kollega")
        kollega.offboarding.tilfoej_notat(kollega.offboarding.hent(sag.id), "kollegaens ændring")

        resultat = self.t.lagring.gaa_online()
        self.assertEqual(resultat.anvendt, 0)
        self.assertEqual(len(resultat.konflikter), 1)
        handlinger = [h["kommentar"] for h in kollega.offboarding.hent(sag.id).historik.haendelser()]
        self.assertIn("kollegaens ændring", handlinger)
        self.assertNotIn("min offline-ændring", handlinger)

        self.t.lagring.loes_konflikt(0, brug_min=True)
        handlinger = [h["kommentar"] for h in kollega.offboarding.hent(sag.id).historik.haendelser()]
        self.assertIn("min offline-ændring", handlinger)
        self.assertEqual(self.t.lagring.konflikter(), [])

    def test_faelles_opsaetning_er_skrivebeskyttet_offline(self):
        self.t.lagring.gaa_offline()
        skabelon = self.t.skabeloner.aktive(sk.MAIL)[0]
        with self.assertRaises(OfflineFejl):
            self.t.skabeloner.gem(sk.MAIL, skabelon)
        with self.assertRaises(OfflineFejl):
            self.t.auth.opret("ny", "Ny", "Bruger", "hemmelig")

    def test_offline_tilstand_huskes_ved_genstart(self):
        self.t.lagring.gaa_offline()
        genstartet = byg_tjenester(self.central, self.lokal)
        self.assertTrue(genstartet.datakilde.offline)


if __name__ == "__main__":
    unittest.main()
