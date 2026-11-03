"""Kalender: gentagelser, visning, .ics-import, deling og KalenderService (JSON-lagring).

Databasens håndhævelse (adgang, maskering, versioner) testes i tests/test_supabase_lokal.py.
"""
import unittest
from datetime import datetime, timedelta

from app import session
from app.domain import kalender as kl
from app.domain.kalender import Begivenhed
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.services.kalender_import import laes_ics
from tests.hjaelp import TjenesteTest

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
X-WR-CALNAME:Arbejde
BEGIN:VTIMEZONE
TZID:Europe/Copenhagen
BEGIN:STANDARD
DTSTART:19701025T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:moede@google.com
SUMMARY:Ugemøde
DTSTART;TZID=Europe/Copenhagen:20261005T090000
DTEND;TZID=Europe/Copenhagen:20261005T100000
RRULE:FREQ=WEEKLY;UNTIL=20261102T080000Z;BYDAY=MO
EXDATE;TZID=Europe/Copenhagen:20261012T090000
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT15M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:moede@google.com
RECURRENCE-ID;TZID=Europe/Copenhagen:20261019T090000
SUMMARY:Ugemøde (flyttet)
DTSTART;TZID=Europe/Copenhagen:20261019T130000
DTEND;TZID=Europe/Copenhagen:20261019T140000
END:VEVENT
BEGIN:VEVENT
UID:ferie@google.com
SUMMARY:Ferie
CLASS:PRIVATE
DTSTART;VALUE=DATE:20261026
DTEND;VALUE=DATE:20261031
END:VEVENT
BEGIN:VEVENT
UID:utc@google.com
SUMMARY:Opkald
DTSTART:20260701T070000Z
DTEND:20260701T073000Z
END:VEVENT
BEGIN:VEVENT
UID:aflyst@google.com
SUMMARY:Aflyst
STATUS:CANCELLED
DTSTART:20260701T070000Z
END:VEVENT
END:VCALENDAR
""".encode()


def t(dag, time=9, minut=0, maaned=10):
    return datetime(2026, maaned, dag, time, minut)


def serie(**ekstra):
    data = {"kalender_id": "k", "titel": "Ugemøde", "start": t(5), "slut": t(5, 10),
            "gentagelse": "FREQ=WEEKLY;BYDAY=MO", "id": "s"}
    data.update(ekstra)
    return Begivenhed(**data)


class GentagelseTest(unittest.TestCase):
    def test_undtagelse_og_rettet_forekomst(self):
        rettet = Begivenhed("k", "Flyttet", t(19, 13), t(19, 14), id="r", gentagelse_af="s",
                            oprindelig_start=t(19))
        alle = kl.forekomster([serie(undtagelser=[t(12)]), rettet], t(1, 0), t(31, 0))
        self.assertEqual([(f.start, f.titel) for f in alle],
                         [(t(5), "Ugemøde"), (t(19, 13), "Flyttet"), (t(26), "Ugemøde")])

    def test_klokkeslaet_holder_over_sommertid(self):
        alle = kl.forekomster([serie()], t(19, 0), t(31, 0))   # sommertid slutter 25. oktober
        self.assertEqual([f.start.hour for f in alle], [9, 9])

    def test_heldag_over_flere_dage_ses_hver_dag(self):
        ferie = Begivenhed("k", "Ferie", t(26, 0), t(31, 0), heldag=True)
        for dag in range(26, 31):
            self.assertEqual(len(kl.forekomster([ferie], t(dag, 0), t(dag + 1, 0))), 1)
        self.assertEqual(kl.forekomster([ferie], t(31, 0), t(31, 23)), [])

    def test_afkortet_serie_kan_vises_og_gemmes_uaendret_i_dialogen(self):
        afkortet = kl.afkort_serie(serie(gentagelse="FREQ=WEEKLY;BYDAY=MO;COUNT=10"), t(19))
        self.assertEqual(kl.fra_rrule(afkortet).til_rrule(), afkortet)
        self.assertEqual([f.start for f in kl.forekomster([serie(gentagelse=afkortet)],
                                                         t(1, 0), t(31, 0))], [t(5), t(12)])
        self.assertEqual(kl.resterende_rrule(serie(gentagelse="FREQ=WEEKLY;COUNT=4"), t(19)),
                         "FREQ=WEEKLY;COUNT=2")

    def test_valg_og_beskrivelse(self):
        self.assertEqual(kl.fra_rrule("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR").frekvens, kl.HVERDAGE)
        valg = kl.Gentagelse(kl.UGENTLIG, 2, (0, 2), antal=10)
        self.assertEqual(kl.beskriv_gentagelse(valg.til_rrule(), t(5)),
                         "Hver 2. uge mandag og onsdag, 10 gange")
        self.assertTrue(kl.fra_rrule("FREQ=MONTHLY;BYDAY=1MO").raa, "ukendt regel bevares")


class VisningTest(unittest.TestCase):
    def test_overlappende_deler_bredden(self):
        def f(start, slut):
            return kl.Forekomst(Begivenhed("k", f"{start}", t(5, start), t(5, slut)),
                                t(5, start), t(5, slut))
        placeret = kl.placer_i_kolonner([f(9, 11), f(10, 12), f(11, 13), f(14, 15)])
        self.assertEqual([(p[0].titel, p[1], p[2]) for p in placeret],
                         [("9", 0, 2), ("10", 1, 2), ("11", 0, 2), ("14", 0, 1)])


class IcsImportTest(unittest.TestCase):
    def test_google_eksport(self):
        kilde = laes_ics(ICS, "fil")
        self.assertEqual((kilde.navn, kilde.sprunget_over), ("Arbejde", 1), "aflyst springes over")
        moede, flyttet, ferie, opkald = kilde.begivenheder
        self.assertEqual((moede.start, moede.paamindelse, moede.undtagelser), (t(5), 15, [t(12)]))
        self.assertIn("UNTIL=20261102T090000", moede.gentagelse, "UTC -> lokal tid")
        self.assertEqual((flyttet.oprindelig_start, flyttet.start), (t(19), t(19, 13)))
        self.assertEqual((ferie.heldag, ferie.privat, ferie.slut), (True, True, t(31, 0)))
        self.assertEqual(opkald.start, datetime(2026, 7, 1, 9, 0), "UTC -> dansk sommertid")


class KalenderServiceTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.s = self.t.kalender
        self.k = self.s.kalendre()[0]

    def hent(self):
        return self.s.forekomster(t(1, 0), t(31, 0) + timedelta(days=30))

    def test_foerste_gang_oprettes_min_kalender_kun_egne_ses(self):
        self.assertEqual((self.k.navn, self.k.ejer), (kl.STANDARD_KALENDER, "tester"))
        self.s.gem(Begivenhed(self.k.id, "Tandlæge", t(6, 8), t(6, 9)))
        session.log_ind({"brugernavn": "ANDEN", "rolle": "Bruger", "moduler": None})
        self.assertNotIn(self.k.id, [k.id for k in self.s.kalendre()])
        self.assertEqual(self.hent(), [])

    def test_validering(self):
        for b in (Begivenhed(self.k.id, " ", t(6), t(6, 10)),
                  Begivenhed(self.k.id, "Møde", t(6, 10), t(6, 9)),
                  Begivenhed(self.k.id, "Møde", t(6), t(6, 10), paamindelse=-5)):
            with self.subTest(b), self.assertRaises(ValideringsFejl):
                self.s.gem(b)

    def test_kun_denne_fremtidige_og_slet(self):
        self.s.gem(serie(kalender_id=self.k.id, id="", gentagelse="FREQ=WEEKLY;BYDAY=MO;COUNT=5"))
        tredje = self.hent()[2]
        self.s.gem_forekomst(tredje, tredje.begivenhed.kopi(start=t(19, 13), slut=t(19, 14)),
                             kl.KUN_DENNE)
        self.assertEqual([f.start for f in self.hent()], [t(5), t(12), t(19, 13), t(26), t(2, maaned=11)])

        anden = self.hent()[1]
        self.s.gem_forekomst(anden, anden.begivenhed.kopi(titel="Nyt navn", start=t(12, 10),
                                                         slut=t(12, 11)), kl.FREMTIDIGE)
        self.assertEqual([(f.start, f.titel) for f in self.hent()],
                         [(t(5), "Ugemøde"), (t(12, 10), "Nyt navn"), (t(19, 10), "Nyt navn"),
                          (t(26, 10), "Nyt navn"), (t(2, 10, maaned=11), "Nyt navn")],
                         "den rettede forekomst efter skillelinjen følger den nye serie")

        self.s.slet_forekomst(self.hent()[2], kl.KUN_DENNE)
        self.s.slet_forekomst(self.hent()[0], kl.HELE_SERIEN)
        self.assertEqual([f.start for f in self.hent()], [t(12, 10), t(26, 10), t(2, 10, maaned=11)])

    def test_import_springer_dubletter_og_gamle_over(self):
        kilde = laes_ics(ICS, "fil")
        resultat = self.s.importer([(kilde, "")], graense=datetime(2026, 9, 1))
        self.assertEqual((resultat.importeret, resultat.sprunget_over, resultat.nye_kalendere),
                         (3, 2, 1), "opkaldet i juli er for gammelt, det aflyste springes over")
        igen = self.s.importer([(kilde, next(k.id for k in self.s.kalendre()
                                             if k.navn == "Arbejde"))],
                               graense=datetime(2026, 9, 1))
        self.assertEqual((igen.importeret, igen.dubletter), (0, 3))
        self.assertIn((t(19, 13), "Ugemøde (flyttet)"), [(f.start, f.titel) for f in self.hent()])

    def test_paamindelse_vises_en_gang(self):
        self.s.gem(Begivenhed(self.k.id, "Møde", t(6, 10), t(6, 11), paamindelse=15))
        self.assertEqual(self.s.tjek(t(6, 9, 40))[1], [], "for tidligt")
        self.assertEqual([f.titel for f in self.s.tjek(t(6, 9, 46))[1]], ["Møde"])
        self.assertEqual(self.s.tjek(t(6, 9, 47))[1], [], "allerede vist")


class DelingTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.s = self.t.kalender

    def som(self, navn, rolle="Bruger"):
        session.log_ind({"brugernavn": navn, "rolle": rolle, "moduler": None})
        self.s.glem_cache()     # som efter log ud/log på

    def hent(self):
        return {f.begivenhed.titel: f for f in self.s.forekomster(t(1, 0), t(31, 0))}

    def annes_kalender(self):
        self.som("ANNE")
        k = self.s.kalendre()[0]
        self.s.gem(Begivenhed(k.id, "Tandlæge", t(6, 10), t(6, 11), sted="Klinikken", paamindelse=15))
        self.s.gem(Begivenhed(k.id, "Hemmeligt", t(7, 10), t(7, 11), privat=True))
        return k

    def delt(self, kalender_id):
        return next(k for k in self.s.kalendre() if k.id == kalender_id)

    def test_ledig_optaget_redigere_og_privat(self):
        k = self.annes_kalender()
        k = self.s.del_kalender(k, "bo", kl.FREEBUSY)
        self.assertEqual([(d.brugernavn, d.niveau) for d in k.delinger], [("BO", kl.FREEBUSY)])

        self.som("BO")
        delt = self.delt(k.id)
        self.assertEqual((delt.adgang, delt.delinger, delt.er_delt_med_mig), (kl.FREEBUSY, [], True))
        self.assertEqual({(f.titel, f.begivenhed.sted) for f in self.hent().values()},
                         {(kl.MASKERET_TITEL, "")}, "kun ledig/optaget")
        with self.assertRaises(DataFejl):
            self.s.gem(Begivenhed(k.id, "Bos møde", t(8, 10), t(8, 11)))
        with self.assertRaises(ValideringsFejl):
            self.s.del_kalender(delt, "CILLE", kl.LAESE)

        self.som("ANNE")
        self.s.del_kalender(k, "BO", kl.SKRIVE)
        self.som("BO")
        delt = self.delt(k.id)
        self.assertEqual(set(self.hent()), {"Tandlæge", kl.MASKERET_TITEL}, "privat er stadig skjult")
        self.s.gem(Begivenhed(k.id, "Bos møde", t(8, 10), t(8, 11)))
        with self.assertRaises(DataFejl):
            self.s.slet_forekomst(self.hent()[kl.MASKERET_TITEL], None)
        with self.assertRaises(ValideringsFejl):
            self.s.slet_kalender(delt)
        self.s.forlad(delt)
        self.assertNotIn(k.id, [x.id for x in self.s.kalendre()])
        self.som("ANNE")
        self.assertIn("Bos møde", self.hent(), "Bo skrev i Annes kalender")

    def test_administrator_ser_alt_undtagen_privat_og_kan_moderere(self):
        k = self.annes_kalender()
        self.som("CHEF", "Administrator")
        andres = self.delt(k.id)
        self.assertEqual(andres.adgang, kl.ADMIN_ADGANG)
        self.assertEqual(set(self.hent()), {"Tandlæge", kl.MASKERET_TITEL})
        self.s.slet_forekomst(self.hent()[kl.MASKERET_TITEL], None)
        self.assertEqual(self.s.del_kalender(andres, "BO", kl.LAESE).delinger[0].brugernavn, "BO")
        self.s.slet_kalender(andres)
        self.som("ANNE")
        self.assertNotIn(k.id, [x.id for x in self.s.kalendre()])

    def test_besked_om_ny_deling_en_gang_og_kun_egne_paamindelser(self):
        self.som("BO")
        self.s.kalendre()
        self.assertEqual(self.s.tjek(t(6, 8))[2], [], "første gang: alt er kendt")
        k = self.annes_kalender()
        self.s.del_kalender(k, "BO", kl.SKRIVE)
        self.som("BO")
        _, alarmer, nye = self.s.tjek(t(6, 9, 50))
        self.assertEqual([x.navn for x in nye], [k.navn])
        self.assertEqual(alarmer, [], "Annes påmindelse følger ikke med")
        self.s.glem_cache()
        self.assertEqual(self.s.tjek(t(6, 9, 51))[2], [], "allerede meldt")

    def test_visningsvalg_huskes_pr_bruger(self):
        self.som("ANNE")
        self.s.gem_visningsvalg({"skjulte": ["k1"], "viste": [], "farver": {"k2": "#000000"}})
        self.som("BO")
        self.assertEqual(self.s.visningsvalg()["skjulte"], [])
        self.som("ANNE")
        self.assertEqual(self.s.visningsvalg()["farver"], {"k2": "#000000"})


if __name__ == "__main__":
    unittest.main()
