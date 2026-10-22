"""Databaseforberedelse: konfiguration, ærlig "ikke implementeret" og migrering."""
import json
import unittest

from app.infrastructure.database.config import KonfigurationsFejl, hent_konfiguration
from app.infrastructure.database.connection import DatabaseIkkeTilgaengelig, opret_klient
from app.infrastructure.database.migrering import byg_raekker, valider
from app.infrastructure import stier
from tests.hjaelp import TjenesteTest


class KonfigurationTest(unittest.TestCase):
    def test_privilegerede_noegler_afvises(self):
        with self.assertRaises(KonfigurationsFejl):
            hent_konfiguration({"SUPABASE_SERVICE_ROLE_KEY": "hemmelig"})

    def test_ingen_falsk_forbindelse(self):
        with self.assertRaises(DatabaseIkkeTilgaengelig):
            opret_klient(hent_konfiguration({}))
        konfig = hent_konfiguration({"INBASE_SUPABASE_URL": "https://x.supabase.co",
                                     "INBASE_SUPABASE_ANON_KEY": "anon"})
        self.assertTrue(konfig.er_konfigureret)
        with self.assertRaises(DatabaseIkkeTilgaengelig):
            opret_klient(konfig)


class MigreringTilSqlTest(TjenesteTest):
    def test_alle_data_kommer_med_og_valideres(self):
        sag = self.ny_offboarding()
        self.t.offboarding.tilfoej_notat(sag, "notat")
        f = self.ny_onboarding(stilling="FM")
        self.t.onboarding.arkiver(f)
        kilde_foer = (self.central / stier.OFFBOARDING_AKTIVE).read_text("utf-8")

        raekker = byg_raekker(self.central)
        self.assertEqual(valider(raekker, self.central), [])
        self.assertEqual(len(raekker["lifecycle_cases"]), 2)
        self.assertEqual(len(raekker["people"]), 2)
        onboarding = next(r for r in raekker["employment_records"] if r["position_id"])
        self.assertIsNone(onboarding["payroll_number"])   # kandidat uden lønnr.
        self.assertTrue(all(r["id"] is None for r in raekker["user_profiles"]))
        self.assertNotIn("hash", json.dumps(raekker["user_profiles"]))
        # Kilden er urørt, og en ny kørsel giver samme id'er.
        self.assertEqual((self.central / stier.OFFBOARDING_AKTIVE).read_text("utf-8"), kilde_foer)
        igen = byg_raekker(self.central)
        self.assertEqual([r["id"] for r in igen["case_tasks"]],
                         [r["id"] for r in raekker["case_tasks"]])

    def test_validering_opdager_manglende_data(self):
        self.ny_offboarding()
        raekker = byg_raekker(self.central)
        raekker["case_tasks"].pop()
        self.assertTrue(valider(raekker, self.central))


if __name__ == "__main__":
    unittest.main()
