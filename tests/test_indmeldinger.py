"""Ønsker & Udvikling: regler og rettigheder i IndmeldingService (JSON-lagring).

Databasens håndhævelse af de samme regler (RLS/RPC) testes i
tests/test_supabase_lokal.py.
"""
import re
import unittest
from pathlib import Path

from app import session
from app.domain import indmelding as im
from app.repositories.fejl import KonfliktFejl, ValideringsFejl
from tests.hjaelp import ADMIN, TjenesteTest

MIGRERING_006 = (Path(__file__).resolve().parents[1]
                 / "app/infrastructure/database/migrations/006_oensker_udvikling.sql")


def bruger(navn: str, rolle: str = "Bruger") -> None:
    session.log_ind({"brugernavn": navn, "navn": navn.title(), "rolle": rolle})


class IndmeldingTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.s = self.t.indmeldinger

    def ny(self, titel="Eksport til Excel fejler", **ekstra):
        return self.s.opret({"titel": titel, "kategori": "Fejlmelding",
                             "beskrivelse": "Knappen Eksportér giver en fejlbesked.", **ekstra})

    def test_oprettelse_og_visning(self):
        bruger("HAFRA")
        ind = self.ny(problem="Fejl 500", oensket_resultat="Excel-fil", effekt="Sparer 1 time/uge")
        self.assertEqual((ind.nummer, ind.status, ind.prioritet, ind.indsender),
                         (1, im.INDSENDT, im.NORMAL, "HAFRA"))
        anden = self.ny("Automatisk rykker")
        self.assertEqual([i.nummer for i in self.s.hent_alle()], [2, 1], "nyeste først")
        detaljer = self.s.detaljer(ind.id)
        self.assertEqual(detaljer.indmelding.effekt, "Sparer 1 time/uge")
        self.assertEqual([a.handling for a in detaljer.historik], [im.Aendring.OPRETTET])
        self.assertEqual(anden.visningsnummer, "#2")

    def test_indsender_og_status_kan_ikke_saettes_af_klienten(self):
        bruger("HAFRA")
        ind = self.ny(indsender="MASAN", status=im.UDGIVET, prioritet=im.KRITISK)
        self.assertEqual((ind.indsender, ind.status, ind.prioritet),
                         ("HAFRA", im.INDSENDT, im.NORMAL))

    def test_validering_af_obligatoriske_felter(self):
        bruger("HAFRA")
        for data in ({"titel": "", "kategori": "Andet", "beskrivelse": "x"},
                     {"titel": "T", "kategori": "Andet", "beskrivelse": "  "},
                     {"titel": "T", "kategori": "Ukendt", "beskrivelse": "x"},
                     {"titel": "T" * 201, "kategori": "Andet", "beskrivelse": "x"}):
            with self.subTest(data), self.assertRaises(ValideringsFejl):
                self.s.opret(data)
        session.log_ud()
        with self.assertRaises(ValideringsFejl):   # ikke logget på
            self.ny()

    def test_almindelig_bruger_kan_ikke_behandle(self):
        bruger("HAFRA")
        ind = self.ny()
        for aendring in ({"status": im.TIL_VURDERING}, {"prioritet": im.KRITISK},
                         {"ansvarlig": "HAFRA"}, {"planlagt_version": "V1"},
                         {"loesning": "Løst"}):
            with self.subTest(aendring), self.assertRaises(ValideringsFejl):
                self.s.opdater(ind, aendring)
        self.assertEqual(self.s.hent(ind.id).version, 1)

    def test_indsender_retter_egen_tekst_kun_mens_indsendt(self):
        bruger("HAFRA")
        ind = self.s.opdater(self.ny(), {"titel": "Eksport fejler i Chrome"})
        self.assertEqual((ind.titel, ind.version), ("Eksport fejler i Chrome", 2))
        bruger("SADAH")
        with self.assertRaises(ValideringsFejl):
            self.s.opdater(ind, {"titel": "Overtaget"})
        bruger(ADMIN, "Administrator")
        ind = self.s.opdater(ind, {"status": im.TIL_VURDERING})
        bruger("HAFRA")
        self.assertFalse(self.s.kan_redigere_tekst(ind))
        with self.assertRaises(ValideringsFejl):
            self.s.opdater(ind, {"beskrivelse": "Mere tekst"})

    def test_administrator_behandler_og_historikken_viser_hvem_og_hvad(self):
        bruger("HAFRA")
        ind = self.ny()
        bruger(ADMIN, "Administrator")
        ind = self.s.opdater(ind, {"status": im.TIL_VURDERING, "prioritet": im.HOEJ,
                                   "ansvarlig": " masan ", "planlagt_version": "V0.8",
                                   "titel": ind.titel})            # uændret felt ignoreres
        self.assertEqual((ind.status, ind.prioritet, ind.ansvarlig, ind.planlagt_version,
                          ind.version), (im.TIL_VURDERING, im.HOEJ, "MASAN", "V0.8", 2))
        historik = self.s.detaljer(ind.id).historik
        aendringer = {a.felt: (a.fra, a.til, a.bruger) for a in historik
                      if a.handling == im.Aendring.AENDRET}
        self.assertEqual(aendringer, {
            "status": (im.INDSENDT, im.TIL_VURDERING, ADMIN),
            "prioritet": (im.NORMAL, im.HOEJ, ADMIN),
            "ansvarlig": ("", "MASAN", ADMIN),
            "planlagt_version": ("", "V0.8", ADMIN),
        })
        self.assertEqual(self.s.opdater(ind, {"prioritet": im.HOEJ}).version, 2, "intet ændret")

    def test_statusovergange_og_afvisning_kraever_begrundelse(self):
        bruger(ADMIN, "Administrator")
        ind = self.ny()
        with self.assertRaises(ValideringsFejl):
            self.s.opdater(ind, {"status": im.UDGIVET})            # spring over trin
        with self.assertRaises(ValideringsFejl):
            self.s.opdater(ind, {"status": im.AFVIST})             # mangler begrundelse
        afvist = self.s.opdater(ind, {"status": im.AFVIST, "loesning": "Dækkes af ERP"})
        self.assertTrue(afvist.afsluttet)
        genaabnet = self.s.opdater(afvist, {"status": im.TIL_VURDERING})
        self.assertEqual(genaabnet.status, im.TIL_VURDERING)

    def test_samtidig_aendring_giver_konflikt(self):
        bruger(ADMIN, "Administrator")
        ind = self.ny()
        self.s.opdater(ind, {"prioritet": im.HOEJ})
        with self.assertRaises(KonfliktFejl):
            self.s.opdater(ind, {"prioritet": im.LAV})             # gammel version
        self.assertEqual(self.s.hent(ind.id).prioritet, im.HOEJ)

    def test_kommentarer_offentlige_og_interne(self):
        bruger("HAFRA")
        ind = self.ny()
        self.s.tilfoej_kommentar(ind.id, "Det sker også i Edge")
        with self.assertRaises(ValideringsFejl):
            self.s.tilfoej_kommentar(ind.id, "Hemmeligt", intern=True)
        with self.assertRaises(ValideringsFejl):
            self.s.tilfoej_kommentar(ind.id, "   ")
        bruger(ADMIN, "Administrator")
        self.s.tilfoej_kommentar(ind.id, "Kræver ny ERP-licens", intern=True)
        self.assertEqual([(k.forfatter, k.intern) for k in self.s.detaljer(ind.id).kommentarer],
                         [("HAFRA", False), (ADMIN, True)])
        bruger("SADAH")
        self.assertEqual([k.tekst for k in self.s.detaljer(ind.id).kommentarer],
                         ["Det sker også i Edge"], "interne noter skjules for brugere")

    def test_sletning_kun_for_administratorer(self):
        bruger("HAFRA")
        ind = self.ny()
        with self.assertRaises(ValideringsFejl):
            self.s.slet(ind)
        bruger(ADMIN, "Administrator")
        self.s.slet(ind)
        self.assertIsNone(self.s.hent(ind.id))


class DomaeneOgDatabaseStemmerOverensTest(unittest.TestCase):
    """Statusmodellen står i domænet OG i migrering 006 – de skal være ens."""

    def setUp(self):
        self.sql = MIGRERING_006.read_text(encoding="utf-8")

    def test_statusovergange(self):
        funktion = self.sql.split("inbase_request_transition_allowed(p_from text, p_to text)")[1]
        funktion = funktion.split("$$;")[0]
        i_sql = set(re.findall(r"\('([^']+)', '([^']+)'\)", funktion))
        i_domaenet = {(fra, til) for fra, tils in im.OVERGANGE.items() for til in tils}
        self.assertEqual(i_sql, i_domaenet)
        self.assertEqual(set(im.OVERGANGE), set(im.STATUSSER))

    def test_kategorier_statusser_og_prioriteter(self):
        for vaerdi in im.KATEGORIER + im.STATUSSER + im.PRIORITETER:
            with self.subTest(vaerdi):
                self.assertIn(f"'{vaerdi}'", self.sql)


if __name__ == "__main__":
    unittest.main()
