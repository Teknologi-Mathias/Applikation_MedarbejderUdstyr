"""Siden Brugerkartotek: opret, slet og skift kode for brugere (kun administratorer)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import brugere, session
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved, vis_dato

BETA_TEKST = (
    "BETA – Adgangskoder er IKKE sikkert gemt. Brugerfilen ligger i datamappen "
    "og kan læses af alle med adgang til den. Brug aldrig en privat adgangskode "
    "eller en kode, I bruger andre steder."
)


def _beta_label():
    label = QLabel(BETA_TEKST)
    label.setObjectName("beta")
    label.setWordWrap(True)
    return label


class KodeDialog(QDialog):
    """Opret bruger (ny=True) eller skift adgangskode for en eksisterende bruger."""

    def __init__(self, parent, ny=True, brugernavn=""):
        super().__init__(parent)
        self.ny = ny
        self.setWindowTitle("Opret bruger" if ny else f"Skift adgangskode: {brugernavn}")
        self.setMinimumWidth(480)

        self.brugernavn_input = QLineEdit(brugernavn)
        self.navn_input = QLineEdit()
        self.rolle_input = QComboBox()
        self.rolle_input.addItems(brugere.ROLLER)
        self.rolle_input.setCurrentText(brugere.ROLLE_BRUGER)
        self.kode_input = QLineEdit()
        self.kode_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gentag_input = QLineEdit()
        self.gentag_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.forstaaet_input = QCheckBox(
            "Jeg har læst BETA-advarslen"
        )

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        if ny:
            form.addRow("Brugernavn", self.brugernavn_input)
            form.addRow("Navn", self.navn_input)
            form.addRow("Rolle", self.rolle_input)
        form.addRow("Adgangskode", self.kode_input)
        form.addRow("Gentag kode", self.gentag_input)

        rolle_hjaelp = QLabel(
            "Administrator: alt, inkl. brugere, skabeloner, data og sletning. "
            "Bruger: arbejder med sager, rykkere og arkiv."
        )
        rolle_hjaelp.setObjectName("hjaelpTekst")
        rolle_hjaelp.setWordWrap(True)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Opret bruger" if ny else "Skift kode")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(_beta_label())
        layout.addLayout(form)
        if ny:
            layout.addWidget(rolle_hjaelp)
        layout.addWidget(self.forstaaet_input)
        layout.addWidget(self.fejl_label)
        layout.addWidget(knapper)

    def accept(self):
        if self.kode_input.text() != self.gentag_input.text():
            self.fejl_label.setText("De to adgangskoder er ikke ens.")
            return
        if not self.forstaaet_input.isChecked():
            self.fejl_label.setText("Bekræft, at du har læst BETA-advarslen.")
            return
        try:
            if self.ny:
                brugere.opret(
                    self.brugernavn_input.text(),
                    self.navn_input.text(),
                    self.rolle_input.currentText(),
                    self.kode_input.text(),
                )
            else:
                brugere.skift_kode(self.brugernavn_input.text(), self.kode_input.text())
        except brugere.BrugerFejl as fejl:
            self.fejl_label.setText(str(fejl))
            return
        super().accept()


class BrugerSide(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        hoved, _ = lav_sidehoved(
            "Brugerkartotek",
            "Brugere med adgang til IN-BASE og deres rolle. Kun administratorer ser denne side.",
        )
        layout.addLayout(hoved)
        layout.addWidget(_beta_label())

        knapper = QHBoxLayout()
        opret = lav_knap("+ Opret bruger", "primary")
        kode = lav_knap("Skift adgangskode")
        slet = lav_knap("Slet bruger", "danger")
        opret.clicked.connect(self.opret)
        kode.clicked.connect(self.skift_kode)
        slet.clicked.connect(self.slet)
        knapper.addStretch()
        for knap in (opret, kode, slet):
            knapper.addWidget(knap)
        layout.addLayout(knapper)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        self.tabel = QTableWidget(0, 4)
        self.tabel.setHorizontalHeaderLabels(["Brugernavn", "Navn", "Rolle", "Oprettet"])
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(42)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        for kolonne, bredde in enumerate((200, 260, 160)):
            self.tabel.setColumnWidth(kolonne, bredde)
        kort_layout.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    def opdater(self):
        alle = [brugere.offentlig(b) for b in brugere.hent()]
        self.tabel.setRowCount(len(alle))
        for raekke, b in enumerate(alle):
            mig = b["brugernavn"] == session.brugernavn()
            celler = (
                b["brugernavn"] + ("  (dig)" if mig else ""),
                b.get("navn", ""),
                b.get("rolle", ""),
                vis_dato(b.get("oprettet", "")[:10]),
            )
            for kolonne, tekst in enumerate(celler):
                item = QTableWidgetItem(tekst)
                item.setData(Qt.ItemDataRole.UserRole, b["brugernavn"])
                self.tabel.setItem(raekke, kolonne, item)

    def _valgt(self):
        rows = self.tabel.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Ingen valgt", "Vælg en bruger i listen først.")
            return None
        return self.tabel.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def opret(self):
        if KodeDialog(self, ny=True).exec():
            self.opdater()

    def skift_kode(self):
        brugernavn = self._valgt()
        if brugernavn and KodeDialog(self, ny=False, brugernavn=brugernavn).exec():
            QMessageBox.information(self, "Adgangskode", f"Koden for {brugernavn} er skiftet.")

    def slet(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        svar = QMessageBox.warning(
            self, "Slet bruger",
            f"Vil du slette brugeren '{brugernavn}'?\n\n"
            "Brugerens navn bevares i tidslinjerne, men brugeren kan ikke længere logge på.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return
        try:
            brugere.slet(brugernavn, session.brugernavn())
        except brugere.BrugerFejl as fejl:
            QMessageBox.warning(self, "Slet bruger", str(fejl))
            return
        self.opdater()
