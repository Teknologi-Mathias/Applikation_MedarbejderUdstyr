"""Måling af Supabase-trafikken (app/infrastructure/database/trafik.py)."""
import unittest
from unittest import mock

from app.infrastructure.database.trafik import Trafiktaeller, endpoint


class TrafikTest(unittest.TestCase):
    def test_endpoint_navne(self):
        self.assertEqual(endpoint("/rest/v1/rpc/inbase_case_signature"), "rpc/inbase_case_signature")
        self.assertEqual(endpoint("/rest/v1/lifecycle_cases"), "lifecycle_cases")
        self.assertEqual(endpoint("/rpc/inbase_tick"), "rpc/inbase_tick")   # lokal PostgREST

    def test_opsummering_efter_interval_nulstiller(self):
        tid = [0.0]
        taeller = Trafiktaeller(interval=60, ur=lambda: tid[0])
        taeller.registrer("/rest/v1/app_settings", 2048)
        taeller.registrer("/rest/v1/app_settings", 2048)
        self.assertEqual(taeller._kald["app_settings"], [2, 4096])
        tid[0] = 61
        with mock.patch("app.infrastructure.database.trafik.log") as log:
            taeller.registrer("/rest/v1/rpc/inbase_case_signature", 512)
        self.assertIn("app_settings 2 kald 4 KB", log.info.call_args.args[1])
        self.assertEqual(dict(taeller._kald), {})


if __name__ == "__main__":
    unittest.main()
