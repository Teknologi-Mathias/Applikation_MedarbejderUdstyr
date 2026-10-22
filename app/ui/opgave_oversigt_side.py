"""Alle opgaver på tværs af et moduls aktive sager.

Onboarding: "Opgaver og milepæle" (kolonne: milepæl). Offboarding:
"Opgaver og udstyr" (kolonne: udstyr). Dobbeltklik åbner sagen på opgaven.
"""
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app import session
from app.ui.hjaelpere import lav_kort, lav_sidehoved, vis_dato
from app.ui.theme import OPGAVE_STIL, TONER
from app.ui.widgets import ID_ROLE, SORT_ROLE, STIL_ROLE, PilleDelegate, SortItem

OPGAVE_ROLE = Qt.ItemDataRole.UserRole + 3


class OpgaveOversigtSide(QWidget):
    aabn_sag = Signal(str, str, str)     # (proces, sag_id, opgave_id)

    def __init__(self, titel, undertitel, ekstra_kolonne: str, parent=None):
        """ekstra_kolonne: "milepael" (onboarding) eller "udstyr" (offboarding)."""
        super().__init__(parent)
        self.ekstra = ekstra_kolonne
        self._sager = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        hoved, _ = lav_sidehoved(titel, undertitel)
        layout.addLayout(hoved)

        filtre = QHBoxLayout()
        self.soeg = QLineEdit()
        self.soeg.setPlaceholderText("Søg på opgave, sag eller ansvarlig…")
        self.soeg.setClearButtonEnabled(True)
        self.kun_mine = QCheckBox("Kun mine opgaver")
        self.kun_forsinkede = QCheckBox("Kun forsinkede")
        self.vis_laaste = QCheckBox("Vis låste (senere milepæle)")
        filtre.addWidget(self.soeg, 1)
        for felt in (self.kun_mine, self.kun_forsinkede, self.vis_laaste):
            filtre.addWidget(felt)
            felt.toggled.connect(self._vis)
        self.vis_laaste.setVisible(ekstra_kolonne == "milepael")
        self.soeg.textChanged.connect(self._vis)
        layout.addLayout(filtre)

        kort = lav_kort(skygge=False)
        lag = QVBoxLayout(kort)
        lag.setContentsMargins(8, 8, 8, 8)
        overskrifter = ["Opgave", "Sag", "Milepæl" if ekstra_kolonne == "milepael" else "Udstyr",
                        "Ansvarlig", "Frist", "Status"]
        self.tabel = QTableWidget(0, len(overskrifter))
        self.tabel.setHorizontalHeaderLabels(overskrifter)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(42)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        for k, bredde in enumerate((260, 200, 160, 130, 110)):
            self.tabel.setColumnWidth(k, bredde)
        pille = PilleDelegate(self.tabel)
        self.tabel.setItemDelegateForColumn(4, pille)
        self.tabel.setItemDelegateForColumn(5, pille)
        self.tabel.setSortingEnabled(True)
        self.tabel.doubleClicked.connect(self._dobbeltklik)
        lag.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    def opdater(self, sager):
        self._sager = [s for s in sager if not s.arkiveret and not s.er_afsluttet()]
        self._vis()

    def _vis(self):
        i_dag = date.today()
        soeg = self.soeg.text().strip().lower()
        mig = (session.brugernavn() or "").lower()
        raekker = []
        for sag in self._sager:
            for o in sag.opgaver:
                laast = sag.er_laast(o)
                if o.afsluttet or (laast and not self.vis_laaste.isChecked()):
                    continue
                if self.kun_mine.isChecked() and o.ansvarlig.lower() != mig:
                    continue
                if self.kun_forsinkede.isChecked() and not o.er_forsinket(i_dag):
                    continue
                ekstra = sag.milepael_navn(o.milepael) if self.ekstra == "milepael" else o.udstyr
                tekst = f"{o.navn} {sag.navn} {o.ansvarlig} {ekstra}".lower()
                if soeg and soeg not in tekst:
                    continue
                raekker.append((sag, o, laast, ekstra))

        self.tabel.setSortingEnabled(False)
        self.tabel.setRowCount(len(raekker))
        for r, (sag, o, laast, ekstra) in enumerate(raekker):
            over = o.dage_over_frist(i_dag)
            frist_stil = TONER["roed"] if over and over > 0 else (
                TONER["gul"] if over == 0 else TONER["intet"])
            status = "Låst" if laast else o.status
            celler = (
                (o.navn, o.navn.lower(), None),
                (sag.navn, sag.navn.lower(), None),
                (ekstra or "–", ekstra or "", None),
                (o.ansvarlig or "–", o.ansvarlig, None),
                (vis_dato(o.frist) if o.frist else "–", o.frist or "9999", frist_stil if o.frist else None),
                (status, status, TONER["graa"] if laast else OPGAVE_STIL[o.status]),
            )
            for k, (tekst, noegle, stil) in enumerate(celler):
                item = SortItem(tekst)
                item.setData(SORT_ROLE, noegle)
                item.setData(ID_ROLE, sag.id)
                item.setData(OPGAVE_ROLE, (sag.PROCES, o.id))
                if stil:
                    item.setData(STIL_ROLE, stil)
                self.tabel.setItem(r, k, item)
        self.tabel.setSortingEnabled(True)

    def _dobbeltklik(self, index):
        item = self.tabel.item(index.row(), 0)
        if item:
            proces, opgave_id = item.data(OPGAVE_ROLE)
            self.aabn_sag.emit(proces, item.data(ID_ROLE), opgave_id)
