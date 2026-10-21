"""Side med søgefelt, knapper og medarbejdertabel (bruges til Hovedside og Arkiv)."""
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.medarbejder import Medarbejder
from app.ui.hjaelpere import lav_kort, lav_sidehoved, laes_dato, vis_dato
from app.ui.theme import STATUS_STIL, opgaver_stil
from app.ui.widgets import LOENNR_ROLE, SORT_ROLE, STIL_ROLE, PilleDelegate, SortItem

# Kolonner: (overskrift, startbredde). Den sidste strækkes til resten af pladsen.
KOLONNER = (
    ("Lønnr.", 110),
    ("Medarbejdernavn", 240),
    ("Sidste arbejdsdag", 150),
    ("Status", 220),
    ("Opgaver", 150),
    ("Kommentar", 0),
)
KOL_LOENNR, KOL_NAVN, KOL_DATO, KOL_STATUS, KOL_OPGAVER, KOL_KOMMENTAR = range(
    len(KOLONNER)
)


class MedarbejderSide(QWidget):
    def __init__(self, titel, undertitel, knapper, handlinger=(), parent=None):
        """knapper: øverste række ved søgefeltet. handlinger: række nedenunder (højre)."""
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        hoved, _ = lav_sidehoved(titel, undertitel)
        layout.addLayout(hoved)

        vaerktoej = QHBoxLayout()
        vaerktoej.setSpacing(10)

        self.soegefelt = QLineEdit()
        self.soegefelt.setPlaceholderText(
            "Søg på navn, lønnr., status, opgave, ansvarlig eller kommentar…"
        )
        self.soegefelt.setClearButtonEnabled(True)
        self.soegefelt.setMinimumWidth(340)
        self.soegefelt.textChanged.connect(self.anvend_filter)
        vaerktoej.addWidget(self.soegefelt)
        vaerktoej.addStretch()
        for knap in knapper:
            vaerktoej.addWidget(knap)
        layout.addLayout(vaerktoej)

        if handlinger:
            anden_raekke = QHBoxLayout()
            anden_raekke.addStretch()
            for widget in handlinger:
                anden_raekke.addWidget(widget)
            layout.addLayout(anden_raekke)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        self.tabel = self._opret_tabel()
        kort_layout.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    def _opret_tabel(self):
        tabel = QTableWidget()
        tabel.setColumnCount(len(KOLONNER))
        tabel.setHorizontalHeaderLabels([navn for navn, _ in KOLONNER])
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
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for kolonne, (_, bredde) in enumerate(KOLONNER):
            if bredde:
                tabel.setColumnWidth(kolonne, bredde)

        pille = PilleDelegate(tabel)
        tabel.setItemDelegateForColumn(KOL_STATUS, pille)
        tabel.setItemDelegateForColumn(KOL_OPGAVER, pille)

        tabel.setSortingEnabled(True)
        header.setSortIndicator(KOL_DATO, Qt.SortOrder.AscendingOrder)
        return tabel

    ### ----- celler ---------------------------------------------------------

    @staticmethod
    def _loennr_noegle(loennr):
        tekst = str(loennr)
        if tekst.isdigit():
            return (0, int(tekst), "")
        return (1, 0, tekst.lower())

    @staticmethod
    def _celle(tekst, noegle, loennr, stil=None, tooltip=None):
        item = SortItem(tekst)
        item.setData(SORT_ROLE, noegle)
        item.setData(LOENNR_ROLE, str(loennr))
        if stil is not None:
            item.setData(STIL_ROLE, stil)
        if tooltip:
            item.setToolTip(tooltip)
        return item

    @staticmethod
    def _opgaver_tooltip(m, i_dag):
        linjer = []
        for o in m.opgaver:
            tegn = "✓" if o.afsluttet else ("!" if o.er_forsinket(i_dag) else "○")
            linje = f"{tegn}  {o.navn} – {o.status}"
            if o.ansvarlig:
                linje += f" ({o.ansvarlig})"
            if not o.afsluttet and o.frist:
                linje += f" · frist {vis_dato(o.frist)}"
            linjer.append(linje)
        return "\n".join(linjer)

    def _raekke_celler(self, m):
        i_dag = date.today()
        dato = laes_dato(m.fratraedelsesdato)
        vis_fratraedelse = (
            dato.toString("dd-MM-yyyy") if dato.isValid() else str(m.fratraedelsesdato)
        )
        status_nr = (
            Medarbejder.STATUSER.index(m.status)
            if m.status in Medarbejder.STATUSER
            else 99
        )
        status_tekst = m.status + (" (manuel)" if m.status_manuel else "")
        status_tooltip = (
            f"Låst manuelt: {m.status_begrundelse}" if m.status_manuel
            else "Beregnet ud fra opgaverne"
        )
        afsluttede, total = m.opgave_optaelling()
        forsinket = bool(m.forsinkede_opgaver(i_dag))
        # Sorteres efter andel afsluttet; sager uden opgaver sidst.
        opgave_noegle = (0, afsluttede / total) if total else (1, 0.0)

        return {
            KOL_LOENNR: self._celle(
                str(m.loennr), self._loennr_noegle(m.loennr), m.loennr),
            KOL_NAVN: self._celle(str(m.navn), str(m.navn).lower(), m.loennr),
            KOL_DATO: self._celle(vis_fratraedelse, str(m.fratraedelsesdato), m.loennr),
            KOL_STATUS: self._celle(
                status_tekst, status_nr, m.loennr,
                STATUS_STIL.get(m.status), status_tooltip),
            KOL_OPGAVER: self._celle(
                m.opgave_tekst(), opgave_noegle, m.loennr,
                opgaver_stil(afsluttede, total, forsinket),
                self._opgaver_tooltip(m, i_dag)),
            KOL_KOMMENTAR: self._celle(
                str(m.kommentar), str(m.kommentar).lower(), m.loennr),
        }

    ### ----- visning --------------------------------------------------------

    def vis(self, medarbejdere):
        """Fylder tabellen; bevarer markering og scrollposition."""
        tabel = self.tabel
        valgt = self.valgt_loennr()
        scroll_position = tabel.verticalScrollBar().value()

        tabel.setUpdatesEnabled(False)
        tabel.setSortingEnabled(False)
        try:
            tabel.setRowCount(len(medarbejdere))
            for row, m in enumerate(medarbejdere):
                for kolonne, item in self._raekke_celler(m).items():
                    tabel.setItem(row, kolonne, item)
        finally:
            # Aktiverer sorteringen igen, hvilket også sorterer rækkerne.
            tabel.setSortingEnabled(True)
            tabel.setUpdatesEnabled(True)

        # Gendan markering ved at matche lønnr. igen.
        if valgt is not None:
            for row in range(tabel.rowCount()):
                item = tabel.item(row, KOL_LOENNR)
                if item is not None and item.data(LOENNR_ROLE) == valgt:
                    tabel.selectRow(row)
                    tabel.setCurrentCell(row, KOL_LOENNR)
                    break

        self.anvend_filter()
        tabel.verticalScrollBar().setValue(scroll_position)

    def anvend_filter(self):
        soegetekst = self.soegefelt.text().strip().lower()
        tabel = self.tabel

        for row in range(tabel.rowCount()):
            if not soegetekst:
                tabel.setRowHidden(row, False)
                continue
            tekster = []
            for kolonne in range(tabel.columnCount()):
                item = tabel.item(row, kolonne)
                if item is not None:
                    # Tooltip med, så man fx kan søge på en opgave eller ansvarlig.
                    tekster.append(f"{item.text()} {item.toolTip()}".lower())
            tabel.setRowHidden(row, not any(soegetekst in t for t in tekster))

    def valgt_loennr(self):
        rows = self.tabel.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.tabel.item(rows[0].row(), KOL_LOENNR)
        return item.data(LOENNR_ROLE) if item is not None else None
