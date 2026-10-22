"""Generisk side med søgning, filtre, knapper og en tabel over sager.

Bruges til "Aktive forløb" og "Arkiv" i både onboarding og offboarding.
Modulet bestemmer kolonnerne (Kolonne) og filtrene (Filtervalg); siden
står for visning, søgning, sortering og for at bevare markeringen.
Rækkerne bærer sagens id (aldrig lønnr.).
"""
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.hjaelpere import lav_kort, lav_sidehoved
from app.ui.widgets import ID_ROLE, SORT_ROLE, STIL_ROLE, PilleDelegate, SortItem


@dataclass
class Kolonne:
    titel: str
    bredde: int                                   # 0 = strækkes
    tekst: Callable                               # sag -> str
    sortering: Optional[Callable] = None          # sag -> sorteringsnøgle
    stil: Optional[Callable] = None               # sag -> {"bg","tekst"} (vises som pille)
    tooltip: Optional[Callable] = None            # sag -> str


@dataclass
class Filtervalg:
    navn: str                                     # fx "Status"
    vaerdier: Callable                            # () -> [str]
    vaerdi: Callable                              # sag -> str


class SagListeSide(QWidget):
    def __init__(self, titel, undertitel, kolonner, knapper=(), handlinger=(),
                 filtre=(), sorter_efter=2, parent=None):
        super().__init__(parent)
        self.kolonner = list(kolonner)
        self.filtre = list(filtre)
        self._sager = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        hoved, _ = lav_sidehoved(titel, undertitel)
        layout.addLayout(hoved)

        vaerktoej = QHBoxLayout()
        vaerktoej.setSpacing(10)
        self.soegefelt = QLineEdit()
        self.soegefelt.setPlaceholderText("Søg på navn, lønnr., status, opgave, ansvarlig…")
        self.soegefelt.setClearButtonEnabled(True)
        self.soegefelt.setMinimumWidth(300)
        self.soegefelt.textChanged.connect(self.anvend_filter)
        vaerktoej.addWidget(self.soegefelt)
        vaerktoej.addStretch()
        self._vaerktoej = vaerktoej
        for knap in knapper:
            self.tilfoej_knap(knap)
        layout.addLayout(vaerktoej)

        # Anden række: filtre til venstre, Handling-menu til højre.
        self._anden_raekke = QHBoxLayout()
        self.filter_felter = []
        for filtervalg in self.filtre:
            felt = QComboBox()
            felt.setMinimumWidth(170)
            felt.currentIndexChanged.connect(self.anvend_filter)
            self.filter_felter.append(felt)
            self._anden_raekke.addWidget(felt)
        self._anden_raekke.addStretch()
        for widget in handlinger:
            self.tilfoej_handling(widget)
        layout.addLayout(self._anden_raekke)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        self.tabel = self._opret_tabel(sorter_efter)
        kort_layout.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    def tilfoej_knap(self, knap):
        """Knap i værktøjslinjen ved søgefeltet."""
        self._vaerktoej.addWidget(knap)

    def tilfoej_handling(self, widget):
        """Widget (fx Handling-menuen) i rækken under søgefeltet, højrestillet."""
        self._anden_raekke.addWidget(widget)

    def _opret_tabel(self, sorter_efter):
        tabel = QTableWidget()
        tabel.setColumnCount(len(self.kolonner))
        tabel.setHorizontalHeaderLabels([k.titel for k in self.kolonner])
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.setShowGrid(False)
        tabel.setAlternatingRowColors(True)
        tabel.setWordWrap(False)
        tabel.setTextElideMode(Qt.TextElideMode.ElideRight)
        tabel.verticalHeader().setVisible(False)
        tabel.verticalHeader().setDefaultSectionSize(46)

        header = tabel.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        pille = PilleDelegate(tabel)
        for index, kolonne in enumerate(self.kolonner):
            if kolonne.bredde:
                tabel.setColumnWidth(index, kolonne.bredde)
            if kolonne.stil:
                tabel.setItemDelegateForColumn(index, pille)

        tabel.setSortingEnabled(True)
        header.setSortIndicator(min(sorter_efter, len(self.kolonner) - 1),
                                Qt.SortOrder.AscendingOrder)
        return tabel

    ### ----- visning --------------------------------------------------------

    def _opdater_filtervalg(self):
        for filtervalg, felt in zip(self.filtre, self.filter_felter):
            valgt = felt.currentText()
            felt.blockSignals(True)
            felt.clear()
            felt.addItem(f"Alle – {filtervalg.navn.lower()}")
            felt.addItems(filtervalg.vaerdier())
            index = felt.findText(valgt)
            felt.setCurrentIndex(max(index, 0))
            felt.blockSignals(False)

    def vis(self, sager):
        """Fylder tabellen; bevarer markering og scrollposition."""
        self._sager = list(sager)
        self._opdater_filtervalg()
        tabel = self.tabel
        valgt = self.valgt_id()
        scroll_position = tabel.verticalScrollBar().value()

        tabel.setUpdatesEnabled(False)
        tabel.setSortingEnabled(False)
        try:
            tabel.setRowCount(len(self._sager))
            for row, sag in enumerate(self._sager):
                for index, kolonne in enumerate(self.kolonner):
                    tabel.setItem(row, index, self._celle(sag, kolonne))
        finally:
            tabel.setSortingEnabled(True)
            tabel.setUpdatesEnabled(True)

        if valgt is not None:
            for row in range(tabel.rowCount()):
                item = tabel.item(row, 0)
                if item is not None and item.data(ID_ROLE) == valgt:
                    tabel.selectRow(row)
                    break
        self.anvend_filter()
        tabel.verticalScrollBar().setValue(scroll_position)

    @staticmethod
    def _celle(sag, kolonne: Kolonne):
        tekst = str(kolonne.tekst(sag) or "")
        item = SortItem(tekst)
        item.setData(SORT_ROLE, kolonne.sortering(sag) if kolonne.sortering else tekst.lower())
        item.setData(ID_ROLE, sag.id)
        if kolonne.stil:
            item.setData(STIL_ROLE, kolonne.stil(sag))
        if kolonne.tooltip:
            item.setToolTip(kolonne.tooltip(sag))
        return item

    def anvend_filter(self):
        soegetekst = self.soegefelt.text().strip().lower()
        valgte = [
            (filtervalg, felt.currentText() if felt.currentIndex() > 0 else None)
            for filtervalg, felt in zip(self.filtre, self.filter_felter)
        ]
        sager = {sag.id: sag for sag in self._sager}
        for row in range(self.tabel.rowCount()):
            sag = sager.get(self.tabel.item(row, 0).data(ID_ROLE))
            skjul = any(vaerdi and filtervalg.vaerdi(sag) != vaerdi for filtervalg, vaerdi in valgte)
            if not skjul and soegetekst:
                tekster = " ".join(
                    f"{self.tabel.item(row, k).text()} {self.tabel.item(row, k).toolTip()}"
                    for k in range(self.tabel.columnCount())
                ).lower()
                skjul = soegetekst not in tekster
            self.tabel.setRowHidden(row, skjul)

    def valgt_id(self):
        rows = self.tabel.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.tabel.item(rows[0].row(), 0)
        return item.data(ID_ROLE) if item is not None else None
