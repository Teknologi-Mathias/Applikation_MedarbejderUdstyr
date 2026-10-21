"""Siden Skabeloner: faner for sager (udstyr), mails og påmindelser."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import skabeloner as sk
from app.data_manager import DataFejl
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
        "Udstyr ved oprettelse",
        "Opgaver og udstyr, der oprettes automatisk, når en medarbejder registreres.",
        ("Navn", "Opgaver", "Udstyr"),
        lambda s: (
            str(len(s["opgaver"])),
            ", ".join(o["udstyr"] for o in s["opgaver"] if o.get("udstyr")) or "–",
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
        skabeloner = self.side.alle[self.slags]
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
        return next((s for s in self.side.alle[self.slags] if s["id"] == valgt_id), None)

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
        resultat = self._aabn_editor(sk.ny_skabelon(self.slags))
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
            self.side.gem(self.slags, dict(valgt, aktiv=not valgt["aktiv"]))


class SkabelonSide(QWidget):
    def __init__(self, hent_medarbejdere, vis_testnotifikation=None):
        super().__init__()
        self.hent_medarbejdere = hent_medarbejdere
        self.vis_testnotifikation = vis_testnotifikation
        self.alle = {slags: [] for slags in sk.SLAGS}
        # Kun administratorer må ændre skabeloner; brugere kan se dem.
        self.redigerbar = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        hoved, _ = lav_sidehoved(
            "Skabeloner",
            "Opret, redigér, kopiér og deaktivér skabeloner. "
            "Deaktiverede skabeloner bevares, men kan ikke vælges.",
        )
        layout.addLayout(hoved)

        self.faner = QTabWidget()
        self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.lister = {}
        for slags in sk.SLAGS:
            liste = SkabelonListe(self, slags)
            self.lister[slags] = liste
            index = self.faner.addTab(liste, _FANER[slags][0])
            self.faner.setTabToolTip(index, _FANER[slags][1])
        self.laast_label = QLabel(
            "Kun administratorer kan ændre skabeloner. Du kan se dem her."
        )
        self.laast_label.setObjectName("info")
        layout.addWidget(self.laast_label)
        layout.addWidget(self.faner, 1)

    def saet_redigerbar(self, redigerbar):
        self.redigerbar = redigerbar
        self.laast_label.setVisible(not redigerbar)
        for liste in self.lister.values():
            liste._opdater_knapper()

    def opdater(self):
        try:
            self.alle = sk.hent_alle()
        except DataFejl as fejl:
            QMessageBox.warning(self, "Skabeloner", str(fejl))
            return
        for liste in self.lister.values():
            liste.vis()

    def gem(self, slags, skabelon):
        """Gemmer én skabelon (ny eller ændret) – genindlæser først filen."""
        try:
            alle = sk.hent_alle()
            liste = alle[slags]
            for i, eksisterende in enumerate(liste):
                if eksisterende["id"] == skabelon["id"]:
                    liste[i] = skabelon
                    break
            else:
                liste.append(skabelon)
            sk.gem_alle(alle)
        except (DataFejl, OSError) as fejl:
            QMessageBox.warning(self, "Skabeloner", f"Skabelonen kunne ikke gemmes:\n{fejl}")
        self.opdater()
