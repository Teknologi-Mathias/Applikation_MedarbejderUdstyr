"""HR's behovsregistrering: validering, betingede opgaver og oplæringsvagt."""
import unittest

from app.domain import statusprik as prik
from app.domain.behov import Behov, Toej
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.repositories.fejl import ValideringsFejl
from app.services import workflow
from app.services.onboarding_service import opgave_med_noegle
from tests.hjaelp import TjenesteTest


class BehovValideringTest(unittest.TestCase):
    def test_stillinger_er_de_fire_kendte(self):
        self.assertEqual(set(OB.STILLINGER), {"Ad Hoc", "FM", "Afløser", "DM"})

    def test_toej_kombinationer_og_storrelse_antal(self):
        for polo, fleece in ((True, False), (False, True), (True, True), (False, False)):
            b = Behov(polo=Toej(polo, "M", 2), fleece=Toej(fleece, "XL", 1))
            self.assertEqual(b.valider("FM"), [])
            self.assertEqual(b.betingelse_opfyldt("toej"), polo or fleece)
        self.assertEqual(len(Behov(polo=Toej(True, "", 2)).valider("FM")), 1)
        self.assertEqual(len(Behov(fleece=Toej(True, "M", 6)).valider("FM")), 1)
        self.assertEqual(len(Behov(fleece=Toej(True, "M", 0)).valider("FM")), 1)
        # Fravalgt tøj gemmer ingen størrelse/antal.
        self.assertEqual(Behov(polo=Toej(False, "M", 3)).til_dict()["polo"],
                         {"valgt": False, "stoerrelse": "", "antal": 0})

    def test_mobil_abonnement_og_udvidet_udstyr_efter_stilling(self):
        self.assertEqual(Behov(mobil=True, abonnement="Tale og data").valider("Afløser"), [])
        self.assertEqual(Behov(mobil=True, abonnement="Kun data").valider("Ad Hoc"), [])
        self.assertTrue(Behov(mobil=True, abonnement="Tale og data").valider("Ad Hoc"))
        self.assertTrue(Behov(mobil=True).valider("FM"))
        self.assertEqual(Behov(mobil=False, abonnement="Kun data").til_dict()["abonnement"], "")
        med_telefon = {"mobil": True, "abonnement": "Kun data"}
        self.assertEqual(Behov(email=True, firmabil=True, **med_telefon).valider("DM"), [])
        self.assertEqual(len(Behov(email=True, firmabil=True, **med_telefon).valider("Ad Hoc")), 2)
        self.assertEqual(Behov(email=True).valider("DM"), ["E-mailkonto kræver mobiltelefon."])


class BetingedeOpgaverTest(TjenesteTest):
    def test_kun_valgte_behov_giver_relevante_opgaver(self):
        sag = self.ny_onboarding(behov={"polo": {"valgt": True, "stoerrelse": "S", "antal": 1},
                                        "mobil": True, "abonnement": "Kun data"})
        udstyr, bil = opgave_med_noegle(sag, "udstyr"), opgave_med_noegle(sag, "firmabil")
        self.assertEqual(udstyr.status, Opgave.IKKE_STARTET)
        self.assertEqual(udstyr.naeste_handling, "Send: Telefon (Kun data), Polo S × 1")
        self.assertEqual((bil.status, bil.begrundelse), (Opgave.UNDTAGET, workflow.IKKE_VALGT))
        uden = self.ny_onboarding(navn="Uden Udstyr")
        self.assertEqual(opgave_med_noegle(uden, "udstyr").status, Opgave.UNDTAGET)

    def test_aendret_behov_genaabner_men_overskriver_ikke_paabegyndt(self):
        sag = self.ny_onboarding(behov={"mobil": True, "abonnement": "Kun data"})
        udstyr = opgave_med_noegle(sag, "udstyr")
        ny = sag.kopi()
        ny.find_opgave(udstyr.id).saet_status(Opgave.I_GANG)
        sag = self.t.onboarding.gem_aendret(sag, ny)
        sag = self.t.onboarding.rediger(sag, {"behov": {"firmabil": True, "mobil": False}})
        self.assertEqual(opgave_med_noegle(sag, "firmabil").status, Opgave.IKKE_STARTET)
        self.assertEqual(opgave_med_noegle(sag, "udstyr").status, Opgave.I_GANG)
        self.assertEqual(len(workflow.uoverensstemmelser(sag, sag.behov)), 1)
        behov = [h for h in sag.historik.haendelser() if h["handling"] == "Behov ændret"]
        self.assertIn("Firmabil: nej → ja", behov[-1]["kommentar"])

    def test_ugyldigt_behov_afvises(self):
        with self.assertRaises(ValideringsFejl):
            self.ny_onboarding(stilling="Ad Hoc", behov={"firmabil": True})


class OplaeringTest(TjenesteTest):
    def test_tidspunkt_afslutter_ikke_bookingen(self):
        sag = self.ny_onboarding(oplaering_planlagt="2026-12-01T08:00:00")
        booket = opgave_med_noegle(sag, "oplaering_booket")
        self.assertEqual((booket.planlagt, booket.status),
                         ("2026-12-01T08:00:00", Opgave.IKKE_STARTET))
        sag = self.t.onboarding.rediger(sag, {"oplaering_booking": "Afventer bekræftelse"})
        self.assertEqual(opgave_med_noegle(sag, "oplaering_booket").status, Opgave.AFVENTER)
        sag = self.t.onboarding.rediger(sag, {"oplaering_planlagt": "2026-12-02T09:00:00"})
        booket = opgave_med_noegle(sag, "oplaering_booket")
        self.assertEqual((booket.planlagt, booket.status),
                         ("2026-12-02T09:00:00", Opgave.AFVENTER))


class KandidatoprettelseTest(TjenesteTest):
    def kandidat(self, **data):
        s = self.t.onboarding
        sag = s.ny_sag({"navn": "Kim Kandidat", "stilling": "FM", "ansaettelsesdato": "",
                        **{k: v for k, v in data.items() if k in ("behov", "loennr", "ansaettelsesdato")}})
        skab = self.t.skabeloner.sagsskabeloner("onboarding", "FM")[0]
        return s.opret(sag, skab, data)

    def test_hele_forloebet_fra_oprettelse_til_afslutning(self):
        sag = self.kandidat(behov={"mobil": True, "abonnement": "Tale og data"})
        # HR opretter kun godkendte kandidater – intet at krydse af bagefter.
        self.assertEqual(sag.status, OB.STATUS_KONTRAKT)
        self.assertTrue(all(not o.frist for o in sag.opgaver), "ingen opfundne frister")
        kontrakt = opgave_med_noegle(sag, "kontrakt")
        with self.assertRaisesRegex(ValideringsFejl, "Lønnr. og Ansættelsesdato skal udfyldes"):
            self.t.onboarding.saet_opgave_status(sag, kontrakt.id, Opgave.AFVENTER)
        sag = self.t.onboarding.rediger(sag, {"loennr": "4711", "ansaettelsesdato": "2026-12-01"})
        frister = {o.noegle: o.frist for o in sag.opgaver}
        self.assertEqual(frister["kontrakt"], "2026-11-24")          # -7 dage i skabelonen
        self.assertTrue(any("Ansættelsesdato: – → 2026-12-01" in h["kommentar"]
                            for h in sag.historik.haendelser()))
        sag = self.t.onboarding.saet_opgave_status(sag, kontrakt.id, Opgave.AFVENTER)
        for noegle in ("kontrakt", "udstyr", "oplaering_booket", "opfoelgning"):
            sag = self.t.onboarding.marker_opgave_udfoert(sag, opgave_med_noegle(sag, noegle).id)
        self.assertEqual(sag.status, OB.STATUS_AKTIV)
        self.assertTrue(sag.er_afsluttet(), "klar til afsluttende kontrol og arkivering")

    def test_stoerrelse_kraeves_foerst_naar_udstyret_sendes(self):
        polo = {"polo": {"valgt": True, "stoerrelse": "", "antal": 2}}
        sag = self.kandidat(behov=polo, loennr="4712", ansaettelsesdato="2026-12-01")
        self.assertEqual(opgave_med_noegle(sag, "udstyr").status, Opgave.IKKE_STARTET)
        sag = self.t.onboarding.marker_opgave_udfoert(sag, opgave_med_noegle(sag, "kontrakt").id)
        with self.assertRaisesRegex(ValideringsFejl, "størrelse til polo"):
            self.t.onboarding.marker_opgave_udfoert(sag, opgave_med_noegle(sag, "udstyr").id)

    def test_standardprofil_respekterer_stillingens_begraensninger(self):
        fuld = {"polo": {"valgt": True, "antal": 2}, "mobil": True,
                "abonnement": "Tale og data", "email": True, "firmabil": True}
        with self.assertRaises(ValideringsFejl):                    # Ad Hoc må ikke få bil
            self.t.indstillinger.opdater(udstyrsprofiler={"Ad Hoc": fuld})
        self.t.indstillinger.opdater(udstyrsprofiler={"FM": fuld})
        profiler = self.t.indstillinger.udstyrsprofiler()
        self.assertEqual((profiler["FM"].polo.antal, profiler["FM"].firmabil), (2, True))
        self.assertEqual(profiler["FM"].polo.stoerrelse, "", "størrelser er personlige")
        self.assertEqual(profiler["Ad Hoc"], Behov(), "ingen profil = intet forvalgt")
        # En profil bestiller intet: opgaverne er blot relevante (ikke startet).
        sag = self.kandidat(behov=profiler["FM"].til_dict())
        self.assertEqual({opgave_med_noegle(sag, n).status for n in ("udstyr", "firmabil")},
                         {Opgave.IKKE_STARTET})


    def test_statusprikker_opdaterer_med_et_klik(self):
        behov = {"polo": {"valgt": True, "stoerrelse": "M", "antal": 1},
                 "mobil": True, "abonnement": "Kun data"}
        sag = self.kandidat(behov=behov)
        s = self.t.onboarding
        self.assertEqual((prik.kontrakt(sag).tone, prik.udstyr(sag).tone), (prik.ROED, prik.ROED))
        # Kontrakten sendes med de manglende felter udfyldt i samme gem.
        self.assertEqual(s.mangler_til_kontrakt(sag), ["loennr", "ansaettelsesdato"])
        sag = s.saet_kontrakt(sag, Opgave.AFVENTER, "4712", "2026-12-01")
        self.assertEqual((sag.loennr, sag.ansaettelsesdato), ("4712", "2026-12-01"))
        sag = s.saet_kontrakt(sag, Opgave.UDFOERT)
        self.assertEqual(prik.kontrakt(sag).tone, prik.GROEN)
        # Delvist sendt = gul og I gang; alt sendt = grøn og Udført.
        sag = s.marker_udstyr_sendt(sag, ["telefon"])
        udstyr = opgave_med_noegle(sag, "udstyr")
        self.assertEqual((prik.udstyr(sag).tone, udstyr.status), (prik.GUL, Opgave.I_GANG))
        self.assertEqual(udstyr.naeste_handling, "Send: Polo M × 1")
        sag = s.marker_udstyr_sendt(sag, ["telefon", "polo"])
        self.assertEqual((prik.udstyr(sag).tone, opgave_med_noegle(sag, "udstyr").status),
                         (prik.GROEN, Opgave.UDFOERT))
        self.assertEqual(prik.udstyr(sag).tekst, "Alt udstyr sendt")
        # Opfølgningen (Merch) kan markeres, når kontrakten er retur.
        sag = s.saet_opgave_status(sag, opgave_med_noegle(sag, "opfoelgning").id, Opgave.UDFOERT)
        self.assertEqual((prik.opfoelgning(sag).tone, prik.opfoelgning(sag).tekst),
                         (prik.GROEN, "Afholdt"))
        self.assertEqual(self.t.onboarding.hent(sag.id).behov.sendt, ["telefon", "polo"])


class SkabelonSletningTest(TjenesteTest):
    def test_slet_skabeloner_men_ikke_den_sidste_og_forloeb_bevares(self):
        from app.domain import skabelon as sk
        s = self.t.skabeloner
        sag = self.ny_onboarding()
        kopi = s.gem(sk.SAG, sk.kopier(s.sagsskabeloner("onboarding")[0]))
        original = next(x for x in s.hent_alle()[sk.SAG]
                        if x["proces"] == "onboarding" and x["id"] != kopi["id"])
        s.slet(sk.SAG, original)
        self.assertEqual([x["id"] for x in s.hent_alle()[sk.SAG] if x["proces"] == "onboarding"],
                         [kopi["id"]])
        with self.assertRaisesRegex(ValideringsFejl, "sidste"):
            s.slet(sk.SAG, kopi)
        self.assertEqual(len(self.t.onboarding.hent(sag.id).opgaver), 5, "forløbet er urørt")
        for slags in (sk.MAIL, sk.PAAMINDELSE):
            foer = s.hent_alle()[slags]
            s.slet(slags, foer[0])
            self.assertEqual(len(s.hent_alle()[slags]), len(foer) - 1)


if __name__ == "__main__":
    unittest.main()
