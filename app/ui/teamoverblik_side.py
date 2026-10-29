"""Teamoverblik: alle aktive onboardingforløb og deres parallelle arbejdsspor.

Én række pr. medarbejder med klarhed til opstart, fremdrift, næste handling og
dens ejer. Standardvisningen er kompakt; "Alle arbejdsspor" viser desuden en
kolonne pr. spor (HR, kontrakt, tøj, telefon …) – spor uden opgaver hos nogen
skjules. Højreklik på overskrifterne vælger selv kolonnerne.

Hver spor-celle viser sporets status som tekst; værktøjstippet viser næste
handling og ejer. Klik på en spor-celle eller næste handling åbner sagen på
den relevante opgave.

Nøgletallene øverst er klikbare og sætter det tilsvarende filter. Alt beregnes
af app/services/teamoverblik.py og app/domain/arbejdsspor.py.
"""
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app import session
from app.domain import arbejdsspor as sp
from app.domain.opgave import Opgave
from app.services import teamoverblik as tov
from app.ui.hjaelpere import lav_kort, lav_sidehoved, vis_dato
from app.ui.theme import spor_stil
from app.ui.widgets import ID_ROLE, SORT_ROLE, STIL_ROLE, PilleDelegate, SortItem

OPGAVE_ROLE = Qt.ItemDataRole.UserRole + 3
_FASTE = ("Medarbejder", "Første dag", "Opstart", "Fremdrift", "Næste handling", "Ansvarlig")
# Sporenes kolonner (Øvrigt kun, hvis et forløb har opgaver uden spor).
_SPOR = [s for s in sp.SPOR if s[0] != sp.OEVRIGT]

KOMPAKT = "kompakt"
DETALJERET = "detaljeret"


class NoegletalKort(QFrame):
    """Et klikbart nøgletal (sætter et filter). ikon=True giver plads til et ikon
    (self.ikon) og en undertekst (self.sub), fx hvad tallet tæller."""
    klikket = Signal(str)

    def __init__(self, titel: str, filter_: str, forklaring: str, ikon: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.filter = filter_
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{forklaring}. Klik for at vise listen.")
        lag = QVBoxLayout(self)
        lag.setContentsMargins(14, 10, 14, 10)
        lag.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.ikon = QLabel()
        self.ikon.setVisible(ikon)
        titel_label = QLabel(titel)
        titel_label.setObjectName("statTitle")
        titel_label.setWordWrap(True)
        top.addWidget(self.ikon)
        top.addWidget(titel_label, 1)
        self.vaerdi = QLabel("0")
        self.vaerdi.setObjectName("statValue")
        self.sub = QLabel("")
        self.sub.setObjectName("statSub")
        self.sub.setWordWrap(True)
        self.sub.setVisible(ikon)
        lag.addLayout(top)
        lag.addWidget(self.vaerdi)
        lag.addWidget(self.sub)

    def mousePressEvent(self, event):
        self.klikket.emit(self.filter)
        super().mousePressEvent(event)


def fremdrift(sag) -> tuple[int, int]:
    """(lukkede, i alt) blandt de relevante obligatoriske opgaver."""
    relevante = [o for o in sag.opgaver if o.obligatorisk and o.status != Opgave.UNDTAGET]
    return sum(o.afsluttet for o in relevante), len(relevante)


class TeamoverblikSide(QWidget):
    aabn_sag = Signal(str, str, str)            # (proces, sag_id, opgave_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sager = []
        self._skjulte = set()                   # kolonner, brugeren selv har skjult
        self.risiko_dage = 7
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)
        hoved, _ = lav_sidehoved(
            "Teamoverblik",
            "Alle aktive onboardingforløb på tværs af afdelinger. Hvert spor har sin egen "
            "status – klik på et spor eller næste handling for at åbne opgaven.")
        layout.addLayout(hoved)

        self.kort = {}
        gitter = QGridLayout()
        gitter.setSpacing(10)
        for i, tal in enumerate(tov.noegletal([], date.today())):
            kort = NoegletalKort(tal.navn, tal.filter, tal.forklaring)
            kort.klikket.connect(self.vaelg_filter)
            self.kort[tal.navn] = kort
            gitter.addWidget(kort, 0, i)
        layout.addLayout(gitter)

        filtre = QHBoxLayout()
        self.filter_input = QComboBox()
        for noegle, navn in tov.TEAM_FILTRE:
            self.filter_input.addItem(navn, noegle)
        self.filter_input.currentIndexChanged.connect(lambda _i: self._vis())
        self.visning_input = QComboBox()
        self.visning_input.addItem("Kompakt", KOMPAKT)
        self.visning_input.addItem("Alle arbejdsspor", DETALJERET)
        self.visning_input.setToolTip("Kompakt: klarhed, næste handling og ansvarlig.\n"
                                      "Alle arbejdsspor: én kolonne pr. spor.\n"
                                      "Højreklik på overskrifterne for at vælge kolonner.")
        self.visning_input.currentIndexChanged.connect(lambda _i: self._kolonner())
        self.soeg = QLineEdit()
        self.soeg.setPlaceholderText("Søg på medarbejder, stilling eller område…")
        self.soeg.setClearButtonEnabled(True)
        self.soeg.textChanged.connect(lambda _t: self._vis())
        filtre.addWidget(QLabel("Vis"))
        filtre.addWidget(self.filter_input)
        filtre.addWidget(self.visning_input)
        filtre.addWidget(self.soeg, 1)
        layout.addLayout(filtre)

        kort = lav_kort(skygge=False)
        lag = QVBoxLayout(kort)
        lag.setContentsMargins(8, 8, 8, 8)
        self.tom = QLabel("")
        self.tom.setObjectName("hjaelpTekst")
        self.tom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabel = QTableWidget(0, len(_FASTE) + len(_SPOR))
        self.tabel.setHorizontalHeaderLabels(list(_FASTE) + [navn for _, navn in _SPOR])
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(42)
        self.tabel.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        for k, bredde in enumerate((180, 100, 140, 90, 260, 170)):
            self.tabel.setColumnWidth(k, bredde)
        pille = PilleDelegate(self.tabel)
        self.tabel.setItemDelegateForColumn(2, pille)
        for k in range(len(_FASTE), len(_FASTE) + len(_SPOR)):
            self.tabel.setColumnWidth(k, 116)
            self.tabel.setItemDelegateForColumn(k, pille)
        self.tabel.setSortingEnabled(True)
        self.tabel.sortItems(1, Qt.SortOrder.AscendingOrder)     # første arbejdsdag først
        self.tabel.cellClicked.connect(self._klik)
        header = self.tabel.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._kolonne_menu)
        lag.addWidget(self.tom)
        lag.addWidget(self.tabel, 1)
        layout.addWidget(kort, 1)
        self._kolonner()

    def vaelg_filter(self, filter_: str) -> None:
        self.filter_input.setCurrentIndex(self.filter_input.findData(filter_))

    def opdater(self, sager, risiko_dage: int = 7):
        self._sager = [s for s in sager if not s.arkiveret]
        self.risiko_dage = risiko_dage
        for tal in tov.noegletal(self._sager, date.today(), risiko_dage):
            self.kort[tal.navn].vaerdi.setText(str(tal.antal))
        self._vis()

    ### ----- kolonner -------------------------------------------------------

    def _kolonner(self):
        """Kompakt: kun de faste kolonner. Alle arbejdsspor: også spor, som mindst ét
        forløb har opgaver i. Kolonner, brugeren har skjult, forbliver skjulte."""
        detaljeret = self.visning_input.currentData() == DETALJERET
        # Kompakt: næste handling fylder resten af bredden; detaljeret: vandret rulning.
        self.tabel.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Interactive if detaljeret else QHeaderView.ResizeMode.Stretch)
        if detaljeret:
            self.tabel.setColumnWidth(4, 260)
        brugte = {sp.spor_for(o) for s in self._sager for o in s.opgaver}
        for k in range(self.tabel.columnCount()):
            synlig = k < len(_FASTE) or (detaljeret and _SPOR[k - len(_FASTE)][0] in brugte)
            self.tabel.setColumnHidden(k, not synlig or k in self._skjulte)

    def _kolonne_menu(self, pos):
        menu = QMenu(self)
        detaljeret = self.visning_input.currentData() == DETALJERET
        for k in range(self.tabel.columnCount()):
            if k >= len(_FASTE) and not detaljeret:
                break
            handling = menu.addAction(self.tabel.horizontalHeaderItem(k).text())
            handling.setCheckable(True)
            handling.setChecked(k not in self._skjulte)
            handling.setEnabled(k != 0)           # medarbejderen vises altid
            handling.toggled.connect(lambda til, k=k: self._skift_kolonne(k, til))
        menu.exec(self.tabel.horizontalHeader().mapToGlobal(pos))

    def _skift_kolonne(self, kolonne, synlig):
        (self._skjulte.discard if synlig else self._skjulte.add)(kolonne)
        self._kolonner()

    ### ----- visning --------------------------------------------------------

    def _vis(self):
        i_dag = date.today()
        filter_ = self.filter_input.currentData()
        soeg = self.soeg.text().strip().lower()
        sager = [s for s in self._sager
                 if tov.sag_matcher(s, filter_, i_dag, session.brugernavn() or "",
                                   session.afdelinger(), self.risiko_dage)
                 and (not soeg or soeg in f"{s.navn} {getattr(s, 'stilling', '')} "
                                           f"{getattr(s, 'omraade', '')}".lower())]
        self.tom.setText("Ingen forløb matcher filteret." if self._sager else
                         "Der er ingen aktive onboardingforløb.")
        self.tom.setVisible(not sager)
        self.tabel.setVisible(bool(sager))
        self.tabel.setSortingEnabled(False)
        self.tabel.setRowCount(len(sager))
        for r, sag in enumerate(sager):
            klar = sp.klarhed(sag, i_dag, self.risiko_dage)
            naeste = tov.naeste_handling(sag, i_dag)
            naeste_id = naeste.naeste.id if naeste and naeste.naeste else ""
            start = sag.maaldato()
            lukkede, i_alt = fremdrift(sag)
            celler = [
                (sag.navn, sag.navn.lower(), None, sag.beskrivelse(), ""),
                (vis_dato(start) if start else "–", start or "9999", None, "", ""),
                (klar.niveau, klar.niveau, spor_stil(klar.niveau),
                 "\n".join(klar.aarsager) or klar.niveau, ""),
                (f"{lukkede}/{i_alt}", lukkede / i_alt if i_alt else 1.0, None,
                 "Lukkede af de relevante obligatoriske opgaver", ""),
                (f"{naeste.navn}: {naeste.tekst}" if naeste else "–",
                 naeste.navn if naeste else "", None,
                 f"{naeste.status} · Ejer: {naeste.ejer}" if naeste else "", naeste_id),
                (naeste.ejer if naeste else "–", naeste.ejer if naeste else "", None,
                 "Ejer af næste handling", naeste_id),
            ]
            for noegle, navn in _SPOR:
                status = sp.spor_status(sag, noegle, i_dag)
                if status is None:
                    celler.append(("–", "", None, f"{navn}: ingen opgaver", ""))
                    continue
                tip = f"{navn}: {status.status} ({status.afsluttede}/{status.total} afsluttet)"
                if status.tekst:
                    tip += f"\n{status.tekst}"
                if status.ejer:
                    tip += f"\nEjer: {status.ejer}"
                celler.append((status.status, status.status, spor_stil(status.status), tip,
                               status.naeste.id if status.naeste else ""))
            for k, (tekst, noegle, stil, tip, opgave_id) in enumerate(celler):
                item = SortItem(tekst)
                item.setData(SORT_ROLE, noegle)
                item.setData(ID_ROLE, sag.id)
                item.setData(OPGAVE_ROLE, (sag.PROCES, opgave_id))
                if stil:
                    item.setData(STIL_ROLE, stil)
                if tip:
                    item.setToolTip(tip)
                self.tabel.setItem(r, k, item)
        self.tabel.setSortingEnabled(True)
        self._kolonner()

    def _klik(self, raekke, kolonne):
        item = self.tabel.item(raekke, kolonne)
        if item is None:
            return
        proces, opgave_id = item.data(OPGAVE_ROLE)
        # Navnet åbner sagen; et spor eller næste handling åbner den relevante opgave.
        if kolonne == 0 or opgave_id:
            self.aabn_sag.emit(proces, item.data(ID_ROLE), opgave_id)
