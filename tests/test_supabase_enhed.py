"""Supabase-laget uden netværk: brugernavnslogin, Auth-service, fejloversættelse og mapping."""
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
    SessionUdloebetFejl,
    ValideringsFejl,
)
from app.repositories.supabase import mapping
from app.repositories.supabase.klient import kald
from app.repositories.supabase.konto_repository import SupabaseKontoRepository
from app.services.auth_service import ROLLE_ADMIN, ROLLE_BRUGER, SupabaseAuthService


def _profil(id_, brugernavn, rolle, skal_skifte=False, aktiv=True):
    return {"id": id_, "brugernavn": brugernavn, "navn": brugernavn.title(), "rolle": rolle,
            "aktiv": aktiv, "oprettet": "", "skal_skifte_kode": skal_skifte}


class FalskKontoRepo:
    """Erstatter Supabase Auth/Edge Functions i testen. Nøgle: normaliseret brugernavn."""

    def __init__(self):
        self.konti = {"MASAN": ("rigtig-kode", _profil("a1", "MASAN", ROLLE_ADMIN)),
                      "HAFRA": ("midlertidig", _profil("b1", "HAFRA", ROLLE_BRUGER, True))}
        self.aktuel = None
        self.kald = []

    def log_ind(self, brugernavn, kode):
        self.kald.append(("log_ind", brugernavn))
        konto = self.konti.get(brugernavn)
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

    def _kraev_admin(self):
        # Som Edge Functions: serveren tjekker rollen.
        if self.aktuel["rolle"] != ROLLE_ADMIN:
            raise DataFejl("Ingen adgang: Kun administratorer kan administrere brugere.")

    def opret(self, brugernavn, navn, rolle, kode):
        self._kraev_admin()
        if brugernavn in self.konti:
            raise ValideringsFejl(f"Brugernavnet '{brugernavn}' er optaget.")
        profil = _profil(f"id-{brugernavn}", brugernavn, rolle, True)
        profil["navn"] = navn
        self.konti[brugernavn] = (kode, profil)
        return profil

    def nulstil_kode(self, bruger_id, kode):
        self._kraev_admin()
        self.kald.append(("nulstil_kode", bruger_id))

    def saet_aktiv(self, bruger_id, aktiv):
        self._kraev_admin()
        self.kald.append(("saet_aktiv", bruger_id, aktiv))

    def saet_rolle(self, bruger_id, rolle):
        self._kraev_admin()
        self.kald.append(("saet_rolle", bruger_id, rolle))

    def slet(self, bruger_id):
        self._kraev_admin()
        self.kald.append(("slet", bruger_id))


class SupabaseAuthTest(unittest.TestCase):
    def setUp(self):
        self.repo = FalskKontoRepo()
        self.auth = SupabaseAuthService(self.repo)

    def test_log_ind_med_brugernavn_normaliseres_og_ud(self):
        self.assertIsNone(self.auth.log_ind("MASAN", "forkert"))
        self.assertIsNone(self.auth.log_ind("UKENDT", "rigtig-kode"))
        bruger = self.auth.log_ind("  masan ", "rigtig-kode")
        self.assertEqual((bruger["brugernavn"], bruger["rolle"]), ("MASAN", ROLLE_ADMIN))
        self.assertIn(("log_ind", "MASAN"), self.repo.kald, "repoet får det normaliserede navn")
        self.auth.log_ud()
        self.assertIn(("log_ud",), self.repo.kald)

    def test_ugyldigt_brugernavn_sendes_ikke_til_serveren(self):
        for tekst in ("", "a", "med mellemrum", "masan@firma.dk"):
            with self.subTest(tekst):
                self.assertIsNone(self.auth.log_ind(tekst, "rigtig-kode"))
        self.assertFalse([k for k in self.repo.kald if k[0] == "log_ind"])

    def test_samme_besked_for_ukendt_bruger_og_forkert_kode(self):
        # Servicen returnerer None i begge tilfælde -> UI viser LOGIN_FEJL.
        self.assertIsNone(self.auth.log_ind("FINDESIKKE", "x"))
        self.assertIsNone(self.auth.log_ind("MASAN", "x"))
        self.assertNotIn("findes", self.auth.LOGIN_FEJL.lower())

    def test_konto_uden_profil_afvises_og_logges_ud(self):
        self.repo.konti["FREMMED"] = ("kode1234", {"id": "x9"})
        self.repo.profil = lambda _id: None
        with self.assertRaises(DataFejl):
            self.auth.log_ind("fremmed", "kode1234")
        self.assertIn(("log_ud",), self.repo.kald)

    def test_deaktiveret_profil_afvises_og_logges_ud(self):
        self.repo.konti["HAFRA"][1]["aktiv"] = False
        with self.assertRaises(DataFejl) as fejl:
            self.auth.log_ind("hafra", "midlertidig")
        self.assertIn("deaktiveret", str(fejl.exception))
        self.assertIn(("log_ud",), self.repo.kald)
        self.assertIsNone(self.auth._aktuel)

    def test_administrator_opretter_bruger_med_profil_og_rolle(self):
        self.auth.log_ind("MASAN", "rigtig-kode")
        self.auth.opret(" sadah ", "Sara Dahl", ROLLE_BRUGER, "midlertid1")
        ny = SupabaseAuthService(self.repo).log_ind("Sadah", "midlertid1")
        self.assertEqual((ny["brugernavn"], ny["rolle"]), ("SADAH", ROLLE_BRUGER))
        self.assertTrue(ny["skal_skifte_kode"])
        self.assertNotIn("email", ny)

    def test_dubleret_brugernavn_uanset_store_og_smaa_bogstaver(self):
        self.auth.log_ind("MASAN", "rigtig-kode")
        with self.assertRaises(ValideringsFejl):
            self.auth.opret("hafra", "Dublet", ROLLE_BRUGER, "kode12345")

    def test_almindelig_bruger_kan_ikke_oprette_administrator(self):
        self.auth.log_ind("HAFRA", "midlertidig")
        with self.assertRaises(DataFejl):
            self.auth.opret("HACKER", "H", ROLLE_ADMIN, "kode12345")
        with self.assertRaises((DataFejl, ValideringsFejl)):   # ser ikke engang profilen (RLS)
            self.auth.saet_rolle("MASAN", ROLLE_BRUGER, "HAFRA")
        self.assertNotIn("HACKER", self.repo.konti)

    def test_validering_foer_serverkald(self):
        self.auth.log_ind("MASAN", "rigtig-kode")
        for args in (("a", "", ROLLE_BRUGER, "kode12345"),             # for kort brugernavn
                     ("an na", "", ROLLE_BRUGER, "kode12345"),         # mellemrum
                     ("anna@x.dk", "", ROLLE_BRUGER, "kode12345"),     # ikke en e-mail
                     ("ANNA", "", "Superbruger", "kode12345"),
                     ("ANNA", "", ROLLE_BRUGER, "kort")):
            with self.subTest(args), self.assertRaises(ValideringsFejl):
                self.auth.opret(*args)

    def test_midlertidig_kode_skiftes(self):
        bruger = self.auth.log_ind("HAFRA", "midlertidig")
        self.assertTrue(bruger["skal_skifte_kode"])
        with self.assertRaises(ValideringsFejl):
            self.auth.skift_midlertidig_kode("ny-kode-1", "ny-kode-2")
        self.auth.skift_midlertidig_kode("ny-kode-123", "ny-kode-123")
        self.assertIn(("skift_egen_kode", "ny-kode-123"), self.repo.kald)

    def test_skift_egen_kode_kraever_rigtig_nuvaerende(self):
        self.auth.log_ind("MASAN", "rigtig-kode")
        with self.assertRaises(ValideringsFejl):
            self.auth.skift_egen_kode("MASAN", "forkert", "ny-kode-123", "ny-kode-123")
        self.auth.skift_egen_kode("MASAN", "rigtig-kode", "ny-kode-123", "ny-kode-123")

    def test_kan_ikke_slette_deaktivere_eller_aendre_rolle_paa_sig_selv(self):
        self.auth.log_ind("MASAN", "rigtig-kode")
        for handling in (lambda: self.auth.slet("masan", "MASAN"),
                         lambda: self.auth.saet_aktiv("masan", False, "MASAN"),
                         lambda: self.auth.saet_rolle("masan", ROLLE_BRUGER, "MASAN")):
            with self.assertRaises(ValideringsFejl):
                handling()
        self.auth.saet_aktiv("hafra", False, "MASAN")
        self.auth.saet_rolle("hafra", ROLLE_ADMIN, "MASAN")
        self.auth.slet("hafra", "MASAN")
        self.assertEqual([k for k in self.repo.kald if k[0] in ("saet_aktiv", "saet_rolle", "slet")],
                         [("saet_aktiv", "b1", False), ("saet_rolle", "b1", ROLLE_ADMIN),
                          ("slet", "b1")])

    def test_kontroller_session_lukker_ved_deaktivering_og_rolleskift(self):
        self.auth.kontroller_session()                  # ikke logget på: intet at kontrollere
        self.auth.log_ind("HAFRA", "midlertidig")
        self.auth.kontroller_session()                  # alt i orden
        self.repo.konti["HAFRA"][1]["rolle"] = ROLLE_ADMIN
        with self.assertRaises(SessionUdloebetFejl):
            self.auth.kontroller_session()
        self.repo.konti["HAFRA"][1].update(rolle=ROLLE_BRUGER, aktiv=False)
        with self.assertRaises(SessionUdloebetFejl):
            self.auth.kontroller_session()
        self.repo.profil = lambda _id: None             # profilen er slettet
        with self.assertRaises(SessionUdloebetFejl):
            self.auth.kontroller_session()


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
        for fejl in (AuthApiError("Invalid login credentials", 400, "invalid_credentials"),
                     AuthApiError("User is banned", 400, "user_banned")):   # deaktiveret
            klient.auth.sign_in_with_password.side_effect = fejl
            with self.subTest(fejl.message), self.assertRaises(ForkertLoginFejl):
                SupabaseKontoRepository(klient).log_ind("HAFRA", "x")
        klient.auth.sign_in_with_password.side_effect = httpx.ConnectError("nede")
        with self.assertRaises(OfflineFejl):
            SupabaseKontoRepository(klient).log_ind("HAFRA", "x")

    def test_login_bruger_internt_alias_af_brugernavnet(self):
        klient = mock.Mock()
        klient.auth.sign_in_with_password.return_value.user.id = "u1"
        self.assertEqual(SupabaseKontoRepository(klient).log_ind("HAFRA", "hemmelig"), "u1")
        klient.auth.sign_in_with_password.assert_called_once_with(
            {"email": "hafra@brugere.in-base.invalid", "password": "hemmelig"})
        self.assertTrue(mapping.login_alias("MASAN").endswith(".invalid"))

    def test_udloebet_session_bliver_sessionsfejl(self):
        from postgrest.exceptions import APIError
        from supabase_auth.errors import AuthSessionMissingError
        from supabase_functions.errors import FunctionsHttpError
        for undtagelse in (APIError({"code": "PGRST303", "message": "JWT expired"}),
                           APIError({"code": "PGRST301", "message": "JWSError"}),
                           AuthSessionMissingError(),
                           FunctionsHttpError("Din session er ugyldig", 401)):
            with self.subTest(type(undtagelse).__name__):
                self.assertIsInstance(self._fejl(undtagelse), SessionUdloebetFejl)
        # Manglende administratorret er IKKE en udløbet session.
        fejl = self._fejl(FunctionsHttpError("Kun administratorer", 403))
        self.assertNotIsInstance(fejl, SessionUdloebetFejl)
        self.assertIsInstance(fejl, DataFejl)


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
