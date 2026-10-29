"""Arbejdsoverblik: et operationelt kontrolrum på tværs af onboarding og offboarding.

Fane 1 "Kontrolrum": fire klikbare overblikskort, seks arbejdskøer og "Haster
nu". Fane 2 "Action Center": alle afvigelser og dagsoversigten. Fane 3
"Nøgletal": filtrerbare målepunkter og diagrammer.

Siden beregner intet selv – tal, køer og prioritering kommer fra
app/services/kontrolrum.py (bygget på arbejdsspor, Teamoverblik og Action
Center). Klik åbner sagen på opgaven; højreklik giver de hurtige handlinger,
som controlleren udfører.
"""
from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain import arbejdsspor as sp
from app.services import kontrolrum as kr
from app.services.action_center import MODUL_NAVN
from app.ui import action_liste as al
from app.ui import ikoner
from app.ui.action_liste import ActionListe
from app.ui.action_liste import opgave_menu
from app.ui.hjaelpere import dansk_dato, lav_kort, lav_sidehoved, scroll_side, vis_dato
from app.ui.rapport_panel import RapportPanel
from app.ui.teamoverblik_side import NoegletalKort
from app.ui.theme import FARVER, TONER, spor_stil
from app.ui.widgets import STIL_ROLE, PilleDelegate

_KORT_IKON = {kr.FORSINKEDE: "forsinket", kr.STARTER_SNART: "kalender",
              kr.MANGLER_KONTRAKT: "kontrakt", kr.I_RISIKO: "risiko"}
_KOE_TOM = {
    kr.KONTRAKT: "Ingen kontrakter kræver handling.",
    kr.UDSTYR: "Intet udstyr eller firmabil mangler.",
    kr.OPLAERING: "Alle oplæringsdage er fastlagt.",
    kr.AFVENTER: "Ingen opgaver afventer andre.",
    kr.RETUR: "Intet udstyr mangler fra fratrådte.",
    kr.AFSLUTNING: "Ingen sager venter på afslutning.",
}
# Køer på tværs af modulerne viser modulnavnet i hver række.
_KOE_MODUL = (kr.AFVENTER, kr.AFSLUTNING)
_HANDLING_TEKST = {kr.TILDEL: "Tildel ansvarlig…", kr.AABN_FORUDSAETNING: "Åbn forudsætning",
                   kr.AABN: "Åbn opgave"}


def _ikon_farve() -> str:
    return FARVER["primary_hover"]


class HasterTabel(QWidget):
    """"Haster nu": prioriteret liste med én direkte handling pr. række."""
    aabn_sag = Signal(str, str, str)            # (proces, sag_id, opgave_id)
    handling = Signal(str, str, str, str)       # (handling, proces, sag_id, opgave_id)

    KOLONNER = ("Medarbejder", "Hvad mangler", "Område", "Ansvarlig", "Frist", "Status",
                "Hvorfor / venter på", "Handling")
    _FRIST, _STATUS, _HANDLING = 4, 5, 7

    def __init__(self):
        super().__init__()
        self._poster = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tom = QLabel("Intet haster lige nu.")
        self.tom.setObjectName("hjaelpTekst")
        self.tom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabel = QTableWidget(0, len(self.KOLONNER))
        self.tabel.setHorizontalHeaderLabels(self.KOLONNER)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(50)       # to linjer
        self.tabel.setWordWrap(True)
        self.tabel.setMinimumHeight(340)
        for k, bredde in enumerate((140, 200, 100, 140, 105, 100, 260, 140)):
            self.tabel.setColumnWidth(k, bredde)
        self.tabel.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        pille = PilleDelegate(self.tabel)
        self.tabel.setItemDelegateForColumn(self._FRIST, pille)
        self.tabel.setItemDelegateForColumn(self._STATUS, pille)
        # Ingen sortering: rækkefølgen ER prioriteringen.
        self.tabel.cellClicked.connect(self._klik)
        self.tabel.cellDoubleClicked.connect(self._dobbeltklik)
        self.tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabel.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.tom)
        layout.addWidget(self.tabel, 1)

    def vis(self, poster, i_dag: date):
        self._poster = list(poster)
        self.tom.setVisible(not poster)
        self.tabel.setVisible(bool(poster))
        self.tabel.setRowCount(len(poster))
        fed = QFont()
        fed.setBold(True)
        for r, p in enumerate(poster):
            o, sag = p.opgave, p.sag
            modul = MODUL_NAVN.get(sag.PROCES, "")
            frist_stil = {sp.FORSINKET: TONER["roed"], sp.NAERMER_SIG: TONER["gul"]}.get(
                p.tidsrisiko)
            hvorfor = f"{p.grund}: {p.forklaring}" + (f" · {p.aarsag}" if p.aarsag else "")
            celler = (
                (f"{sag.navn}\n{modul}", f"{modul} · {sag.status}", None),
                (o.navn, o.beskrivelse, None),
                (p.omraade or "–", "", None),
                (sp.ejer(o), "", None),
                (vis_dato(o.frist) if o.frist else "–", p.tidsrisiko, frist_stil),
                (p.tilstand, sp.FORKLARING.get(p.tilstand, ""), spor_stil(p.tilstand)),
                (hvorfor, hvorfor, None),
                (_HANDLING_TEKST[p.handling], "Klik for at udføre", None),
            )
            for k, (tekst, tip, stil) in enumerate(celler):
                item = QTableWidgetItem(tekst)
                if stil:
                    item.setData(STIL_ROLE, stil)
                if tip:
                    item.setToolTip(tip)
                if k == self._HANDLING:
                    item.setForeground(QColor(FARVER["primary_hover"]))
                    item.setFont(fed)
                self.tabel.setItem(r, k, item)

    def _klik(self, raekke, kolonne):
        if kolonne != self._HANDLING or raekke >= len(self._poster):
            return
        p = self._poster[raekke]
        if p.handling == kr.TILDEL:
            self.handling.emit(al.ANSVARLIG, p.sag.PROCES, p.sag.id, p.opgave.id)
        else:
            self.aabn_sag.emit(p.sag.PROCES, p.sag.id, p.handling_opgave_id)

    def _dobbeltklik(self, raekke, kolonne):
        if kolonne != self._HANDLING and raekke < len(self._poster):
            p = self._poster[raekke]
            self.aabn_sag.emit(p.sag.PROCES, p.sag.id, p.opgave.id)

    def _menu(self, pos):
        item = self.tabel.itemAt(pos)
        if item is None or item.row() >= len(self._poster):
            return
        p = self._poster[item.row()]
        opgave_menu(self.tabel, p.sag.PROCES, p.sag.id, p.opgave.id, self.aabn_sag,
                    self.handling, self.tabel.viewport().mapToGlobal(pos))


class DashboardSide(QWidget):
    vis_liste = Signal(str, str)        # (kontrolrum.TEAM, teamfilter)

    def __init__(self, rapporter, parent=None):
        super().__init__(parent)
        self._maal = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)
        hoved, self.dato_label = lav_sidehoved("Arbejdsoverblik", "")
        layout.addLayout(hoved)

        self.faner = QTabWidget()
        self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.faner.addTab(self._opbyg_kontrolrum(), "Kontrolrum")
        self.faner.addTab(self._opbyg_handling(), "Action Center")
        self.rapport = RapportPanel(rapporter)
        self.faner.addTab(self.rapport, "Nøgletal")
        self.faner.setTabToolTip(0, "Det, der kræver handling nu: overblik, arbejdskøer og "
                                    "de vigtigste opgaver")
        self.faner.setTabToolTip(1, "Alle afvigelser og opgaver med frist i dag")
        self.faner.setTabToolTip(2, "Behandlingstider, frister og arbejdsfordeling")
        layout.addWidget(self.faner, 1)

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_kontrolrum(self):
        side = QWidget()
        layout = scroll_side(side)
        layout.setContentsMargins(0, 12, 8, 12)
        layout.setSpacing(12)

        self.kort = {}
        raekke = QHBoxLayout()
        raekke.setSpacing(12)
        for tal in kr.overblik([], date.today()):
            kort = NoegletalKort(tal.navn, tal.noegle, tal.forklaring, ikon=True)
            kort.klikket.connect(self._kort_klikket)
            self.kort[tal.noegle] = kort
            raekke.addWidget(kort, 1)
        layout.addLayout(raekke)

        layout.addWidget(self._sektion("Arbejdskøer", "Medarbejdere med åbent arbejde pr. "
                                       "område. Klik for at åbne sagen – opgaverne ses dér."))
        gitter = QGridLayout()
        gitter.setSpacing(12)
        self.koe_lister = {}
        for i, koe in enumerate(kr.koeer([], date.today())):
            liste = ActionListe(koe.navn, koe.forklaring, vis_modul=koe.noegle in _KOE_MODUL,
                                parent=self, ikon=ikoner.pixmap(koe.ikon, _ikon_farve(), 20),
                                kan_arkivere=koe.noegle == kr.AFSLUTNING)
            liste.liste.setMinimumHeight(200)
            self.koe_lister[koe.noegle] = liste
            gitter.addWidget(liste.kort, i // 3, i % 3)
        for k in range(3):
            gitter.setColumnStretch(k, 1)
        layout.addLayout(gitter)

        self.haster_titel = self._sektion("Haster nu", "Forsinkelser, opstarter i risiko, "
                                          "opgaver uden ejer og opgaver, der står stille – "
                                          "vigtigste først.")
        layout.addWidget(self.haster_titel)
        kort = lav_kort(skygge=False)
        lag = QVBoxLayout(kort)
        lag.setContentsMargins(8, 8, 8, 8)
        self.haster = HasterTabel()
        lag.addWidget(self.haster)
        layout.addWidget(kort)
        return side

    @staticmethod
    def _sektion(titel, tekst):
        boks = QWidget()
        lag = QVBoxLayout(boks)
        lag.setContentsMargins(0, 8, 0, 0)
        lag.setSpacing(0)
        titel_label = QLabel(titel)
        titel_label.setObjectName("sektionTitel")
        tekst_label = QLabel(tekst)
        tekst_label.setObjectName("hjaelpTekst")
        tekst_label.setWordWrap(True)
        lag.addWidget(titel_label)
        lag.addWidget(tekst_label)
        boks.titel = titel_label
        return boks

    def _opbyg_handling(self):
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 12, 0, 0)
        lister = QHBoxLayout()
        lister.setSpacing(14)
        self.action = ActionListe(
            "Action Center",
            "Afvigelser og næste handling – klik for at åbne, højreklik for hurtige handlinger",
            parent=self,
        )
        self.dag = ActionListe("Dagsoversigt", "Opgaver med frist i dag", parent=self)
        lister.addWidget(self.action.kort, 3)
        lister.addWidget(self.dag.kort, 2)
        layout.addLayout(lister, 1)
        return side

    def handlingslister(self):
        """Alle lister med aabn_sag/handling-signaler (forbindes af hovedvinduet)."""
        return [self.action, self.dag, *self.koe_lister.values(), self.haster]

    ### ----- data -----------------------------------------------------------

    def _kort_klikket(self, noegle):
        maal = self._maal.get(noegle)
        if maal:
            self.vis_liste.emit(*maal)

    def opdater(self, sager_pr_modul: dict, alarmer, dagens, regler=None):
        """sager_pr_modul: {proces: aktive + arkiverede sager} (arkiverede bruges af nøgletal)."""
        i_dag = date.today()
        alle = [s for sager in sager_pr_modul.values() for s in sager]
        aktive = [s for s in alle if not s.arkiveret]

        for tal in kr.overblik(aktive, i_dag, regler):
            kort = self.kort[tal.noegle]
            kort.vaerdi.setText(str(tal.antal))
            kort.sub.setText(f"{tal.enhed} · klik for at se listen")
            kort.ikon.setPixmap(ikoner.pixmap(_KORT_IKON[tal.noegle], _ikon_farve(), 22))
            self._maal[tal.noegle] = tal.maal

        for koe in kr.koeer(aktive, i_dag, regler):
            liste = self.koe_lister[koe.noegle]
            liste.vis_alarmer(koe.poster, _KOE_TOM[koe.noegle])
            liste.antal.setToolTip(f"{len(koe.poster)} {koe.enhed}")
            liste.kort.ikon_label.setPixmap(ikoner.pixmap(koe.ikon, _ikon_farve(), 20))

        haster = kr.haster_nu(aktive, i_dag, regler)
        self.haster.vis(haster, i_dag)
        self.haster_titel.titel.setText(f"Haster nu ({len(haster)})")

        self.action.vis_alarmer(alarmer)
        self.dag.vis_opgaver(dagens)
        self.rapport.opdater(alle)
        self.dato_label.setText(
            f"Det, der kræver handling på tværs af onboarding og offboarding · "
            f"{dansk_dato(QDate.currentDate())}"
        )
