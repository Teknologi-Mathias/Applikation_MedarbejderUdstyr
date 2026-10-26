"""Fælles hjælp til tests: midlertidige mapper og færdigbyggede services."""
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app import session
from app.bootstrap import byg_tjenester, klargoer

# Den første administrator i testenes JSON-datamappe (ingen standardbruger findes).
ADMIN, ADMIN_KODE = "ADMIN", "admin-kode-1"


def dato(dage: int = 0) -> str:
    return (date.today() + timedelta(days=dage)).isoformat()


class TjenesteTest(unittest.TestCase):
    """Giver self.t (Tjenester) bygget på tomme midlertidige mapper med én administrator."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="inbase-test-"))
        self.central = self._tmp / "Data"
        self.lokal = self._tmp / "Lokal"
        self.central.mkdir()
        session.log_ind({"brugernavn": "tester", "navn": "Test", "rolle": "Administrator"})
        self.t = byg_tjenester(self.central, self.lokal)
        klargoer(self.t)
        self.t.auth.opret_foerste_administrator(ADMIN, "Administrator", ADMIN_KODE)

    def tearDown(self):
        session.log_ud()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ny_offboarding(self, loennr="100", navn="Mette Jensen", dage=-10, skabelon="Standard"):
        s = self.t.offboarding
        sag = s.ny_sag({"loennr": loennr, "navn": navn, "fratraedelsesdato": dato(dage),
                        "email": "mette@example.com"})
        skab = next(x for x in self.t.skabeloner.sagsskabeloner("offboarding")
                    if x["navn"] == skabelon)
        return s.opret(sag, skab)

    def ny_onboarding(self, navn="Ole Hansen", stilling="FM", dage=7, behov=None, **data):
        s = self.t.onboarding
        sag = s.ny_sag({"navn": navn, "stilling": stilling, "omraade": "Område Nord",
                        "ansaettelsesdato": dato(dage), "ansvarlig": "tester", "behov": behov})
        skab = self.t.skabeloner.sagsskabeloner("onboarding", stilling)[0]
        return s.opret(sag, skab, data)
