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
from datetime import datetime, timedelta
from unittest import mock

from app import KRAEVET_SKEMA, session
from app.domain import historik
from app.domain import kalender as kl
from app.domain import mdm_enhed as md
from app.domain import opdatering as op
from app.domain.kalender import Begivenhed, Kalender
from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opdatering import Udgivelse
from app.domain.opgave import Opgave
from app.repositories.fejl import DataFejl, KonfliktFejl, SessionUdloebetFejl, ValideringsFejl
from app.repositories.supabase import mapping
from app.repositories.supabase.indmelding_repository import SupabaseIndmeldingRepository
from app.repositories.supabase.kalender_repository import SupabaseKalenderRepository
from app.repositories.supabase.klient import kald
from app.repositories.supabase.konto_repository import SupabaseKontoRepository
from app.repositories.supabase.mdm_repository import SupabaseMdmRepository
from app.repositories.supabase.opdatering_repository import SupabaseOpdateringRepository
from app.repositories.supabase.opsaetning_repository import (
    SupabaseIndstillingRepository,
    SupabasePraeferenceRepository,
    SupabaseSkabelonRepository,
)
from app.repositories.supabase.sag_repository import SupabaseSagRepository
from app.repositories.supabase.tjek_repository import SupabaseTjekRepository
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
    """Standardskabelonen med arbejdsspor (migrering 018)."""
    return next(s for s in bruger.skabeloner.sagsskabeloner("onboarding", "DM")
                if s["navn"] == "Onboarding")


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
        # Standardskabelonen (migrering 018): HR's felter er udfyldt – kontrakten er første skridt.
        self.assertEqual(hentet.status, OnboardingForloeb.STATUS_KONTRAKT)
        self.assertEqual(hentet.skabelon["navn"], "Onboarding")

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
        self.assertEqual((efter["udstyr"].afhaenger_af, efter["udstyr"].afdeling),
                         (["kontrakt"], "Administration"))
        self.assertNotEqual(efter["udstyr"].status, "Undtaget", "polo og mobil er valgt")
        self.assertEqual(efter["firmabil"].status, "Undtaget")

    def test_bruger_ser_kun_egen_profil_men_navneliste(self):
        profiler = self.anne.konto.alle_profiler()
        self.assertEqual([p["brugernavn"] for p in profiler], [self.anne.brugernavn])
        katalog = [b["brugernavn"] for b in self.anne.konto.katalog()]
        self.assertIn(self.bo.brugernavn, katalog)
        self.assertNotIn("email", self.anne.konto.katalog()[0])
        self.assertGreaterEqual(len(self.admin.konto.alle_profiler()), 3)

    def test_alle_aendrer_opsaetning_men_kun_administrator_data(self):
        # Ny, tom database: en administrator gemmer indstillingerne første gang
        # (kendt begrænsning, docs/ARKITEKTUR.md) – derefter kan alle gemme Organisation.
        self.admin.aktiv()
        self.admin.indstillinger.opdater()
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
        # Listen har ikke versionerne med (trafik) – de hentes for sig og overlever
        # en gemning uden indholdsændring.
        self.assertEqual(hos_bo["versioner"], [])
        self.assertEqual(len(self.bo.skabeloner.repo.versioner(gemt["id"])), 1)
        self.admin.skabeloner.skift_aktiv(sk.SAG, hos_bo)
        self.assertEqual(len(self.bo.skabeloner.repo.versioner(gemt["id"])), 1)
        gammel = self.bo.skabeloner.version({"id": gemt["id"], "version": 1})
        self.assertEqual([o["navn"] for o in gammel["opgaver"]], ["Opgave A"])

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

    # ----- central opdatering og skemaversion (migrering 019) ---------------

    def test_krav_kan_laeses_foer_log_paa(self):
        krav = SupabaseOpdateringRepository(klient(jwt("anon"))).krav()
        self.assertGreaterEqual(krav["schema_version"], KRAEVET_SKEMA)
        self.assertEqual(krav["min_client_version"], "0.0.0")

    def test_signatur_skelner_aktive_og_arkiv(self):
        repo = self.anne.offboarding.repo
        foer = repo.signatur()
        sag = self.ny_offboarding(self.anne)
        efter_opret = repo.signatur()
        self.assertNotEqual(efter_opret[0], foer[0])
        self.assertEqual(efter_opret[1], foer[1], "arkivet er uændret")
        self.anne.offboarding.arkiver(sag)
        self.assertNotEqual(repo.signatur()[1], efter_opret[1])

    # ----- minut-tjekket (migrering 023) ------------------------------------

    def test_minut_tjek_i_et_kald(self):
        tjek = SupabaseTjekRepository(self.anne.klient)
        foer = tjek.signaturer()
        self.assertEqual(foer.profil["brugernavn"], self.anne.brugernavn)
        self.assertEqual(foer.sager["offboarding"], self.anne.offboarding.repo.signatur())
        self.assertEqual(foer.kalender, SupabaseKalenderRepository(self.anne.klient).signatur())
        self.ny_offboarding(self.anne)
        self.anne.skabeloner.gem(sk.MAIL, sk.ny_skabelon(sk.MAIL))
        efter = tjek.signaturer()
        self.assertNotEqual(efter.sager["offboarding"], foer.sager["offboarding"])
        self.assertEqual(efter.sager["onboarding"], foer.sager["onboarding"])
        self.assertNotEqual(efter.skabeloner, foer.skabeloner)
        self.assertEqual(efter.indstillinger, foer.indstillinger)
        self.assertIsNone(SupabaseTjekRepository(self.uden_profil.klient).signaturer().profil)

    def test_kun_aendrede_sager_hentes_og_flettes(self):
        s = self.anne.offboarding
        a, b, c = (self.ny_offboarding(self.anne) for _ in range(3))
        kendt, aktive, arkiv = s.signatur(), s.hent_aktive(), s.hent_arkiverede()
        self.assertEqual(s.opdater_lister(kendt, s.signatur(), aktive, arkiv), (None, None))

        self.bo.aktiv()          # en kollega ændrer én sag ...
        b_hos_bo = self.bo.offboarding.hent(b.id)
        opgave_id = b_hos_bo.opgaver[1].id
        self.bo.offboarding.marker_opgave_udfoert(b_hos_bo, opgave_id)
        self.anne.aktiv()        # ... en anden arkiveres, og en tredje slettes
        s.arkiver(s.hent(a.id), "Test")
        self.admin.offboarding.slet(self.admin.offboarding.hent(c.id))

        with mock.patch.object(s.repo, "hent_aktive", wraps=s.repo.hent_aktive) as aktive_helt, \
                mock.patch.object(s.repo, "hent_arkiverede", wraps=s.repo.hent_arkiverede) as arkiv_helt:
            nye_aktive, nyt_arkiv = s.opdater_lister(kendt, s.signatur(), aktive, arkiv)
        aktive_helt.assert_not_called()
        arkiv_helt.assert_not_called()
        self.assertEqual({x.id for x in nye_aktive}, {x.id for x in s.hent_aktive()})
        self.assertEqual({x.id for x in nyt_arkiv}, {x.id for x in s.hent_arkiverede()})
        self.assertNotIn(c.id, {x.id for x in nye_aktive})
        self.assertIn(a.id, {x.id for x in nyt_arkiv})
        aendret = next(x for x in nye_aktive if x.id == b.id)
        self.assertEqual(aendret.find_opgave(opgave_id).status, Opgave.UDFOERT)

    def test_udgivelser_pilotkanal_og_kun_administratorer_udgiver(self):
        n = uuid.uuid4().int % 10**6
        stabil = Udgivelse(f"9.{n}.0", op.STABIL, f"stabil-{n}.exe", "a" * 64, 10)
        pilot = Udgivelse(f"9.{n}.1", op.PILOT, f"pilot-{n}.exe", "b" * 64, 10)
        admin = SupabaseOpdateringRepository(self.admin.klient)
        anne = SupabaseOpdateringRepository(self.anne.klient)
        admin.opret(stabil)
        admin.opret(pilot)
        try:
            synlige = {u.version for u in anne.udgivelser()}
            self.assertIn(stabil.version, synlige)
            self.assertNotIn(pilot.version, synlige, "pilot kun med pilotkanal")
            with self.assertRaises(DataFejl):
                anne.opret(Udgivelse(f"9.{n}.2", op.STABIL, "x.exe", "c" * 64, 10))
            with self.assertRaises(DataFejl):
                anne.opdater(stabil.version, trukket_tilbage=True)
            with self.assertRaises(DataFejl):
                self.anne.konto.saet_opdateringskanal(self.anne.id, op.PILOT)
            self.admin.konto.saet_opdateringskanal(self.anne.id, op.PILOT)
            self.assertIn(pilot.version, {u.version for u in anne.udgivelser()})
            admin.opdater(pilot.version, trukket_tilbage=True)
            self.assertTrue(next(u for u in anne.udgivelser()
                                 if u.version == pilot.version).trukket_tilbage)
        finally:
            self.admin.konto.saet_opdateringskanal(self.anne.id, op.STABIL)
            for u in (stabil, pilot):
                admin.slet(u.version)

    def test_klientversion_meldes_paa_egen_profil(self):
        repo = SupabaseOpdateringRepository(self.bo.klient)
        repo.rapporter("0.10.0")
        profil = self.bo.konto.profil(self.bo.id)
        self.assertEqual((profil["klient_version"], profil["kanal"]), ("0.10.0", op.STABIL))
        self.assertTrue(profil["klient_set"])
        with self.assertRaises(ValideringsFejl):
            repo.rapporter("ikke-en-version")

    # ----- kalender (migrering 020) -----------------------------------------

    def test_kalender_kun_ejeren_aendrer_og_ikke_direkte_fra_tabellen(self):
        anne, bo = SupabaseKalenderRepository(self.anne.klient), SupabaseKalenderRepository(self.bo.klient)
        kalender = anne.opret_kalender(Kalender("Annes testkalender"))
        self.assertEqual(kalender.ejer, self.anne.brugernavn)
        start = datetime(2026, 10, 5, 9)
        serie = anne.opret(Begivenhed(kalender.id, "Ugemøde", start, start + timedelta(hours=1),
                                      gentagelse="FREQ=WEEKLY;COUNT=3"))
        self.assertEqual(serie.oprettet_af, self.anne.brugernavn)
        fra, til = datetime(2026, 10, 1), datetime(2026, 11, 1)
        self.assertIn(serie.id, [b.id for b in anne.begivenheder(fra, til)])
        bos_syn = next(k for k in bo.kalendre() if k.id == kalender.id)
        self.assertEqual((bos_syn.adgang, bos_syn.er_egen), (kl.LAESE, False), "alle ser alle")
        self.assertEqual([b.titel for b in bo.begivenheder(fra, til) if b.id == serie.id], ["Ugemøde"])
        for funktion in (lambda: bo.opdater(serie.kopi(titel="Bos")), lambda: bo.slet_kalender(kalender.id),
                         lambda: bo.opret(serie.kopi(id="", version=0, titel="Snyd"))):
            with self.assertRaises(DataFejl):
                funktion()
        with self.assertRaises(Exception):   # ingen select-grant (42501): kun RPC'erne
            self.bo.klient.table("calendar_events").select("title").execute()
        self.assertEqual(next(b for b in anne.begivenheder(fra, til) if b.id == serie.id).titel,
                         "Ugemøde", "Bo ændrede intet")
        anne.slet_kalender(kalender.id)

    def test_kalender_version_rettet_forekomst_og_import(self):
        repo = SupabaseKalenderRepository(self.anne.klient)
        kalender = repo.opret_kalender(Kalender("Import-test"))
        start = datetime(2026, 10, 5, 9)
        serie = repo.opret(Begivenhed(kalender.id, "Ugemøde", start, start + timedelta(hours=1),
                                      gentagelse="FREQ=WEEKLY;BYDAY=MO", paamindelse=15))
        rettet = repo.opret(Begivenhed(kalender.id, "Flyttet", start + timedelta(days=7, hours=4),
                                       start + timedelta(days=7, hours=5), gentagelse_af=serie.id,
                                       oprindelig_start=start + timedelta(days=7)))
        opdateret = repo.opdater(serie.kopi(undtagelser=[start + timedelta(days=14)]))
        self.assertEqual((opdateret.version, opdateret.paamindelse), (2, 15))
        with self.assertRaises(KonfliktFejl):
            repo.opdater(serie.kopi(titel="Forældet version"))
        fra, til = datetime(2026, 10, 1), datetime(2026, 11, 1)

        def egne():
            return [b for b in repo.begivenheder(fra, til) if b.kalender_id == kalender.id]

        alle = kl.forekomster(egne(), fra, til)
        self.assertEqual([(f.start.day, f.titel) for f in alle],
                         [(5, "Ugemøde"), (12, "Flyttet"), (26, "Ugemøde")])
        self.assertEqual(repo.opdater(opdateret.kopi(gentagelse="")).gentagelse, "")
        self.assertNotIn(rettet.id, [b.id for b in egne()],
                         "en serie uden gentagelse har ingen rettede forekomster")

        ny = Begivenhed(kalender.id, "Importeret", start, start + timedelta(hours=1),
                        gentagelse="FREQ=DAILY;COUNT=5", ical_uid="uid-1@test")
        flyttet = Begivenhed(kalender.id, "Importeret (flyttet)", start + timedelta(days=1, hours=2),
                             start + timedelta(days=1, hours=3), ical_uid="uid-1@test",
                             oprindelig_start=start + timedelta(days=1))
        self.assertEqual(repo.importer(kalender.id, [flyttet, ny]), 2)
        self.assertEqual(repo.importer(kalender.id, [flyttet, ny]), 0, "dubletter springes over")
        signatur = repo.signatur()
        repo.slet_kalender(kalender.id)
        self.assertNotEqual(repo.signatur(), signatur)
        self.assertNotIn(kalender.id, [k.id for k in repo.kalendre()])

    def test_kalender_kraever_modulet(self):
        repo = SupabaseKalenderRepository(self.bo.klient)
        kalender = repo.opret_kalender(Kalender("Bos kalender"))
        self.admin.konto.saet_moduler(self.bo.id, ["oensker"])
        try:
            self.assertEqual(repo.kalendre(), [])
            with self.assertRaises(DataFejl):
                repo.opret_kalender(Kalender("Uden modul"))
        finally:
            self.admin.konto.saet_moduler(self.bo.id, None)
        self.assertIn(kalender.id, [k.id for k in repo.kalendre()])
        repo.slet_kalender(kalender.id)

    # ----- alle ser alle (migrering 021/022) --------------------------------

    def annes_kalender(self):
        """Annes kalender med en almindelig og en privat begivenhed."""
        anne = SupabaseKalenderRepository(self.anne.klient)
        kalender = anne.opret_kalender(Kalender("Annes testkalender"))
        start = datetime(2026, 10, 6, 10)
        anne.opret(Begivenhed(kalender.id, "Tandlæge", start, start + timedelta(hours=1),
                              sted="Klinikken", beskrivelse="Fri note"))
        anne.opret(Begivenhed(kalender.id, "Privat aftale", start + timedelta(days=1),
                              start + timedelta(days=1, hours=1), sted="Hemmeligt sted",
                              privat=True))
        return anne, kalender

    def raa(self, bruger, kalender_id) -> str:
        """Direkte fra RPC'en – uden om programmet."""
        data = bruger.klient.rpc("inbase_calendar_events", {
            "p_from": "2026-10-01T00:00:00+02:00", "p_to": "2026-11-01T00:00:00+01:00"}).execute().data
        return " ".join(json.dumps(r, ensure_ascii=False) for r in data if r["calendar_id"] == kalender_id)

    def test_kolleger_ser_detaljer_men_aldrig_private(self):
        anne, kalender = self.annes_kalender()
        raa = self.raa(self.bo, kalender.id)
        for synligt in ("Tandlæge", "Klinikken", "Fri note"):
            self.assertIn(synligt, raa)
        for hemmeligt in ("Privat aftale", "Hemmeligt sted"):
            self.assertNotIn(hemmeligt, raa, "private sendes aldrig til andre end ejeren")
        self.assertEqual(raa.count('"masked": true'), 1)
        admin = self.raa(self.admin, kalender.id)
        self.assertNotIn("Privat aftale", admin, "heller ikke til administratorer")
        anne.slet_kalender(kalender.id)

    def test_administrator_kan_slette_kollegers_og_deling_er_fjernet(self):
        anne, kalender = self.annes_kalender()
        bo, admin = SupabaseKalenderRepository(self.bo.klient), SupabaseKalenderRepository(self.admin.klient)
        fra, til = datetime(2026, 10, 1), datetime(2026, 11, 1)
        privat = next(b for b in bo.begivenheder(fra, til) if b.kalender_id == kalender.id and b.maskeret)
        with self.assertRaises(DataFejl):
            bo.slet(privat.id)
        with self.assertRaises(DataFejl):
            bo.slet_kalender(kalender.id)
        admin.slet(privat.id)                       # moderation
        with self.assertRaises(DataFejl):           # RPC'en til deling findes ikke længere
            with kald("dele kalenderen"):
                self.anne.klient.rpc("inbase_calendar_share_set", {
                    "p_calendar_id": kalender.id, "p_username": self.bo.brugernavn,
                    "p_level": "write"}).execute()
        admin.slet_kalender(kalender.id)
        self.assertNotIn(kalender.id, [k.id for k in anne.kalendre()])

    def test_deaktiveret_bruger_ser_ingen_kalendere(self):
        anne, kalender = self.annes_kalender()
        cecilie = Bruger(self.service)
        self.assertIn(kalender.id, [k.id for k in SupabaseKalenderRepository(cecilie.klient).kalendre()])
        self.service.rpc("test_saet_aktiv", {"p_id": cecilie.id, "p_active": False}).execute()
        self.assertEqual(self.raa(cecilie, kalender.id), "")
        anne.slet_kalender(kalender.id)


    # ----- Find telefon (migrering 024) -------------------------------------

    def test_find_telefon_via_telefonens_anonyme_tjek(self):
        admin = SupabaseMdmRepository(self.admin.klient)
        navn = f"T{uuid.uuid4().hex[:8].upper()}"
        enhed = admin.opret(md.MdmEnhed(navn=navn, id=str(uuid.uuid4())))
        admin.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        anonym = klient(jwt("anon"))

        def tjek(noegle, position=None):
            return anonym.rpc("inbase_mdm_phone_checkin", {
                "p_name": navn.lower(), "p_key": noegle, "p_location": position}).execute().data

        noegle = md.sporingsnoegle("01234567")
        self.assertFalse(tjek(noegle)["find"])
        self.assertTrue(admin.hent(enhed.id).senest_set, "tjekket registreres som senest set")
        admin.opdater([{"id": enhed.id, "find_anmodet": historik.nu()}])
        self.assertFalse(tjek(md.sporingsnoegle("99999999"))["find"], "forkert nøgle")
        self.assertTrue(tjek(noegle)["find"])
        tjek(noegle, {"lat": 55.86, "lng": 9.84, "noejagtighed": 12.4, "batteri": 41,
                      "ukendt": "x" * 500})
        efter = admin.hent(enhed.id)
        self.assertEqual(efter.find_anmodet, "", "anmodningen nulstilles, når telefonen svarer")
        self.assertEqual((efter.position["lat"], efter.position["noejagtighed"]), (55.86, 12))
        self.assertNotIn("ukendt", efter.position)
        self.assertTrue(efter.position["modtaget"])
        self.assertFalse(tjek(noegle)["find"])
        with self.assertRaises(DataFejl):          # anon kan ikke læse tabellen
            SupabaseMdmRepository(anonym).hent_alle()
        admin.opdater([{"id": enhed.id, "arkiveret": historik.nu()}])
        admin.slet(enhed.id)

    # ----- Lås skærmlåsen op (migrering 025) --------------------------------

    def test_laas_op_via_telefonens_anonyme_tjek(self):
        admin = SupabaseMdmRepository(self.admin.klient)
        navn = f"T{uuid.uuid4().hex[:8].upper()}"
        enhed = admin.opret(md.MdmEnhed(navn=navn, id=str(uuid.uuid4())))
        admin.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        anonym = klient(jwt("anon"))
        noegle = md.sporingsnoegle("01234567")

        def tjek(**ekstra):
            svar = anonym.rpc("inbase_mdm_phone_checkin",
                              {"p_name": navn, "p_key": noegle, **ekstra}).execute().data
            return {k: svar[k] for k in ("find", "laas_op")}   # "app" afhænger af udgivelser

        self.assertEqual(tjek(p_location=None), {"find": False, "laas_op": False},
                         "kald som styrings-app 7.0 (uden p_report) virker stadig")
        tjek(p_report={"laas_op_klar": True})
        self.assertTrue(admin.hent(enhed.id).laas_op_klar)
        admin.opdater([{"id": enhed.id, "laas_op_anmodet": historik.nu()}])
        self.assertEqual(tjek(p_key=md.sporingsnoegle("99999999")),
                         {"find": False, "laas_op": False}, "forkert nøgle")
        self.assertEqual(tjek(), {"find": False, "laas_op": True})
        self.assertEqual(tjek(p_report={"laas_op": {"ok": True}}), {"find": False, "laas_op": False})
        efter = admin.hent(enhed.id)
        self.assertEqual(efter.laas_op_anmodet, "", "anmodningen nulstilles, når telefonen svarer")
        self.assertTrue(efter.laas_op_svar["ok"])
        self.assertTrue(efter.laas_op_svar["modtaget"])
        admin.opdater([{"id": enhed.id, "arkiveret": historik.nu()}])
        admin.slet(enhed.id)


    # ----- automatisk opdatering af styrings-appen (migrering 026) ----------

    def test_styrings_app_udgives_og_hentes_med_telefonens_noegle(self):
        admin = SupabaseMdmRepository(self.admin.klient)
        navn = f"T{uuid.uuid4().hex[:8].upper()}"
        enhed = admin.opret(md.MdmEnhed(navn=navn, id=str(uuid.uuid4())))
        admin.opdater([{"id": enhed.id, "nulstillingskode": "01234567"}])
        anonym = klient(jwt("anon"))
        noegle = md.sporingsnoegle("01234567")
        apk = b"PK\x03\x04" + uuid.uuid4().bytes * 1000
        version = int(time.time())              # den lokale database deler én udgivelse
        with self.assertRaises(DataFejl):       # kun med modulet Telefoner
            SupabaseMdmRepository(self.anne.klient).udgiv_app(version, "9.9", apk)
        with self.assertRaises(ValideringsFejl):       # ikke en APK
            admin.udgiv_app(version, "9.9", b"ikke en apk")
        info = admin.udgiv_app(version, "9.9", apk)
        self.assertEqual((info["version_kode"], info["sha256"]),
                         (version, hashlib.sha256(apk).hexdigest()))
        self.assertEqual(admin.app_info()["udgivet_af"], self.admin.brugernavn)
        with self.assertRaises(ValideringsFejl):       # samme version igen
            admin.udgiv_app(version, "9.9", apk)

        svar = anonym.rpc("inbase_mdm_phone_checkin", {
            "p_name": navn, "p_key": noegle, "p_report": {"version": "8.0"}}).execute().data
        self.assertEqual(svar["app"], {"version_code": version, "sha256": info["sha256"]})
        self.assertEqual(admin.hent(enhed.id).app_version, "8.0")
        hentet = anonym.rpc("inbase_mdm_phone_app", {"p_name": navn, "p_key": noegle}).execute().data
        self.assertNotIn("\n", hentet)
        self.assertEqual(base64.b64decode(hentet), apk)
        self.assertIsNone(anonym.rpc("inbase_mdm_phone_app", {
            "p_name": navn, "p_key": md.sporingsnoegle("99999999")}).execute().data, "forkert nøgle")
        admin.opdater([{"id": enhed.id, "arkiveret": historik.nu()}])
        admin.slet(enhed.id)


if __name__ == "__main__":
    unittest.main()
