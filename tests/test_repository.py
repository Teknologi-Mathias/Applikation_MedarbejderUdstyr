"""JSON-repository: id-baseret lagring, optimistisk låsning, arkiv og migrering."""
import json
import unittest

from app.infrastructure import stier
from app.repositories.fejl import KonfliktFejl
from tests.hjaelp import TjenesteTest, dato


class SagRepositoryTest(TjenesteTest):
    def test_gem_og_hent_paa_id(self):
        sag = self.ny_offboarding()
        hentet = self.t.offboarding.hent(sag.id)
        self.assertEqual(hentet.navn, "Mette Jensen")
        self.assertEqual(hentet.version, 1)

    def test_loennr_kan_aendres_uden_at_miste_sagen(self):
        sag = self.ny_offboarding(loennr="100")
        ny = sag.kopi()
        ny.loennr = "200"
        self.t.offboarding.gem_aendret(sag, ny)
        self.assertEqual(self.t.offboarding.hent(sag.id).loennr, "200")

    def test_samtidig_aendring_afvises(self):
        sag = self.ny_offboarding()
        kollega = self.t.offboarding.hent(sag.id)
        self.t.offboarding.tilfoej_notat(kollega, "Kollegaens ændring")
        with self.assertRaises(KonfliktFejl):
            self.t.offboarding.tilfoej_notat(sag, "Min ændring på gammel version")

    def test_aendring_i_en_sag_overskriver_ikke_andre(self):
        a = self.ny_offboarding(loennr="1", navn="A")
        b = self.ny_offboarding(loennr="2", navn="B")
        self.t.offboarding.tilfoej_notat(a, "notat")
        self.t.offboarding.tilfoej_notat(b, "notat")   # b var hentet før a blev gemt
        self.assertEqual({s.navn for s in self.t.offboarding.hent_aktive()}, {"A", "B"})

    def test_arkiver_og_aktiver(self):
        sag = self.ny_offboarding()
        arkiveret = self.t.offboarding.arkiver(sag)
        self.assertEqual(self.t.offboarding.hent_aktive(), [])
        self.assertEqual(self.t.offboarding.hent_arkiverede()[0].arkiveret, dato())
        self.t.offboarding.aktiver(arkiveret)
        self.assertEqual(len(self.t.offboarding.hent_aktive()), 1)

    def test_halvt_arkiveret_sag_vises_som_arkiveret(self):
        sag = self.ny_offboarding()
        aktive = json.loads((self.central / stier.OFFBOARDING_AKTIVE).read_text("utf-8"))
        (self.central / stier.OFFBOARDING_ARKIV).write_text(json.dumps(aktive), "utf-8")
        self.assertEqual(self.t.offboarding.hent_aktive(), [])
        self.assertEqual(self.t.offboarding.hent_arkiverede()[0].id, sag.id)


class MigreringTest(TjenesteTest):
    def test_gamle_poster_faar_stabile_id_og_backup_tages_foerst(self):
        gammel = [{"loennr": "5", "navn": "Gammel", "fratraedelsesdato": dato(-3),
                   "status": "Afviklet", "kommentar": "behold mig"}]
        (self.central / stier.OFFBOARDING_AKTIVE).write_text(json.dumps(gammel), "utf-8")
        from app.bootstrap import klargoer
        klargoer(self.t)
        data = json.loads((self.central / stier.OFFBOARDING_AKTIVE).read_text("utf-8"))
        self.assertTrue(data[0]["id"])
        self.assertEqual(data[0]["kommentar"], "behold mig")
        self.assertEqual(data[0]["status"], "Afviklet")
        id_foer = data[0]["id"]
        klargoer(self.t)   # anden opstart: id må ikke ændre sig
        data = json.loads((self.central / stier.OFFBOARDING_AKTIVE).read_text("utf-8"))
        self.assertEqual(data[0]["id"], id_foer)
        self.assertTrue(any(b.aarsag == "foer-migrering" for b in self.t.backup.liste()))


if __name__ == "__main__":
    unittest.main()
