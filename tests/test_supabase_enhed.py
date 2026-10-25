"""Supabase-laget uden netværk: Auth-service, fejloversættelse og mapping."""
import unittest
from datetime import date
from unittest import mock

import httpx

from app import session
from app.domain import historik
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import Opgave
from app.domain.rykker import Rykker
from app.repositories.fejl import (
    DataFejl,
    ForkertLoginFejl,
    KonfliktFejl,
    OfflineFejl,
    ValideringsFejl,
)
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import kald
from app.repositories.supabase.konto_repository import SupabaseKontoRepository
from app.services.auth_service import ROLLE_ADMIN, ROLLE_BRUGER, SupabaseAuthService

ADMIN = {"id": "a1", "brugernavn": "admin", "navn": "Admin", "email": "admin@firma.dk",
         "rolle": ROLLE_ADMIN, "oprettet": "", "skal_skifte_kode": False}
BRUGER = {"id": "b1", "brugernavn": "bo", "navn": "Bo", "email": "bo@firma.dk",
          "rolle": ROLLE_BRUGER, "oprettet": "", "skal_skifte_kode": True}


class FalskKontoRepo:
    """Erstatter Supabase Auth/Edge Functions i testen."""

    def __init__(self):
        self.konti = {"admin@firma.dk": ("rigtig-kode", ADMIN), "bo@firma.dk": ("midlertidig", BRUGER)}
        self.aktuel = None
        self.kald = []

    def log_ind(self, email, kode):
        konto = self.konti.get(email)
        if not konto or konto[0] != kode:
            raise ForkertLoginFejl("Invalid login credentials")
        self.aktuel = konto[1]
        return konto[1]["id"]

    def log_ud(self):
        self.kald.append(("log_ud",))
        self.aktuel = None

    def profil(self, bruger_id):
        return next((dict(p) for _, p in self.konti.values() if p["id"] == bruger_id), None)

    def alle_profiler(self):
        if self.aktuel["rolle"] != ROLLE_ADMIN:      # som RLS: kun egen profil
            return [dict(self.aktuel)]
        return [dict(p) for _, p in self.konti.values()]

    def katalog(self):
        return [{"brugernavn": p["brugernavn"], "navn": p["navn"]} for _, p in self.konti.values()]

    def skift_egen_kode(self, ny):
        self.kald.append(("skift_egen_kode", ny))

    def opret(self, email, brugernavn, navn, rolle, kode):
        # Som Edge Function admin-create-user: serveren tjekker rollen.
        if self.aktuel["rolle"] != ROLLE_ADMIN:
            raise DataFejl("Ingen adgang: Kun administratorer kan administrere brugere.")
        profil = {"id": f"id-{brugernavn}", "brugernavn": brugernavn, "navn": navn, "email": email,
                  "rolle": rolle, "oprettet": "", "skal_skifte_kode": True}
        self.konti[email] = (kode, profil)
        return profil

    def nulstil_kode(self, bruger_id, kode):
        self.kald.append(("nulstil_kode", bruger_id))

    def slet(self, bruger_id):
        self.kald.append(("slet", bruger_id))


class SupabaseAuthTest(unittest.TestCase):
    def setUp(self):
        self.repo = FalskKontoRepo()
        self.auth = SupabaseAuthService(self.repo)

    def test_log_ind_og_ud(self):
        self.assertIsNone(self.auth.log_ind("admin@firma.dk", "forkert"))
        self.assertIsNone(self.auth.log_ind("admin", "rigtig-kode"))   # kræver e-mail
        bruger = self.auth.log_ind(" Admin@Firma.dk ", "rigtig-kode")
        self.assertEqual((bruger["brugernavn"], bruger["rolle"]), ("admin", ROLLE_ADMIN))
        self.auth.log_ud()
        self.assertIn(("log_ud",), self.repo.kald)

    def test_konto_uden_profil_afvises_og_logges_ud(self):
        self.repo.konti["fremmed@x.dk"] = ("kode1234", {"id": "x9"})
        self.repo.profil = lambda _id: None
        with self.assertRaises(DataFejl):
            self.auth.log_ind("fremmed@x.dk", "kode1234")
        self.assertIn(("log_ud",), self.repo.kald)

    def test_administrator_opretter_bruger_med_profil_og_rolle(self):
        self.auth.log_ind("admin@firma.dk", "rigtig-kode")
        self.auth.opret("ny.bruger", "Ny Bruger", ROLLE_BRUGER, "midlertid1", email="ny@firma.dk")
        ny = SupabaseAuthService(self.repo).log_ind("ny@firma.dk", "midlertid1")
        self.assertEqual((ny["brugernavn"], ny["rolle"]), ("ny.bruger", ROLLE_BRUGER))
        self.assertTrue(ny["skal_skifte_kode"])

    def test_almindelig_bruger_kan_ikke_oprette_brugere(self):
        self.auth.log_ind("bo@firma.dk", "midlertidig")
        with self.assertRaises(DataFejl):
            self.auth.opret("hacker", "H", ROLLE_ADMIN, "kode12345", email="h@x.dk")
        # og ser kun navne, ikke andres e-mail og rolle
        self.assertTrue(all("email" not in b for b in self.auth.brugere()))

    def test_validering_foer_serverkald(self):
        self.auth.log_ind("admin@firma.dk", "rigtig-kode")
        for args in (("a", "", ROLLE_BRUGER, "kode12345", "x@y.dk"),        # for kort brugernavn
                     ("anna", "", ROLLE_BRUGER, "kode12345", "ikke-email"),
                     ("anna", "", "Superbruger", "kode12345", "x@y.dk"),
                     ("anna", "", ROLLE_BRUGER, "kort", "x@y.dk")):
            with self.subTest(args), self.assertRaises(ValideringsFejl):
                self.auth.opret(*args[:4], email=args[4])

    def test_midlertidig_kode_skiftes(self):
        bruger = self.auth.log_ind("bo@firma.dk", "midlertidig")
        self.assertTrue(bruger["skal_skifte_kode"])
        with self.assertRaises(ValideringsFejl):
            self.auth.skift_midlertidig_kode("ny-kode-1", "ny-kode-2")
        self.auth.skift_midlertidig_kode("ny-kode-123", "ny-kode-123")
        self.assertIn(("skift_egen_kode", "ny-kode-123"), self.repo.kald)

    def test_skift_egen_kode_kraever_rigtig_nuvaerende(self):
        self.auth.log_ind("admin@firma.dk", "rigtig-kode")
        with self.assertRaises(ValideringsFejl):
            self.auth.skift_egen_kode("admin", "forkert", "ny-kode-123", "ny-kode-123")
        self.auth.skift_egen_kode("admin", "rigtig-kode", "ny-kode-123", "ny-kode-123")

    def test_kan_ikke_slette_sig_selv(self):
        self.auth.log_ind("admin@firma.dk", "rigtig-kode")
        with self.assertRaises(ValideringsFejl):
            self.auth.slet("admin", "admin")
        self.auth.slet("bo", "admin")
        self.assertIn(("slet", "b1"), self.repo.kald)


class FejloversaettelseTest(unittest.TestCase):
    def _fejl(self, undtagelse):
        with self.assertRaises(Exception) as ctx, kald("teste"):
            raise undtagelse
        return ctx.exception

    def test_koder_bliver_typede_fejl(self):
        from postgrest.exceptions import APIError
        self.assertIsInstance(self._fejl(APIError({"code": "IB409", "message": "ændret"})), KonfliktFejl)
        self.assertIsInstance(self._fejl(APIError({"code": "IB422", "message": "x"})), ValideringsFejl)
        self.assertIsInstance(self._fejl(APIError({"code": "42501", "message": "x"})), DataFejl)
        self.assertIsInstance(self._fejl(httpx.ConnectError("nede")), OfflineFejl)

    def test_netvaerksfejl_giver_ingen_stiltiende_reserve(self):
        """En Supabase-fejl må aldrig ende i, at gamle/lokale data vises."""
        fejl = self._fejl(httpx.ConnectTimeout("timeout"))
        self.assertIsInstance(fejl, OfflineFejl)
        self.assertIn("Intet er gemt lokalt", str(fejl))

    def test_forkert_kode_er_ikke_en_datafejl(self):
        from supabase_auth.errors import AuthApiError
        klient = mock.Mock()
        klient.auth.sign_in_with_password.side_effect = AuthApiError("Invalid login", 400, None)
        with self.assertRaises(ForkertLoginFejl):
            SupabaseKontoRepository(klient).log_ind("a@b.dk", "x")
        klient.auth.sign_in_with_password.side_effect = httpx.ConnectError("nede")
        with self.assertRaises(OfflineFejl):
            SupabaseKontoRepository(klient).log_ind("a@b.dk", "x")


class MappingTest(unittest.TestCase):
    def setUp(self):
        historik.saet_brugerkilde(session.brugernavn)
        session.log_ind({"brugernavn": "tester", "rolle": ROLLE_BRUGER})

    def tearDown(self):
        session.log_ud()

    def _rundtur(self, sag):
        """Domæne -> rækker -> (som PostgREST returnerer dem) -> domæne."""
        r = mapping.sag_til_raekker(sag)
        raekke = {**r["case"], "version": 3, "updated_at": "2026-10-22T10:00:00+00:00",
                  "people": r["person"],
                  "employment_records": {**r["employment"],
                                         "positions": {"code": r["employment"]["position_code"]},
                                         "areas": {"name": r["employment"]["area_name"]}},
                  "case_tasks": list(reversed(r["tasks"])),
                  "case_reminders": r["reminders"], "audit_events": r["events"]}
        return mapping.sag_fra_raekke(raekke, type(sag))

    def test_offboarding_rundtur_bevarer_alt_og_hashkaeden(self):
        sag = Medarbejder("123", "Mette Fiktiv", "2026-11-30", "kommentar",
                          [Opgave("Modtag tøj", "HR", "2026-12-01", udstyr="Tøj"),
                           Opgave("Luk konto", "IT", "")],
                          email="m@x.dk", tracking_link="https://spor")
        sag.opgaver[0].saet_status(Opgave.UDFOERT)
        sag.rykkere.append(Rykker("Første", "Første påmindelse", "Emne", "2026-12-05"))
        sag.historik.tilfoej("Sag oprettet", data={"type": "oprettet", "status": sag.status})
        sag.historik.tilfoej("Notat", "æøå")
        igen = self._rundtur(sag)
        self.assertEqual(igen.til_dict() | {"version": 0, "opdateret": ""},
                         sag.til_dict() | {"version": 0, "opdateret": ""})
        self.assertTrue(igen.historik.er_intakt())
        self.assertEqual(igen.version, 3)

    def test_onboarding_rundtur(self):
        sag = OnboardingForloeb("Ole Fiktiv", stilling="FM", omraade="Område Nord",
                                ansaettelsesdato="2026-11-01", ansvarlig="HR")
        sag.skabelon = {"id": "6f1d3c52-6a0e-4d1b-9a7e-2c5b8f0e1a11", "navn": "S", "version": 2}
        igen = self._rundtur(sag)
        self.assertEqual((igen.stilling, igen.omraade, igen.ansaettelsesdato, igen.loennr),
                         ("FM", "Område Nord", "2026-11-01", ""))
        self.assertEqual(igen.skabelon, sag.skabelon)

    def test_payload_indeholder_kun_aendringer(self):
        sag = Medarbejder("1", "A", "2026-11-30", opgaver=[Opgave("x"), Opgave("y")])
        forrige = mapping.sag_til_raekker(sag)
        ny = sag.kopi()
        ny.opgaver[1].ansvarlig = "IT"
        del ny.opgaver[0]
        ny.historik.tilfoej("Ændret")
        payload = mapping.rpc_payload(mapping.sag_til_raekker(ny), forrige)
        self.assertEqual([t["id"] for t in payload["tasks_upsert"]], [ny.opgaver[0].id])
        self.assertEqual(payload["tasks_delete"], [sag.opgaver[0].id])
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["reminders_upsert"], [])
        fuld = mapping.rpc_payload(mapping.sag_til_raekker(ny), None)
        self.assertTrue(fuld["tasks_replace"])

    def test_tidspunkter_rundtur(self):
        lokal = "2026-03-29T02:30:00"   # nat med sommertidsskift
        for tekst in ("2026-10-22T14:03:05", "2026-10-25T02:30:00", lokal):
            self.assertEqual(mapping.fra_tidspunkt(mapping.til_tidspunkt(tekst)),
                             mapping.fra_tidspunkt(mapping.til_tidspunkt(
                                 mapping.fra_tidspunkt(mapping.til_tidspunkt(tekst)))))
        self.assertEqual(mapping.fra_tidspunkt(mapping.til_tidspunkt("2026-10-22T14:03:05")),
                         "2026-10-22T14:03:05")
        self.assertIsNone(mapping.til_dato("ikke en dato"))
        self.assertEqual(mapping.til_dato(date(2026, 1, 2).isoformat()), "2026-01-02")

    def test_ugyldigt_id_afvises_foer_databasen(self):
        sag = Medarbejder("1", "A", "2026-11-30", opgaver=[Opgave("x", id="abc123def456")])
        with self.assertRaises(ValideringsFejl):
            mapping.sag_til_raekker(sag)


if __name__ == "__main__":
    unittest.main()
