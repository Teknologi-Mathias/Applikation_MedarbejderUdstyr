"""Integrationstest: Supabase-repositories + SQL-migreringer + RLS i en LOKAL database.

Køres kun, når den lokale testdatabase kører (tools/lokal_testdatabase.py) og
INBASE_LOKAL_PGRST_URL er sat – ellers springes testene over. Rører aldrig
Supabase-projektet eller rigtige medarbejderdata; alle navne er fiktive.

Dækker: delte data mellem brugere, opret/rediger/arkivér, opgaver og
tidslinje, skabeloner, optimistisk låsning, RLS (konto uden profil, anonym,
almindelig bruger vs. administrator), forsøg på at ændre egen rolle og
insert-only tidslinje.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import uuid

from app import session
from app.domain import historik
from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave
from app.repositories.fejl import DataFejl, KonfliktFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.konto_repository import SupabaseKontoRepository
from app.repositories.supabase.opsaetning_repository import (
    SupabaseIndstillingRepository,
    SupabasePraeferenceRepository,
    SupabaseSkabelonRepository,
)
from app.repositories.supabase.sag_repository import SupabaseSagRepository
from app.services.indstillinger_service import IndstillingerService
from app.services.offboarding_service import OffboardingService
from app.services.onboarding_service import OnboardingService
from app.services.skabelon_service import SkabelonService
from tests.hjaelp import dato

URL = os.environ.get("INBASE_LOKAL_PGRST_URL", "")
HEMMELIGHED = "lokal-test-hemmelighed-kun-til-docker-0123456789"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt(rolle: str, sub: str | None = None) -> str:
    hoved = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    krop = {"role": rolle, "exp": int(time.time()) + 3600}
    if sub:
        krop["sub"] = sub
    krop = _b64(json.dumps(krop).encode())
    signatur = hmac.new(HEMMELIGHED.encode(), f"{hoved}.{krop}".encode(), hashlib.sha256).digest()
    return f"{hoved}.{krop}.{_b64(signatur)}"


def klient(token: str | None):
    from postgrest import SyncPostgrestClient
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return SyncPostgrestClient(URL, headers=headers)


class Bruger:
    """En testbruger med egen forbindelse og egne services (som en anden pc)."""

    def __init__(self, service_klient, rolle="Bruger", profil=True):
        endelse = uuid.uuid4().hex[:8]
        self.brugernavn = f"test_{endelse}" if profil else None
        self.id = service_klient.rpc("test_opret_konto", {
            "p_email": f"{endelse}@test.invalid", "p_username": self.brugernavn,
            "p_role": rolle}).execute().data
        self.klient = klient(jwt("authenticated", self.id))
        self.offboarding = OffboardingService(SupabaseSagRepository(self.klient, Medarbejder))
        self.onboarding = OnboardingService(SupabaseSagRepository(self.klient, OnboardingForloeb))
        self.skabeloner = SkabelonService(SupabaseSkabelonRepository(self.klient))
        self.indstillinger = IndstillingerService(SupabaseIndstillingRepository(self.klient),
                                                  SupabasePraeferenceRepository(self.klient))
        self.konto = SupabaseKontoRepository(self.klient)

    def aktiv(self):
        """Gør brugeren til den, der står i tidslinjen (som efter log på)."""
        session.log_ind({"brugernavn": self.brugernavn, "rolle": "Bruger"})
        return self


@unittest.skipUnless(URL, "Lokal testdatabase kører ikke (se tools/lokal_testdatabase.py)")
class SupabaseLokalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        historik.saet_brugerkilde(session.brugernavn)
        cls.service = klient(jwt("service_role"))
        cls.admin = Bruger(cls.service, "Administrator")
        cls.anne = Bruger(cls.service)
        cls.bo = Bruger(cls.service)
        cls.uden_profil = Bruger(cls.service, profil=False)

    def tearDown(self):
        session.log_ud()

    def ny_offboarding(self, bruger, navn="Testperson Fiktiv"):
        bruger.aktiv()
        sag = bruger.offboarding.ny_sag({
            "loennr": f"T{uuid.uuid4().hex[:6]}", "navn": navn,
            "fratraedelsesdato": dato(-3), "email": "fiktiv@test.invalid"})
        skabelon = next(s for s in bruger.skabeloner.sagsskabeloner("offboarding")
                        if s["navn"] == "Standard")
        return bruger.offboarding.opret(sag, skabelon)

    # ----- delte data og sagsforløb ----------------------------------------

    def test_ny_bruger_ser_kollegers_sager(self):
        sag = self.ny_offboarding(self.anne)
        self.assertEqual(sag.version, 1)
        hos_bo = self.bo.offboarding.hent(sag.id)
        self.assertIsNotNone(hos_bo)
        self.assertEqual(hos_bo.navn, sag.navn)
        self.assertEqual(len(hos_bo.opgaver), 5)
        self.assertIn(sag.id, [s.id for s in self.bo.offboarding.hent_aktive()])

    def test_opgaver_tidslinje_og_arkivering(self):
        sag = self.ny_offboarding(self.anne)
        opgave = sag.opgaver[1]
        self.bo.aktiv()
        sag = self.bo.offboarding.hent(sag.id)
        sag = self.bo.offboarding.marker_opgave_udfoert(sag, opgave.id)
        self.assertEqual(sag.version, 2)

        hentet = self.anne.offboarding.hent(sag.id)
        self.assertEqual(hentet.find_opgave(opgave.id).status, Opgave.UDFOERT)
        self.assertEqual(hentet.status, Medarbejder.STATUS_DELVIST)
        self.assertTrue(hentet.historik.er_intakt(), "hash-kæden skal overleve databasen")
        self.assertEqual([h["bruger"] for h in hentet.historik.haendelser()][-1],
                         self.bo.brugernavn)

        self.anne.aktiv()
        arkiveret = self.anne.offboarding.arkiver(hentet, "Test")
        self.assertNotIn(sag.id, [s.id for s in self.bo.offboarding.hent_aktive()])
        self.assertIn(sag.id, [s.id for s in self.bo.offboarding.hent_arkiverede()])
        aktiv = self.anne.offboarding.aktiver(arkiveret)
        self.assertIn(aktiv.id, [s.id for s in self.bo.offboarding.hent_aktive()])

    def test_onboarding_med_stilling_og_omraade(self):
        self.anne.aktiv()
        s = self.anne.onboarding
        sag = s.ny_sag({"navn": "Kandidat Fiktiv", "stilling": "FM", "omraade": "Område Nord",
                        "ansaettelsesdato": dato(10), "ansvarlig": "HR"})
        sag = s.opret(sag, self.anne.skabeloner.sagsskabeloner("onboarding", "FM")[0])
        hentet = self.bo.onboarding.hent(sag.id)
        self.assertEqual((hentet.stilling, hentet.omraade, hentet.loennr), ("FM", "Område Nord", ""))
        self.assertEqual(hentet.status, OnboardingForloeb.STATUS_KANDIDAT)
        self.assertEqual(hentet.skabelon["navn"], "Onboarding – FM/DM")

    def test_samtidig_aendring_giver_konflikt(self):
        sag = self.ny_offboarding(self.anne)
        anne_udgave = self.anne.offboarding.hent(sag.id)
        bo_udgave = self.bo.offboarding.hent(sag.id)
        self.anne.aktiv()
        self.anne.offboarding.tilfoej_notat(anne_udgave, "Annes ændring")
        self.bo.aktiv()
        with self.assertRaises(KonfliktFejl):
            self.bo.offboarding.tilfoej_notat(bo_udgave, "Bos ændring")
        # Annes ændring er bevaret, Bos er ikke gemt.
        noter = [h["kommentar"] for h in self.bo.offboarding.hent(sag.id).historik.haendelser()]
        self.assertIn("Annes ændring", noter)
        self.assertNotIn("Bos ændring", noter)

    def test_kun_aendrede_opgaver_sendes_og_andre_sager_er_uroerte(self):
        sag1 = self.ny_offboarding(self.anne)
        sag2 = self.ny_offboarding(self.anne)
        repo = self.anne.offboarding.repo
        signatur_foer = repo.signatur()
        forrige = repo._kendt[sag1.id][1]
        ny = sag1.kopi()
        ny.opgaver[0].ansvarlig = "HR"
        payload = mapping.rpc_payload(mapping.sag_til_raekker(ny), forrige)
        self.assertEqual([t["id"] for t in payload["tasks_upsert"]], [ny.opgaver[0].id])
        self.assertFalse(payload["tasks_replace"])
        self.anne.aktiv()
        self.anne.offboarding.gem_aendret(sag1, ny)
        self.assertNotEqual(repo.signatur(), signatur_foer)
        self.assertEqual(self.bo.offboarding.hent(sag2.id).version, 1)

    # ----- RLS og rettigheder ----------------------------------------------

    def test_konto_uden_profil_ser_intet_og_kan_intet(self):
        self.ny_offboarding(self.anne)
        self.assertEqual(self.uden_profil.offboarding.hent_aktive(), [])
        self.assertEqual(self.uden_profil.skabeloner.hent_alle()[sk.SAG], [])
        sag = Medarbejder("X1", "Uvedkommende", dato(0))
        with self.assertRaises(DataFejl):
            self.uden_profil.offboarding.repo.gem(sag)

    def test_anonym_har_ingen_adgang(self):
        anonym = SupabaseSagRepository(klient(None), Medarbejder)
        with self.assertRaises(DataFejl):
            anonym.hent_aktive()

    def test_bruger_kan_ikke_aendre_egen_rolle_men_eget_tema(self):
        with self.assertRaises(Exception):
            self.anne.klient.table("user_profiles").update({"role": "Administrator"}) \
                .eq("id", self.anne.id).execute()
        self.anne.indstillinger.gem_praeference(self.anne.brugernavn, tema="lys")
        self.assertEqual(self.anne.indstillinger.praeference(self.anne.brugernavn)["tema"], "lys")
        profil = self.anne.konto.profil(self.anne.id)
        self.assertEqual(profil["rolle"], "Bruger")

    def test_bruger_ser_kun_egen_profil_men_navneliste(self):
        profiler = self.anne.konto.alle_profiler()
        self.assertEqual([p["brugernavn"] for p in profiler], [self.anne.brugernavn])
        katalog = [b["brugernavn"] for b in self.anne.konto.katalog()]
        self.assertIn(self.bo.brugernavn, katalog)
        self.assertNotIn("email", self.anne.konto.katalog()[0])
        self.assertGreaterEqual(len(self.admin.konto.alle_profiler()), 3)

    def test_kun_administrator_aendrer_opsaetning(self):
        self.anne.aktiv()
        with self.assertRaises(DataFejl):
            self.anne.indstillinger.opdater(stillestaaende_dage=99)
        with self.assertRaises(DataFejl):
            self.anne.skabeloner.gem(sk.MAIL, sk.ny_skabelon(sk.MAIL))
        self.admin.aktiv()
        nyt_omraade = f"Område Test {uuid.uuid4().hex[:4]}"
        ind = self.admin.indstillinger.hent()
        self.admin.indstillinger.opdater(stillestaaende_dage=21,
                                         omraader=ind["omraader"] + [nyt_omraade])
        hos_bo = self.bo.indstillinger.hent()
        self.assertEqual(hos_bo["stillestaaende_dage"], 21)
        self.assertIn(nyt_omraade, hos_bo["omraader"])
        self.admin.indstillinger.opdater(omraader=ind["omraader"])
        self.assertNotIn(nyt_omraade, self.bo.indstillinger.hent()["omraader"])

    def test_tidslinjen_kan_ikke_aendres_eller_forfalskes(self):
        sag = self.ny_offboarding(self.anne)
        haendelser = self.anne.klient.table("audit_events").select("id").eq(
            "case_id", sag.id).execute().data
        self.assertTrue(haendelser)
        for forsoeg in (
            lambda: self.anne.klient.table("audit_events").update({"comment": "ændret"})
            .eq("case_id", sag.id).execute(),
            lambda: self.anne.klient.table("audit_events").delete().eq("case_id", sag.id).execute(),
            lambda: self.anne.klient.table("audit_events").insert({
                "case_id": sag.id, "sequence": 999, "occurred_at": "2026-01-01T00:00:00Z",
                "actor": "x", "action": "falsk"}).execute(),
        ):
            with self.assertRaises(Exception):
                forsoeg()
        # Hændelser i en andens navn afvises af RPC'en.
        ny = sag.kopi()
        ny.historik.tilfoej("Falsk", bruger=self.bo.brugernavn)
        with self.assertRaises(DataFejl):
            self.anne.offboarding.repo.gem(ny)

    def test_direkte_skrivning_i_sager_er_blokeret(self):
        sag = self.ny_offboarding(self.anne)
        with self.assertRaises(Exception):
            self.anne.klient.table("lifecycle_cases").update({"comment": "uden om"}) \
                .eq("id", sag.id).execute()

    def test_permanent_sletning_kun_for_administratorer(self):
        sag = self.ny_offboarding(self.anne)
        with self.assertRaises(DataFejl):
            self.anne.offboarding.slet(sag)
        self.admin.offboarding.slet(self.admin.offboarding.hent(sag.id))
        self.assertIsNone(self.bo.offboarding.hent(sag.id))
        person = self.service.table("people").select("id").eq("id", sag.person_id).execute()
        self.assertEqual(person.data, [], "persondata skal slettes med sagen")

    # ----- skabeloner --------------------------------------------------------

    def test_skabelon_versioneres_og_deles(self):
        self.admin.aktiv()
        ny = sk.ny_skabelon(sk.SAG, "offboarding")
        ny["navn"] = f"Test {uuid.uuid4().hex[:6]}"
        ny["opgaver"] = [{"navn": "Opgave A", "ansvarlig": "HR", "frist_dage": "3"}]
        gemt = self.admin.skabeloner.gem(sk.SAG, sk.klargoer(ny, sk.SAG))
        aendret = dict(gemt, opgaver=gemt["opgaver"] + [{"navn": "Opgave B", "frist_dage": 5}])
        self.admin.skabeloner.gem(sk.SAG, sk.klargoer(aendret, sk.SAG))
        hos_bo = next(s for s in self.bo.skabeloner.hent_alle()[sk.SAG] if s["id"] == gemt["id"])
        self.assertEqual(hos_bo["version"], 2)
        self.assertEqual([o["navn"] for o in hos_bo["opgaver"]], ["Opgave A", "Opgave B"])
        self.assertEqual(hos_bo["opgaver"][0]["frist_dage"], 3)
        self.assertEqual(len(hos_bo["versioner"]), 1)


if __name__ == "__main__":
    unittest.main()
