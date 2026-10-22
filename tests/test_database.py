"""Central Supabase-konfiguration, valg af backend og forbindelse (uden netværk)."""
import base64
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.bootstrap import byg_fra_konfiguration
from app.infrastructure.database import connection
from app.infrastructure.database.config import (
    BACKEND_JSON,
    BACKEND_SUPABASE,
    KonfigurationsFejl,
    hent_konfiguration,
)
from app.infrastructure.database.connection import DatabaseIkkeTilgaengelig, opret_klient

URL = "https://eksempel.supabase.co"
OFFENTLIG = "sb_publishable_test123"


def _jwt(rolle: str) -> str:
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'HS256'})}.{b64({'role': rolle})}.signatur"


class KonfigurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="inbase-konfig-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        connection.nulstil_klient()

    def test_privilegerede_noegler_afvises(self):
        for navn in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", "DATABASE_PASSWORD"):
            with self.subTest(navn), self.assertRaises(KonfigurationsFejl):
                hent_konfiguration({navn: "hemmelig"}, filer=[])

    def test_secret_noegle_som_anon_noegle_afvises(self):
        for noegle in ("sb_secret_abc", _jwt("service_role")):
            with self.subTest(noegle[:10]), self.assertRaises(KonfigurationsFejl):
                hent_konfiguration({"INBASE_SUPABASE_URL": URL,
                                    "INBASE_SUPABASE_ANON_KEY": noegle}, filer=[])
        # Den offentlige (legacy) anon-JWT er tilladt.
        konfig = hent_konfiguration({"INBASE_SUPABASE_URL": URL,
                                     "INBASE_SUPABASE_ANON_KEY": _jwt("anon")}, filer=[])
        self.assertTrue(konfig.er_konfigureret)

    def test_manglende_konfiguration_giver_tydelig_fejl(self):
        konfig = hent_konfiguration({}, filer=[])
        self.assertFalse(konfig.er_konfigureret)
        self.assertEqual(konfig.backend, BACKEND_SUPABASE)
        with self.assertRaises(DatabaseIkkeTilgaengelig):
            opret_klient(konfig)
        # Ingen stiltiende skift til JSON: programmet kræver konfigurationen.
        with self.assertRaises(KonfigurationsFejl) as fejl:
            byg_fra_konfiguration(konfig)
        self.assertIn(".env", str(fejl.exception))

    def test_ugyldig_backend_og_url_afvises(self):
        with self.assertRaises(KonfigurationsFejl):
            hent_konfiguration({"INBASE_BACKEND": "excel"}, filer=[])
        with self.assertRaises(KonfigurationsFejl):
            hent_konfiguration({"INBASE_SUPABASE_URL": "http://eksempel.supabase.co"}, filer=[])

    def test_env_fil_laeses_og_miljoeet_vinder(self):
        fil = self.tmp / ".env"
        fil.write_text(f"INBASE_SUPABASE_URL={URL}\nINBASE_SUPABASE_ANON_KEY=fra_fil\n",
                       encoding="utf-8")
        konfig = hent_konfiguration({}, filer=[fil])
        self.assertEqual((konfig.url, konfig.anon_noegle), (URL, "fra_fil"))
        self.assertEqual(konfig.kilder, (str(fil),))
        konfig = hent_konfiguration({"INBASE_SUPABASE_ANON_KEY": OFFENTLIG}, filer=[fil])
        self.assertEqual(konfig.anon_noegle, OFFENTLIG)

    def test_klienten_oprettes_eet_sted_og_genbruges(self):
        konfig = hent_konfiguration({"INBASE_SUPABASE_URL": URL,
                                     "INBASE_SUPABASE_ANON_KEY": OFFENTLIG}, filer=[])
        klient = opret_klient(konfig)
        self.assertIs(opret_klient(konfig), klient)

    def test_json_kraever_eksplicit_valg(self):
        self.assertEqual(hent_konfiguration({"INBASE_BACKEND": "json"}, filer=[]).backend,
                         BACKEND_JSON)


class BackendValgTest(unittest.TestCase):
    def tearDown(self):
        connection.nulstil_klient()

    def test_supabase_vaelges_naar_konfigureret(self):
        konfig = hent_konfiguration({"INBASE_SUPABASE_URL": URL,
                                     "INBASE_SUPABASE_ANON_KEY": OFFENTLIG}, filer=[])
        t = byg_fra_konfiguration(konfig)
        self.assertEqual(t.backend, BACKEND_SUPABASE)
        self.assertIsNone(t.datakilde)
        self.assertIsNone(t.backup)
        self.assertFalse(t.lagring.understoetter_offline)
        self.assertEqual(type(t.offboarding.repo).__name__, "SupabaseSagRepository")
        self.assertEqual(type(t.auth).__name__, "SupabaseAuthService")


if __name__ == "__main__":
    unittest.main()
