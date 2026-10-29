"""Statusfelterne i "Aktive forløb" (offboarding): farver, tekster og de services,
drop down-menuerne bruger. Onboardingens felter testes i test_behov."""
from app.domain import statusprik as prik
from app.domain.opgave import Opgave
from tests.hjaelp import TjenesteTest


class OffboardingFelterTest(TjenesteTest):
    def setUp(self):
        super().setUp()
        self.sag = self.ny_offboarding()           # standardskabelonen
        self.s = self.t.offboarding

    def felter(self, sag=None):
        sag = sag or self.s.hent(self.sag.id)
        return {navn: (f(sag).tone, f(sag).tekst) for navn, f in (
            ("tankkort", prik.tankkort), ("toej", prik.toej), ("telefon", prik.telefon),
            ("nav", prik.nav))}

    def test_ny_sag_er_roed_og_opgaverne_findes_paa_udstyret(self):
        self.assertEqual(self.felter(), {
            "tankkort": (prik.ROED, "Ikke behandlet"), "toej": (prik.ROED, "Intet afleveret"),
            "telefon": (prik.ROED, "Intet afleveret"), "nav": (prik.ROED, "Nej")})
        self.assertEqual([o.udstyr for o in prik.toej_opgaver(self.sag)], ["Tøj"])
        self.assertEqual([o.udstyr for o in prik.telefon_opgaver(self.sag)], ["Telefon og SIM-kort"])

    def test_tankkort_ikke_relevant_kan_fortrydes(self):
        opgave = prik.tankkort_opgaver(self.sag)[0]
        sag = self.s.undtag_opgave(self.sag, opgave.id, prik.IKKE_RELEVANT_BEGRUNDELSE)
        self.assertEqual(self.felter(sag)["tankkort"], (prik.INTET, "Ikke relevant"))
        sag = self.s.saet_opgave_status(sag, opgave.id, Opgave.UDFOERT)
        self.assertEqual(self.felter(sag)["tankkort"], (prik.GROEN, "Behandlet"))
        self.assertEqual(sag.find_opgave(opgave.id).begrundelse, "")

    def test_toej_og_udstyr_roerer_kun_egne_opgaver(self):
        ekstra = Opgave("Modtag computer", "IT", udstyr="Computer")
        self.sag.opgaver.append(ekstra)
        gruppe = [o.id for o in prik.toej_opgaver(self.sag)]
        self.assertEqual(len(gruppe), 2)
        sag = self.s.marker_afleveret(self.sag, [ekstra.id], gruppe)
        self.assertEqual(self.felter(sag)["toej"], (prik.GUL, "Delvist afleveret"))
        self.assertEqual(self.felter(sag)["telefon"], (prik.ROED, "Intet afleveret"),
                         "telefonen er ikke en del af gruppen")
        sag = self.s.marker_afleveret(sag, gruppe, gruppe)
        self.assertEqual(self.felter(sag)["toej"], (prik.GROEN, "Alt afleveret"))

    def test_nav_ja_nej(self):
        sag = self.s.saet_opgave_status(self.sag, prik.nav_opgave(self.sag).id, Opgave.UDFOERT)
        self.assertEqual(self.felter(sag)["nav"], (prik.GROEN, "Ja"))

    def test_uden_opgaver_er_feltet_ikke_relevant(self):
        tom = self.ny_offboarding(loennr="101", skabelon="Tom sag (tilføj opgaver selv)")
        self.assertEqual({t for t, _ in self.felter(tom).values()}, {prik.INTET})
