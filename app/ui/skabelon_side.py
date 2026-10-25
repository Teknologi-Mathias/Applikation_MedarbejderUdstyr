"""Skabelonsider: arbejdsgange, mails og påmindelser.

Samme komponent bruges under Onboarding (arbejdsgange), Offboarding
(arbejdsgange + mails) og Indstillinger (påmindelser). Alle ændringer går
gennem SkabelonService (versionering, offline-spærring).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain import skabelon as sk
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved
from app.ui.theme import FARVER
from app.ui.skabelon_dialoger import (
    MailSkabelonDialog,
    PaamindelseDialog,
    SagSkabelonDialog,
)

# Pr. slags: (fanens navn, forklaring, kolonner, funktion der giver kolonneværdier)
_FANER = {
    sk.SAG: (
        "Arbejdsgange",
        "Opgaver der oprettes automatisk, når et forløb oprettes. Ændringer gemmes som "
        "ny version og påvirker kun nye forløb.",
        ("Navn", "Version · opgaver", "Stillinger / udstyr"),
        lambda s: (
            f"v{s.get('version', 1)} · {len(s['opgaver'])} opgaver",
            ", ".join(s.get("stillinger") or []) or ", ".join(
                o["udstyr"] for o in s["opgaver"] if o.get("udstyr")) or "Alle",
        ),
    ),
    sk.MAIL: (
        "Mails",
        "Rykkere og andre mails. Den relevante skabelon vælges ud fra kategorien.",
        ("Navn", "Kategori", "Tone"),
        lambda s: (s["kategori"], s["tone"]),
    ),
    sk.PAAMINDELSE: (
        "Påmindelser",
        "Windows-notifikationer, der vises når en foruddefineret regel rammer.",
        ("Navn", "Regel", "Titel"),
        lambda s: (
            sk.REGLER.get(s["regel"], ("Ukendt regel",))[0].replace(
                "X", str(s.get("dage", 0))
            ),
            s["titel"],
        ),
    ),
}


class SkabelonListe(QWidget):
    def __init__(self, side, slags):
        super().__init__()
        self.side = side
        self.slags = slags
        self._skabeloner = []
        _, forklaring, kolonner, _ = _FANER[slags]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)

        top = QHBoxLayout()
        tekst = QLabel(forklaring)
        tekst.setObjectName("pageSub")
        top.addWidget(tekst, 1)
        self.ny_knap = lav_knap("+ Ny skabelon", "primary")
        self.rediger_knap = lav_knap("Rediger")
        self.kopier_knap = lav_knap("Kopiér")
        self.aktiv_knap = lav_knap("Deaktivér")
        for knap in (self.ny_knap, self.rediger_knap, self.kopier_knap, self.aktiv_knap):
            top.addWidget(knap)
        layout.addLayout(top)

        self.ny_knap.clicked.connect(self.ny)
        self.rediger_knap.clicked.connect(self.rediger)
        self.kopier_knap.clicked.connect(self.kopier)
        self.aktiv_knap.clicked.connect(self.skift_aktiv)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        self.tabel = QTableWidget(0, len(kolonner) + 1)
        self.tabel.setHorizontalHeaderLabels([*kolonner, "Status"])
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(42)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        self.tabel.setColumnWidth(0, 280)
        self.tabel.setColumnWidth(1, 260)
        self.tabel.setColumnWidth(2, 300)
        self.tabel.doubleClicked.connect(lambda _index: self.rediger())
        self.tabel.itemSelectionChanged.connect(self._opdater_knapper)
        kort_layout.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    ### ----- visning --------------------------------------------------------

    def vis(self):
        skabeloner = [s for s in self.side.alle[self.slags]
                      if self.slags != sk.SAG or s.get("proces") == self.side.proces]
        self._skabeloner = skabeloner
        valgt = self._valgt_id()
        vaerdier = _FANER[self.slags][3]
        self.tabel.setRowCount(len(skabeloner))
        for raekke, s in enumerate(skabeloner):
            celler = (s["navn"], *vaerdier(s), "Aktiv" if s["aktiv"] else "Deaktiveret")
            for kolonne, tekst in enumerate(celler):
                item = QTableWidgetItem(tekst)
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                item.setToolTip(tekst)
                if not s["aktiv"]:
                    item.setForeground(QColor(FARVER["dim"]))
                self.tabel.setItem(raekke, kolonne, item)
            if s["id"] == valgt:
                self.tabel.selectRow(raekke)
        self._opdater_knapper()

    def _valgt_id(self):
        rows = self.tabel.selectionModel().selectedRows()
        if not rows:
            return None
        return self.tabel.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _valgt(self):
        valgt_id = self._valgt_id()
        return next((s for s in self._skabeloner if s["id"] == valgt_id), None)

    def _opdater_knapper(self):
        valgt = self._valgt()
        redigerbar = self.side.redigerbar
        self.ny_knap.setEnabled(redigerbar)
        for knap in (self.rediger_knap, self.kopier_knap, self.aktiv_knap):
            knap.setEnabled(redigerbar and valgt is not None)
        self.aktiv_knap.setText("Aktivér" if valgt and not valgt["aktiv"] else "Deaktivér")

    ### ----- handlinger -----------------------------------------------------

    def _aabn_editor(self, skabelon):
        if self.slags == sk.MAIL:
            dialog = MailSkabelonDialog(self, skabelon, self.side.hent_medarbejdere())
        elif self.slags == sk.PAAMINDELSE:
            dialog = PaamindelseDialog(self, skabelon, self.side.vis_testnotifikation)
        else:
            dialog = SagSkabelonDialog(self, skabelon)
        return dialog.skabelon if dialog.exec() else None

    def ny(self):
        resultat = self._aabn_editor(sk.ny_skabelon(self.slags, self.side.proces))
        if resultat:
            self.side.gem(self.slags, resultat)

    def rediger(self):
        valgt = self._valgt()
        if valgt and self.side.redigerbar:
            resultat = self._aabn_editor(valgt)
            if resultat:
                self.side.gem(self.slags, resultat)

    def kopier(self):
        valgt = self._valgt()
        if valgt:
            resultat = self._aabn_editor(sk.kopier(valgt))
            if resultat:
                self.side.gem(self.slags, resultat)

    def skift_aktiv(self):
        valgt = self._valgt()
        if valgt:
            self.side.skift_aktiv(self.slags, valgt)


class SkabelonSide(QWidget):
    def __init__(self, skabeloner, slags, proces=None, titel="Skabeloner", undertitel="",
                 hent_sager=lambda: [], vis_testnotifikation=None, indlejret=False):
        """slags: hvilke skabelontyper der vises som faner. proces: filter for arbejdsgange."""
        super().__init__()
        self.skabeloner = skabeloner
        self.proces = proces
        self.hent_medarbejdere = hent_sager
        self.vis_testnotifikation = vis_testnotifikation
        self.alle = {s: [] for s in sk.SLAGS}
        # Alle brugere må ændre skabeloner – dog ikke offline.
        self.redigerbar = True

        layout = QVBoxLayout(self)
        margin = 0 if indlejret else 32
        layout.setContentsMargins(margin, 0 if indlejret else 28, margin, 0 if indlejret else 28)
        layout.setSpacing(10)
        if not indlejret:
            hoved, _ = lav_sidehoved(titel, undertitel or (
                "Opret, redigér, kopiér og deaktivér skabeloner. "
                "Deaktiverede skabeloner bevares, men kan ikke vælges."))
            layout.addLayout(hoved)

        self.laast_label = QLabel("Skabeloner kan ikke ændres offline.")
        self.laast_label.setObjectName("info")
        layout.addWidget(self.laast_label)

        self.lister = {}
        if len(slags) == 1:
            liste = SkabelonListe(self, slags[0])
            self.lister[slags[0]] = liste
            layout.addWidget(liste, 1)
        else:
            self.faner = QTabWidget()
            self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
            for slag in slags:
                liste = SkabelonListe(self, slag)
                self.lister[slag] = liste
                index = self.faner.addTab(liste, _FANER[slag][0])
                self.faner.setTabToolTip(index, _FANER[slag][1])
            layout.addWidget(self.faner, 1)

    def saet_redigerbar(self, redigerbar):
        self.redigerbar = redigerbar
        self.laast_label.setVisible(not redigerbar)
        for liste in self.lister.values():
            liste._opdater_knapper()

    def opdater(self):
        alle = udfoer(self, self.skabeloner.hent_alle)
        if alle is FEJL:
            return
        self.alle = alle
        for liste in self.lister.values():
            liste.vis()

    def gem(self, slags, skabelon):
        udfoer(self, self.skabeloner.gem, slags, skabelon)
        self.opdater()

    def skift_aktiv(self, slags, skabelon):
        udfoer(self, self.skabeloner.skift_aktiv, slags, skabelon)
        self.opdater()
