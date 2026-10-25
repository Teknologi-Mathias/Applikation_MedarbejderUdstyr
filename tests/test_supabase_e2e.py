"""End-to-end mod en KONTROLLERET Supabase (Auth + Edge Functions + database).

Opretter og sletter testkonti. Køres derfor KUN, når alle disse er sat:

    INBASE_E2E_URL              fx http://127.0.0.1:54321 (lokal `supabase start`)
    INBASE_E2E_ANON_KEY         projektets publishable/anon-nøgle
    INBASE_E2E_ADMIN_USERNAME   en administrator (oprettet med bootstrap-proceduren)
    INBASE_E2E_ADMIN_PASSWORD
    INBASE_E2E_OPRET_BRUGERE=1  udtrykkelig tilladelse til at oprette/slette testkonti
    INBASE_E2E_SERVICE_KEY      (valgfri) kun til test af genoptagelse af en afbrudt oprettelse

Kræver migreringerne 001-006 og de deployede Edge Functions.

Brug ALDRIG produktionsprojektet med rigtige medarbejderdata. Se
docs/SUPABASE_OPSAETNING.md, afsnit "Test".
"""
import os
import unittest
import uuid

import httpx

from app import session
from app.bootstrap import byg_supabase_tjenester
from app.domain.opgave import Opgave
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.repositories.supabase.mapping import login_alias
from tests.hjaelp import dato

E = {k: os.environ.get(f"INBASE_E2E_{k}", "") for k in
     ("URL", "ANON_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "OPRET_BRUGERE", "SERVICE_KEY")}
AKTIV = all(E[k] for k in ("URL", "ANON_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD")) \
    and E["OPRET_BRUGERE"] == "1"


def ny_pc():
    """Én installation af IN-BASE: egen klient og egne services."""
    from supabase import ClientOptions, create_client
    klient = create_client(E["URL"], E["ANON_KEY"],
                           options=ClientOptions(persist_session=False))
    return byg_supabase_tjenester(klient, lokal_mappe=__import__("pathlib").Path(
        __import__("tempfile").mkdtemp(prefix="inbase-e2e-")))


@unittest.skipUnless(AKTIV, "E2E-miljøet er ikke sat op (se docstring)")
class SupabaseE2ETest(unittest.TestCase):
    def setUp(self):
        self.admin = ny_pc()
        bruger = self.admin.auth.log_ind(E["ADMIN_USERNAME"], E["ADMIN_PASSWORD"])
        self.assertEqual(bruger["rolle"], "Administrator")
        session.log_ind(bruger)
        self.navn, self.kode = f"E2E_{uuid.uuid4().hex[:6].upper()}", "Midlertidig-1"
        self.oprydning = []

    def tearDown(self):
        session.log_ind(self.admin.auth._aktuel)
        for funktion in reversed(self.oprydning):
            try:
                funktion()
            except Exception as fejl:   # oprydning må ikke skjule testens egentlige fejl
                print("Oprydning fejlede:", fejl)
        self.admin.auth.log_ud()
        session.log_ud()

    def opret_bruger(self):
        self.admin.auth.opret(self.navn.lower(), "E2E Testbruger", "Bruger", self.kode)
        self.oprydning.append(lambda: self.admin.auth.slet(self.navn, "chef"))

    def test_administrator_opretter_bruger_som_logger_paa_fra_anden_pc(self):
        self.opret_bruger()
        profil = next(b for b in self.admin.auth.brugere() if b["brugernavn"] == self.navn)
        self.assertEqual((profil["rolle"], profil["aktiv"]), ("Bruger", True))
        self.assertTrue(profil["skal_skifte_kode"])
        self.assertNotIn("email", profil)

        pc2 = ny_pc()
        self.assertIsNone(pc2.auth.log_ind(self.navn, "forkert-kode"))
        self.assertIsNone(pc2.auth.log_ind("E2E_FINDESIKKE", self.kode))
        bruger = pc2.auth.log_ind(f"  {self.navn.lower()} ", self.kode)   # normaliseres
        self.assertTrue(bruger["skal_skifte_kode"])
        pc2.auth.skift_midlertidig_kode("Min-egen-kode-1", "Min-egen-kode-1")
        pc2.auth.log_ud()
        self.assertIsNone(pc2.auth.log_ind(self.navn, self.kode), "den midlertidige kode er udløbet")
        bruger = pc2.auth.log_ind(self.navn, "Min-egen-kode-1")
        self.assertFalse(bruger["skal_skifte_kode"])

        # Fælles data: administratoren opretter en sag – brugeren ser og ændrer den.
        sag = self.admin.offboarding.ny_sag({"loennr": f"E{uuid.uuid4().hex[:5]}",
                                             "navn": "E2E Fiktiv", "fratraedelsesdato": dato(-1)})
        skabelon = next(s for s in self.admin.skabeloner.sagsskabeloner("offboarding")
                        if s["navn"] == "Standard")
        sag = self.admin.offboarding.opret(sag, skabelon)
        self.oprydning.append(lambda: self.admin.offboarding.slet(self.admin.offboarding.hent(sag.id)))

        session.log_ind(bruger)
        hos_bruger = pc2.offboarding.hent(sag.id)
        self.assertIsNotNone(hos_bruger, "ny bruger skal se fælles sager")
        pc2.offboarding.marker_opgave_udfoert(hos_bruger, hos_bruger.opgaver[0].id)
        session.log_ind(self.admin.auth._aktuel)
        igen = self.admin.offboarding.hent(sag.id)
        self.assertEqual(igen.opgaver[0].status, Opgave.UDFOERT)
        self.assertEqual(igen.historik.haendelser()[-1]["bruger"], self.navn)
        self.assertTrue(igen.historik.er_intakt())

        # Almindelig bruger: kan ikke oprette brugere, ændre rolle eller slette sager.
        session.log_ind(bruger)
        with self.assertRaises(DataFejl):
            pc2.auth.opret("OND", "Ond", "Administrator", "Ond-kode-123")
        klient = pc2.auth.repo.klient
        with self.assertRaises(Exception):
            klient.table("user_profiles").update({"role": "Administrator"}).eq(
                "id", bruger["id"]).execute()
        self.assertEqual(pc2.auth.repo.profil(bruger["id"])["rolle"], "Bruger")
        with self.assertRaises(DataFejl):
            pc2.offboarding.slet(pc2.offboarding.hent(sag.id))
        pc2.auth.log_ud()

    def test_dublet_nulstilling_deaktivering_og_sletning(self):
        self.opret_bruger()
        with self.assertRaises(ValideringsFejl):
            self.admin.auth.opret(self.navn.lower(), "Dublet", "Bruger", self.kode)

        self.admin.auth.nulstil_kode(self.navn, "Ny-midlertidig-2")
        pc2 = ny_pc()
        self.assertTrue(pc2.auth.log_ind(self.navn, "Ny-midlertidig-2")["skal_skifte_kode"])

        # Deaktivering: den åbne session mister adgangen, og ny log på afvises.
        self.admin.auth.saet_aktiv(self.navn, False, self.admin.auth._aktuel["brugernavn"])
        self.assertEqual(pc2.offboarding.hent_aktive(), [])
        with self.assertRaises(DataFejl):
            pc2.auth.kontroller_session()
        self.assertIsNone(ny_pc().auth.log_ind(self.navn, "Ny-midlertidig-2"))
        self.admin.auth.saet_aktiv(self.navn, True, self.admin.auth._aktuel["brugernavn"])
        self.assertIsNotNone(ny_pc().auth.log_ind(self.navn, "Ny-midlertidig-2"))

        self.oprydning.pop()   # slettes nu i testen
        self.admin.auth.slet(self.navn, "chef")
        self.assertIsNone(ny_pc().auth.log_ind(self.navn, "Ny-midlertidig-2"))
        with self.assertRaises(ValideringsFejl):
            self.admin.auth.slet(self.admin.auth._aktuel["brugernavn"],
                                 self.admin.auth._aktuel["brugernavn"])

    @unittest.skipUnless(E["SERVICE_KEY"], "INBASE_E2E_SERVICE_KEY ikke sat")
    def test_afbrudt_oprettelse_genoptages(self):
        """Auth-konto uden profil (fx efter et netværksnedbrud) -> næste forsøg fuldfører."""
        nøgle = E["SERVICE_KEY"]
        svar = httpx.post(f"{E['URL']}/auth/v1/admin/users",
                          headers={"apikey": nøgle, "Authorization": f"Bearer {nøgle}"},
                          json={"email": login_alias(self.navn), "password": "Gammel-kode-9",
                                "email_confirm": True})
        self.assertEqual(svar.status_code, 200, svar.text)
        konto_uden_profil = ny_pc()
        with self.assertRaises(DataFejl):   # konto uden profil har ingen adgang
            konto_uden_profil.auth.log_ind(self.navn, "Gammel-kode-9")
        self.opret_bruger()
        bruger = ny_pc().auth.log_ind(self.navn, self.kode)
        self.assertEqual(bruger["id"], svar.json()["id"], "samme Auth-konto, nu med profil")


if __name__ == "__main__":
    unittest.main()
