"""Nøgletal: filtrerbare målepunkter for onboarding og offboarding.

Viser tydeligt, om et tal er antal, andel eller gennemsnit/median, og hvor
mange sager det bygger på (n). Uden datagrundlag vises "Ikke nok data".
"""
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.rapport_service import Filter, RapportService
from app.ui.hjaelpere import lav_kort, scroll_side


def _tabel(overskrifter):
    tabel = QTableWidget(0, len(overskrifter))
    tabel.setHorizontalHeaderLabels(overskrifter)
    tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabel.setShowGrid(False)
    tabel.setAlternatingRowColors(True)
    tabel.verticalHeader().setVisible(False)
    tabel.horizontalHeader().setStretchLastSection(True)
    tabel.setColumnWidth(0, 300)
    tabel.setMinimumHeight(220)
    return tabel


class RapportPanel(QWidget):
    def __init__(self, rapporter: RapportService, parent=None):
        super().__init__(parent)
        self.rapporter = rapporter
        self._sager = []

        layout = scroll_side(self)
        layout.setContentsMargins(0, 12, 8, 12)
        layout.setSpacing(14)

        filtre = QHBoxLayout()
        filtre2 = QHBoxLayout()
        self.fra = QDateEdit(QDate.currentDate().addMonths(-6))
        self.til = QDateEdit(QDate.currentDate())
        for felt in (self.fra, self.til):
            felt.setCalendarPopup(True)
            felt.setDisplayFormat("dd-MM-yyyy")
        self.modul = QComboBox()
        self.modul.addItem("Alle moduler", "")
        self.modul.addItem("Onboarding", "onboarding")
        self.modul.addItem("Offboarding", "offboarding")
        self.stilling = QComboBox()
        self.omraade = QComboBox()
        self.ansvarlig = QComboBox()
        for label, felt in (("Oprettet fra", self.fra), ("til", self.til), ("", self.modul)):
            if label:
                filtre.addWidget(QLabel(label))
            filtre.addWidget(felt)
        for felt in (self.stilling, self.omraade, self.ansvarlig):
            felt.setMinimumWidth(170)
            filtre2.addWidget(felt)
        filtre.addStretch()
        filtre2.addStretch()
        layout.addLayout(filtre)
        layout.addLayout(filtre2)
        for felt in (self.fra, self.til):
            felt.dateChanged.connect(self.beregn)
        for felt in (self.modul, self.stilling, self.omraade, self.ansvarlig):
            felt.currentIndexChanged.connect(self.beregn)

        self.maal_grid = QGridLayout()
        self.maal_grid.setSpacing(12)
        layout.addLayout(self.maal_grid)

        tabeller = QVBoxLayout()
        tabeller.setSpacing(14)
        self.fordeling = _tabel(["Ansvarlig", "Åbne opgaver", "Heraf forsinkede"])
        self.flaskehalse = _tabel(["Gruppe · status (åbne onboardingforløb)", "Antal",
                                   "Gns. dage i status"])
        for titel, tabel in (("Arbejdsfordeling", self.fordeling),
                             ("Flaskehalse", self.flaskehalse)):
            kort = lav_kort(skygge=False)
            lag = QVBoxLayout(kort)
            lag.setContentsMargins(16, 14, 16, 12)
            titel_label = QLabel(titel)
            titel_label.setObjectName("cardTitle")
            lag.addWidget(titel_label)
            lag.addWidget(tabel)
            tabeller.addWidget(kort, 1)
        layout.addLayout(tabeller)

        note = QLabel(
            "Tider bygger på registrerede statusskift. Sager fra før statusskift blev "
            "registreret, indgår kun i antal og opgavefrister. Stilling og område findes "
            "kun på onboarding."
        )
        note.setObjectName("hjaelpTekst")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    @staticmethod
    def _fyld_valg(felt: QComboBox, alle_tekst: str, vaerdier):
        valgt = felt.currentData()
        felt.blockSignals(True)
        felt.clear()
        felt.addItem(alle_tekst, "")
        for vaerdi in vaerdier:
            felt.addItem(vaerdi, vaerdi)
        index = felt.findData(valgt)
        felt.setCurrentIndex(max(index, 0))
        felt.blockSignals(False)

    def opdater(self, sager):
        self._sager = list(sager)
        valg = self.rapporter.valgmuligheder(self._sager)
        self._fyld_valg(self.stilling, "Alle stillinger", valg["stillinger"])
        self._fyld_valg(self.omraade, "Alle områder", valg["omraader"])
        self._fyld_valg(self.ansvarlig, "Alle ansvarlige", valg["ansvarlige"])
        self.beregn()

    def beregn(self):
        f = Filter(
            fra=self.fra.date().toPython(), til=self.til.date().toPython(),
            modul=self.modul.currentData() or "", stilling=self.stilling.currentData() or "",
            omraade=self.omraade.currentData() or "", ansvarlig=self.ansvarlig.currentData() or "",
        )
        rapport = self.rapporter.beregn(self._sager, f, date.today())

        while self.maal_grid.count():
            widget = self.maal_grid.takeAt(0).widget()
            if widget:
                widget.setParent(None)   # fjernes med det samme (ikke først senere)
                widget.deleteLater()
        for i, maal in enumerate(rapport.maalinger):
            kort = lav_kort(skygge=False)
            lag = QVBoxLayout(kort)
            lag.setContentsMargins(16, 12, 16, 12)
            lag.setSpacing(2)
            titel = QLabel(maal.navn)
            titel.setObjectName("statTitle")
            vaerdi = QLabel(maal.vaerdi if maal.vaerdi is not None else "Ikke nok data")
            vaerdi.setObjectName("statValue" if maal.vaerdi is not None else "hjaelpTekst")
            sub = QLabel(f"{maal.slags} · n = {maal.n}")
            sub.setObjectName("statSub")
            for label in (titel, vaerdi, sub):
                label.setWordWrap(True)
                lag.addWidget(label)
            if maal.forklaring:
                kort.setToolTip(maal.forklaring)
            self.maal_grid.addWidget(kort, i // 3, i % 3)

        for tabel, raekker in ((self.fordeling, rapport.arbejdsfordeling),
                               (self.flaskehalse, rapport.flaskehalse)):
            tabel.setRowCount(len(raekker))
            for r, raekke in enumerate(raekker):
                for k, vaerdi in enumerate(raekke):
                    tekst = f"{vaerdi:.1f}" if isinstance(vaerdi, float) else str(vaerdi)
                    tabel.setItem(r, k, QTableWidgetItem(tekst))
