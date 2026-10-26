"""Integrationstest: Supabase-repositories + SQL-migreringer + RLS i en LOKAL database.

Køres kun, når den lokale testdatabase kører (tools/lokal_testdatabase.py) og
INBASE_LOKAL_PGRST_URL er sat – ellers springes testene over. Rører aldrig
Supabase-projektet eller rigtige medarbejderdata; alle navne er fiktive.

Dækker: delte data mellem brugere, opret/rediger/arkivér, opgaver og
tidslinje, skabeloner, optimistisk låsning, RLS (konto uden profil, anonym,
almindelig bruger vs. administrator, deaktiveret bruger), forsøg på at ændre
egen rolle/status, insert-only tidslinje og Ønsker & Udvikling (indsender fra
login, behandling kun for administratorer – også uden om programmet –,
statusregler, kommentarer/interne noter, historik og sletning).
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
from app.repositories.fejl import DataFejl, KonfliktFejl, SessionUdloebetFejl, ValideringsFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.indmelding_repository import SupabaseIndmeldingRepository
from app.repositories.supabase.konto_repository import SupabaseKontoRepository
from app.repositories.supabase.opsaetning_repository import (
    SupabaseIndstillingRepository,
    SupabasePraeferenceRepository,
    SupabaseSkabelonRepository,
)
from app.repositories.supabase.sag_repository import SupabaseSagRepository
from app.services.auth_service import SupabaseAuthService
from app.services.indmelding_service import IndmeldingService
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
        navn = f"TEST_{uuid.uuid4().hex[:8].upper()}"
        self.brugernavn = navn if profil else None
        self.rolle = rolle
        self.id = service_klient.rpc("test_opret_konto", {
            "p_username": navn, "p_role": rolle, "p_profil": profil}).execute().data
        self.klient = klient(jwt("authenticated", self.id))
        self.offboarding = OffboardingService(SupabaseSagRepository(self.klient, Medarbejder))
        self.onboarding = OnboardingService(SupabaseSagRepository(self.klient, OnboardingForloeb))
        self.skabeloner = SkabelonService(SupabaseSkabelonRepository(self.klient))
        self.indstillinger = IndstillingerService(SupabaseIndstillingRepository(self.klient),
                                                  SupabasePraeferenceRepository(self.klient))
        self.konto = SupabaseKontoRepository(self.klient)
        self.indmeldinger = IndmeldingService(
            SupabaseIndmeldingRepository(self.klient),
            lambda: {"brugernavn": self.brugernavn, "rolle": self.rolle})

    def aktiv(self):
        """Gør brugeren til den, der står i tidslinjen (som efter log på)."""
        session.log_ind({"brugernavn": self.brugernavn, "rolle": self.rolle})
        return self


def s_skabelon(bruger):
    return next(s for s in bruger.skabeloner.sagsskabeloner("onboarding", "DM")
                if "arbejdsspor" in s["navn"])


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
        self.assertEqual(hentet.skabelon["navn"], "Onboarding – arbejdsspor FM/DM")

    def test_samtidige_uafhaengige_aendringer_flettes(self):
        sag = self.ny_offboarding(self.anne)
        anne_udgave = self.anne.offboarding.hent(sag.id)
        bo_udgave = self.bo.offboarding.hent(sag.id)
        self.anne.aktiv()
        self.anne.offboarding.tilfoej_notat(anne_udgave, "Annes ændring")
        self.bo.aktiv()
        self.bo.offboarding.marker_opgave_udfoert(bo_udgave, bo_udgave.opgaver[0].id)
        hentet = self.anne.offboarding.hent(sag.id)
        noter = [h["kommentar"] for h in hentet.historik.haendelser()]
        self.assertIn("Annes ændring", noter)
        self.assertEqual(hentet.opgaver[0].status, "Udført")
        self.assertTrue(hentet.historik.er_intakt())

    def test_samtidig_aendring_af_samme_felt_giver_konflikt(self):
        sag = self.ny_offboarding(self.anne)
        anne_udgave = self.anne.offboarding.hent(sag.id)
        bo_udgave = self.bo.offboarding.hent(sag.id)
        self.anne.aktiv()
        self.anne.offboarding.aendr_frist(anne_udgave, sag.opgaver[1].id, dato(5))
        self.bo.aktiv()
        with self.assertRaises(KonfliktFejl):
            self.bo.offboarding.aendr_frist(bo_udgave, sag.opgaver[1].id, dato(9))
        # Annes ændring er bevaret, Bos er ikke gemt.
        self.assertEqual(self.bo.offboarding.hent(sag.id).opgaver[1].frist, dato(5))

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

    def test_kun_administrator_saetter_afdelinger_og_de_vises_i_navnelisten(self):
        with self.assertRaises(DataFejl):
            self.anne.konto.saet_afdelinger(self.anne.id, ["HR"])
        with self.assertRaises(Exception):
            self.anne.klient.table("user_profiles").update({"roles": ["HR"]})                 .eq("id", self.anne.id).execute()
        self.admin.konto.saet_afdelinger(self.anne.id, ["Merch", "HR", "HR"])
        self.assertEqual(self.anne.konto.profil(self.anne.id)["roller"], ["HR", "Merch"])
        katalog = {b["brugernavn"]: b for b in self.bo.konto.katalog()}
        self.assertEqual(katalog[self.anne.brugernavn]["roller"], ["HR", "Merch"])
        self.admin.konto.saet_afdelinger(self.anne.id, [])

    def test_behov_og_arbejdsspor_gemmes(self):
        self.anne.aktiv()
        s = self.anne.onboarding
        sag = s.ny_sag({"navn": "Kandidat Behov", "stilling": "DM", "omraade": "Område Nord",
                        "ansaettelsesdato": dato(10),
                        "behov": {"polo": {"valgt": True, "stoerrelse": "M", "antal": 2},
                                  "mobil": True, "abonnement": "Tale og data"}})
        sag = s.opret(sag, s_skabelon(self.anne), {"oplaering_planlagt": "2026-12-01T08:00:00"})
        hentet = self.bo.onboarding.hent(sag.id)
        self.assertEqual(hentet.behov.til_dict(), sag.behov.til_dict())
        efter = {o.noegle: o for o in hentet.opgaver}
        self.assertEqual(efter["oplaering_booket"].planlagt, "2026-12-01T08:00:00")
        self.assertEqual((efter["telefon"].afhaenger_af, efter["telefon"].afdeling),
                         (["kontrakt"], "Administration"))
        self.assertEqual(efter["firmabil"].status, "Undtaget")

    def test_bruger_ser_kun_egen_profil_men_navneliste(self):
        profiler = self.anne.konto.alle_profiler()
        self.assertEqual([p["brugernavn"] for p in profiler], [self.anne.brugernavn])
        katalog = [b["brugernavn"] for b in self.anne.konto.katalog()]
        self.assertIn(self.bo.brugernavn, katalog)
        self.assertNotIn("email", self.anne.konto.katalog()[0])
        self.assertGreaterEqual(len(self.admin.konto.alle_profiler()), 3)

    def test_alle_aendrer_opsaetning_men_kun_administrator_data(self):
        self.anne.aktiv()
        self.anne.indstillinger.opdater(stillestaaende_dage=14)
        self.anne.skabeloner.gem(sk.MAIL, sk.ny_skabelon(sk.MAIL))
        with self.assertRaises(DataFejl):
            self.anne.indstillinger.opdater(backup_antal=99)
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

    # ----- brugernavne og deaktivering -------------------------------------

    def test_profiler_har_normaliseret_brugernavn_og_ingen_email(self):
        profil = self.anne.konto.profil(self.anne.id)
        self.assertEqual(profil["brugernavn"], self.anne.brugernavn)
        self.assertTrue(profil["aktiv"])
        raekke = self.anne.klient.table("user_profiles").select("*").eq(
            "id", self.anne.id).execute().data[0]
        self.assertNotIn("email", raekke)

    def test_bruger_kan_ikke_aendre_egen_status_brugernavn_eller_rolle(self):
        for felter in ({"active": False}, {"username": "ANDET"}, {"role": "Administrator"},
                       {"must_change_password": False}):
            with self.subTest(felter), self.assertRaises(Exception):
                self.anne.klient.table("user_profiles").update(felter) \
                    .eq("id", self.anne.id).execute()

    def test_deaktiveret_bruger_mister_adgangen_med_det_samme(self):
        cecilie = Bruger(self.service)
        sag = self.ny_offboarding(self.anne)
        ind = self.ny_indmelding(self.anne)
        self.assertIsNotNone(cecilie.offboarding.hent(sag.id))
        self.service.rpc("test_saet_aktiv", {"p_id": cecilie.id, "p_active": False}).execute()
        # Samme, stadig gyldige token: RLS lukker for alle data.
        self.assertIsNone(cecilie.offboarding.hent(sag.id))
        self.assertIsNone(cecilie.indmeldinger.hent(ind.id))
        cecilie.aktiv()
        with self.assertRaises(DataFejl):
            cecilie.offboarding.repo.gem(sag)
        with self.assertRaises(DataFejl):
            cecilie.indmeldinger.repo.tilfoej_kommentar(ind.id, "Efter deaktivering", False)
        # Egen profil kan stadig læses, så programmet opdager det og logger ud.
        auth = SupabaseAuthService(cecilie.konto)
        auth._aktuel = cecilie.konto.profil(cecilie.id)
        self.assertFalse(auth._aktuel["aktiv"])
        with self.assertRaises(SessionUdloebetFejl):
            auth.kontroller_session()
        self.assertNotIn(cecilie.brugernavn, [b["brugernavn"] for b in self.anne.konto.katalog()])

    # ----- Ønsker & Udvikling ----------------------------------------------

    def ny_indmelding(self, bruger, titel="Fiktiv fejl i eksport"):
        bruger.aktiv()
        return bruger.indmeldinger.opret({"titel": titel, "kategori": "Fejlmelding",
                                          "beskrivelse": "Fiktiv testbeskrivelse"})

    def test_indmelding_faar_indsender_fra_login_og_deles(self):
        ind = self.ny_indmelding(self.anne)
        self.assertEqual((ind.indsender, ind.status, ind.prioritet, ind.version),
                         (self.anne.brugernavn, "Indsendt", "Normal", 1))
        self.assertGreater(ind.nummer, 0)
        self.assertEqual(self.bo.indmeldinger.hent(ind.id).titel, "Fiktiv fejl i eksport")
        self.assertIn(ind.id, [i.id for i in self.bo.indmeldinger.hent_alle()])
        # RPC'en ignorerer forsøg på at angive indsender, status og prioritet.
        raekke = self.bo.klient.rpc("inbase_create_request", {"p_request": {
            "title": "Snyd", "category": "Andet", "description": "x",
            "submitted_by_username": self.admin.brugernavn, "submitted_by": self.admin.id,
            "status": "Udgivet", "priority": "Kritisk"}}).execute().data
        self.assertEqual((raekke["submitted_by_username"], raekke["submitted_by"], raekke["status"],
                          raekke["priority"]), (self.bo.brugernavn, self.bo.id, "Indsendt", "Normal"))
        historik = self.bo.indmeldinger.detaljer(ind.id).historik
        self.assertEqual([(a.handling, a.bruger) for a in historik],
                         [("oprettet", self.anne.brugernavn)])

    def test_kun_administrator_behandler_ogsaa_uden_om_programmet(self):
        ind = self.ny_indmelding(self.anne)
        repo = self.anne.indmeldinger.repo          # direkte – uden servicens kontrol
        for aendring in ({"status": "Til vurdering"}, {"prioritet": "Kritisk"},
                         {"ansvarlig": self.anne.brugernavn}, {"loesning": "Løst"}):
            with self.subTest(aendring), self.assertRaises(DataFejl):
                repo.opdater(ind.id, ind.version, aendring)
        with self.assertRaises(DataFejl):           # andres tekst
            self.bo.indmeldinger.repo.opdater(ind.id, ind.version, {"titel": "Overtaget"})
        ind = repo.opdater(ind.id, ind.version, {"titel": "Rettet af indsender"})
        self.admin.aktiv()
        ind = self.admin.indmeldinger.opdater(ind, {
            "status": "Til vurdering", "prioritet": "Høj",
            "ansvarlig": self.bo.brugernavn.lower(), "planlagt_version": "V0.8"})
        self.assertEqual((ind.status, ind.prioritet, ind.ansvarlig, ind.version),
                         ("Til vurdering", "Høj", self.bo.brugernavn, 3))
        with self.assertRaises(DataFejl):           # ikke længere Indsendt
            repo.opdater(ind.id, ind.version, {"titel": "For sent"})
        historik = self.bo.indmeldinger.detaljer(ind.id).historik
        self.assertEqual([(a.felt, a.bruger) for a in historik if a.handling == "aendret"],
                         [("titel", self.anne.brugernavn), ("status", self.admin.brugernavn),
                          ("prioritet", self.admin.brugernavn), ("ansvarlig", self.admin.brugernavn),
                          ("planlagt_version", self.admin.brugernavn)])
        # Direkte skrivning i tabellerne er blokeret – også for administratorer.
        for forsoeg in (
            lambda: self.admin.klient.table("development_requests").update(
                {"status": "Udgivet"}).eq("id", ind.id).execute(),
            lambda: self.anne.klient.table("development_requests").insert(
                {"title": "x", "category": "Andet", "submitted_by_username": "x"}).execute(),
            lambda: self.admin.klient.table("development_request_events").insert(
                {"request_id": ind.id, "actor_username": "x", "action": "aendret"}).execute(),
            lambda: self.admin.klient.table("development_request_events").delete().eq(
                "request_id", ind.id).execute(),
            lambda: self.anne.klient.table("development_request_comments").insert(
                {"request_id": ind.id, "author_username": "x", "body": "x"}).execute(),
        ):
            with self.assertRaises(Exception):
                forsoeg()

    def test_statusregler_og_konflikt_haandhaeves_af_databasen(self):
        ind = self.ny_indmelding(self.anne)
        repo = self.admin.indmeldinger.repo
        for aendring in ({"status": "Udgivet"},          # springer trin over
                         {"status": "Afvist"},           # mangler begrundelse
                         {"ansvarlig": "FINDES_IKKE"},
                         {"prioritet": "Akut"}):
            with self.subTest(aendring), self.assertRaises(ValideringsFejl):
                repo.opdater(ind.id, ind.version, aendring)
        repo.opdater(ind.id, ind.version, {"prioritet": "Lav"})
        with self.assertRaises(KonfliktFejl):
            repo.opdater(ind.id, ind.version, {"prioritet": "Høj"})
        self.assertEqual(self.bo.indmeldinger.hent(ind.id).prioritet, "Lav")
        afvist = repo.opdater(ind.id, ind.version + 1, {"status": "Afvist", "loesning": "Dækkes af ERP"})
        self.assertEqual(afvist.status, "Afvist")

    def test_kommentarer_og_interne_noter(self):
        ind = self.ny_indmelding(self.anne)
        self.anne.indmeldinger.repo.tilfoej_kommentar(ind.id, "Offentlig kommentar", False)
        with self.assertRaises(DataFejl):
            self.anne.indmeldinger.repo.tilfoej_kommentar(ind.id, "Intern?", True)
        self.admin.indmeldinger.repo.tilfoej_kommentar(ind.id, "Intern note", True)
        hos_bo = self.bo.indmeldinger.repo.kommentarer(ind.id)
        self.assertEqual([(k.tekst, k.forfatter) for k in hos_bo],
                         [("Offentlig kommentar", self.anne.brugernavn)])
        self.assertEqual([k.tekst for k in self.admin.indmeldinger.repo.kommentarer(ind.id)],
                         ["Offentlig kommentar", "Intern note"])
        with self.assertRaises(ValideringsFejl):
            self.bo.indmeldinger.repo.tilfoej_kommentar(ind.id, "   ", False)

    def test_sletning_kun_for_administratorer_og_ingen_adgang_uden_profil(self):
        ind = self.ny_indmelding(self.anne)
        with self.assertRaises(DataFejl):
            self.anne.indmeldinger.repo.slet(ind.id)
        self.assertIsNotNone(self.bo.indmeldinger.hent(ind.id))
        self.assertEqual(self.uden_profil.indmeldinger.repo.hent_alle(), [])
        with self.assertRaises(DataFejl):
            self.uden_profil.indmeldinger.repo.opret(
                {"titel": "x", "kategori": "Andet", "beskrivelse": "x"})
        with self.assertRaises(DataFejl):
            SupabaseIndmeldingRepository(klient(None)).hent_alle()
        self.admin.indmeldinger.repo.slet(ind.id)
        self.assertIsNone(self.bo.indmeldinger.hent(ind.id))


if __name__ == "__main__":
    unittest.main()
