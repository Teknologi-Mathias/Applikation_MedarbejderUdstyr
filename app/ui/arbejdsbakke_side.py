"""Arbejdsbakke: de opgaver, brugeren og brugerens afdelinger skal håndtere.

Visningerne (Mine opgaver, Min afdeling, Ikke tildelte …) og statusserne
kommer fra app/services/arbejdsbakke.py – samme beregning som Teamoverblikket.
Opgaver, der kan udføres nu, og opgaver, der venter på en forudsætning, vises
i hver sin tabel; de blokerede viser hvorfor.

Klik åbner sagen på opgaven. Højreklik giver hurtige handlinger, som
controlleren udfører (signalet handling) – ikke siden selv.
"""
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTabBar,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app import session
from app.domain import arbejdsspor as sp
from app.services import arbejdsbakke as ab
from app.services.action_center import MODUL_NAVN
from app.ui import action_liste as al
from app.ui.hjaelpere import lav_kort, lav_sidehoved, vis_dato
from app.ui.theme import TONER, spor_stil
from app.ui.widgets import ID_ROLE, SORT_ROLE, STIL_ROLE, PilleDelegate, SortItem

OPGAVE_ROLE = Qt.ItemDataRole.UserRole + 3

_KOLONNER = ("Opgave", "Medarbejder", "Spor", "Afdeling", "Ansvarlig", "Frist", "Planlagt",
             "Status", "Næste handling / venter på")
_STATUS_KOLONNE = 7

_TOM = {
    ab.MINE: "Du har ingen åbne opgaver tildelt.",
    ab.MIN_AFDELING: "Ingen åbne opgaver i dine afdelinger.",
    ab.IKKE_TILDELT: "Alle opgaver har en ejer (afdeling eller person).",
    ab.AFVENTER_ANDRE: "Ingen opgaver afventer andre.",
    ab.FORSINKEDE: "Ingen forsinkede opgaver.",
    ab.NYLIGT_AFSLUTTET: f"Ingen opgaver er udført de seneste {ab.NYLIG_DAGE} dage.",
}


def vis_tidspunkt(tekst: str) -> str:
    """"2026-12-01T08:00:00" -> "01-12-2026 08:00"."""
    if not tekst:
        return ""
    return f"{vis_dato(tekst[:10])} {tekst[11:16]}".strip()


def opgave_menu(parent, proces, sag_id, opgave_id, aabn_sag, handling, pos_global):
    """Højrekliksmenu for én opgave (bruges af arbejdsbakken og teamoverblikket)."""
    menu = QMenu(parent)
    menu.addAction("Åbn sag", lambda: aabn_sag.emit(proces, sag_id, opgave_id))
    menu.addSeparator()
    for navn, tekst in ((al.UDFOERT, "Markér som udført"), (al.I_GANG, "Sæt i gang"),
                        (al.AFVENTER, "Afventer andre"), (al.FRIST, "Ændr frist…"),
                        (al.ANSVARLIG, "Tildel ansvarlig…")):
        menu.addAction(tekst, lambda n=navn: handling.emit(n, proces, sag_id, opgave_id))
    menu.addSeparator()
    menu.addAction("Vis historik", lambda: handling.emit(al.HISTORIK, proces, sag_id, ""))
    menu.exec(pos_global)


class OpgaveTabel(QWidget):
    """Titel, tom-tilstand og en tabel med opgaver (Post fra arbejdsbakke)."""

    def __init__(self, titel: str, side: "ArbejdsbakkeSide"):
        super().__init__()
        self.side = side
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.titel = QLabel(titel)
        self.titel.setObjectName("sektionTitel")
        self._titel_tekst = titel
        self.tom = QLabel("")
        self.tom.setObjectName("hjaelpTekst")
        self.tabel = QTableWidget(0, len(_KOLONNER))
        self.tabel.setHorizontalHeaderLabels(_KOLONNER)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(40)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        for k, bredde in enumerate((230, 170, 110, 120, 110, 100, 130, 130)):
            self.tabel.setColumnWidth(k, bredde)
        pille = PilleDelegate(self.tabel)
        self.tabel.setItemDelegateForColumn(5, pille)
        self.tabel.setItemDelegateForColumn(_STATUS_KOLONNE, pille)
        self.tabel.setSortingEnabled(True)
        self.tabel.sortItems(5, Qt.SortOrder.AscendingOrder)     # frist først
        self.tabel.itemDoubleClicked.connect(self._aabn)
        self.tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabel.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.titel)
        layout.addWidget(self.tom)
        layout.addWidget(self.tabel, 1)

    def vis(self, poster, tom_tekst: str, i_dag: date):
        self.titel.setText(f"{self._titel_tekst} ({len(poster)})")
        self.tom.setText(tom_tekst)
        self.tom.setVisible(not poster)
        self.tabel.setVisible(bool(poster))
        self.tabel.setSortingEnabled(False)
        self.tabel.setRowCount(len(poster))
        for r, p in enumerate(poster):
            o, sag = p.opgave, p.sag
            over = o.dage_over_frist(i_dag)
            frist_stil = TONER["roed"] if over and over > 0 else (
                TONER["gul"] if over == 0 else None)
            spor = sp.SPOR_NAVNE[sp.spor_for(o)]
            modul = MODUL_NAVN.get(sag.PROCES, "")
            naeste = p.aarsag or o.naeste_handling
            celler = (
                (o.navn, o.navn.lower(), None, o.beskrivelse),
                (sag.navn, sag.navn.lower(), None, f"{modul} · {sag.status}"),
                (spor, spor, None, ""),
                (o.afdeling or "–", o.afdeling, None, ""),
                (o.ansvarlig or "Ikke tildelt", o.ansvarlig, None, ""),
                # Tidsrisikoen vises også på blokerede opgaver (rød frist + "Venter på").
                (vis_dato(o.frist) if o.frist else "–", o.frist or "9999", frist_stil,
                 f"Forsinket – {over} {'dag' if over == 1 else 'dage'} over frist"
                 if over and over > 0 else ""),
                (vis_tidspunkt(o.planlagt) or "–", o.planlagt or "9999", None, ""),
                (p.status, p.status, spor_stil(p.status), sp.FORKLARING.get(p.status, "")),
                (naeste or "–", naeste, None, naeste),
            )
            for k, (tekst, noegle, stil, tip) in enumerate(celler):
                item = SortItem(tekst)
                item.setData(SORT_ROLE, noegle)
                item.setData(ID_ROLE, sag.id)
                item.setData(OPGAVE_ROLE, (sag.PROCES, o.id))
                if stil:
                    item.setData(STIL_ROLE, stil)
                if tip:
                    item.setToolTip(tip)
                self.tabel.setItem(r, k, item)
        self.tabel.setSortingEnabled(True)

    def _data(self, item):
        if item is None:
            return None
        proces, opgave_id = item.data(OPGAVE_ROLE)
        return proces, item.data(ID_ROLE), opgave_id

    def _aabn(self, item):
        data = self._data(item)
        if data:
            self.side.aabn_sag.emit(*data)

    def _menu(self, pos):
        data = self._data(self.tabel.itemAt(pos))
        if data:
            opgave_menu(self.tabel, *data, self.side.aabn_sag, self.side.handling,
                        self.tabel.viewport().mapToGlobal(pos))


class ArbejdsbakkeSide(QWidget):
    aabn_sag = Signal(str, str, str)            # (proces, sag_id, opgave_id)
    handling = Signal(str, str, str, str)       # (handling, proces, sag_id, opgave_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sager = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)
        hoved, self.undertitel = lav_sidehoved(
            "Arbejdsbakke",
            "Opgaver, du og dine afdelinger skal håndtere. Dobbeltklik for at åbne sagen, "
            "højreklik for hurtige handlinger.")
        layout.addLayout(hoved)

        self.faner = QTabBar()
        self.faner.setExpanding(False)
        self.faner.setCursor(Qt.CursorShape.PointingHandCursor)
        for _, navn in ab.VISNINGER:
            self.faner.addTab(navn)
        self.faner.currentChanged.connect(lambda _i: self._vis())
        self.soeg = QLineEdit()
        self.soeg.setPlaceholderText("Søg på opgave, medarbejder eller ansvarlig…")
        self.soeg.setClearButtonEnabled(True)
        self.soeg.textChanged.connect(lambda _t: self._vis())
        top = QHBoxLayout()
        top.addWidget(self.faner)
        top.addStretch()
        top.addWidget(self.soeg, 1)
        layout.addLayout(top)
        self.afdeling_info = QLabel("")
        self.afdeling_info.setObjectName("hjaelpTekst")
        self.afdeling_info.setWordWrap(True)
        layout.addWidget(self.afdeling_info)

        kort = lav_kort(skygge=False)
        lag = QVBoxLayout(kort)
        lag.setContentsMargins(12, 10, 12, 10)
        lag.setSpacing(14)
        self.klar = OpgaveTabel("Kan udføres nu", self)
        self.blokeret = OpgaveTabel("Venter på en forudsætning", self)
        lag.addWidget(self.klar, 3)
        lag.addWidget(self.blokeret, 2)
        layout.addWidget(kort, 1)

    def visning(self) -> str:
        return ab.VISNINGER[max(self.faner.currentIndex(), 0)][0]

    def vaelg(self, visning: str) -> None:
        self.faner.setCurrentIndex([v for v, _ in ab.VISNINGER].index(visning))

    def opdater(self, sager):
        self._sager = list(sager)
        self._vis()

    def _vis(self):
        i_dag = date.today()
        visning = self.visning()
        afdelinger = session.afdelinger()
        poster = ab.poster(self._sager, visning, i_dag, session.brugernavn() or "", afdelinger)
        soeg = self.soeg.text().strip().lower()
        if soeg:
            poster = [p for p in poster if soeg in
                      f"{p.opgave.navn} {p.sag.navn} {p.opgave.ansvarlig}".lower()]
        if visning == ab.MIN_AFDELING and not afdelinger:
            self.afdeling_info.setText("Du er ikke medlem af en afdeling. En administrator kan "
                                       "tilføje dig under Indstillinger → Brugere → Afdelinger.")
        elif visning == ab.MIN_AFDELING:
            self.afdeling_info.setText("Dine afdelinger: " + ", ".join(afdelinger))
        else:
            self.afdeling_info.setText("")
        self.afdeling_info.setVisible(bool(self.afdeling_info.text()))
        tom = _TOM[visning]
        self.klar.vis([p for p in poster if not p.blokeret], tom, i_dag)
        blokerede = [p for p in poster if p.blokeret]
        self.blokeret.vis(blokerede, "Ingen opgaver venter på en forudsætning.", i_dag)
        self.blokeret.setVisible(visning != ab.NYLIGT_AFSLUTTET)
