"""Dialog til at oprette eller redigere én opgave i en afviklingssag."""
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.opgave import Opgave
from app.ui.hjaelpere import laes_dato, lav_knap


class OpgaveDialog(QDialog):
    """Ændrer opgaven direkte ved Gem. Efter exec(): tjek self.slettet."""

    def __init__(self, parent, opgave=None, ansvarlige=(), standard_frist=""):
        super().__init__(parent)
        self.ny = opgave is None
        self.opgave = opgave or Opgave("", frist=standard_frist)
        self.slettet = False

        self.setWindowTitle("Ny opgave" if self.ny else "Rediger opgave")
        self.setMinimumWidth(480)

        self.navn_input = QLineEdit(self.opgave.navn)
        self.udstyr_input = QLineEdit(self.opgave.udstyr)
        self.udstyr_input.setPlaceholderText(
            "Fx 'Telefon og SIM-kort' – tom, hvis det er en intern opgave"
        )

        self.ansvarlig_input = QComboBox()
        self.ansvarlig_input.setEditable(True)
        self.ansvarlig_input.addItems(list(ansvarlige))
        self.ansvarlig_input.setCurrentText(self.opgave.ansvarlig)

        self.frist_input = QDateEdit()
        self.frist_input.setCalendarPopup(True)
        self.frist_input.setDisplayFormat("dd-MM-yyyy")
        frist = laes_dato(self.opgave.frist)
        self.frist_input.setDate(frist if frist.isValid() else QDate.currentDate())

        self.status_input = QComboBox()
        self.status_input.addItems(Opgave.STATUSER)
        self.status_input.setCurrentText(self.opgave.status)

        self.obligatorisk_input = QCheckBox("Skal være afsluttet, før sagen er afviklet")
        self.obligatorisk_input.setChecked(self.opgave.obligatorisk)

        self.begrundelse_input = QLineEdit(self.opgave.begrundelse)
        self.begrundelse_input.setPlaceholderText(
            "Påkrævet ved Undtaget, fx 'Havde intet tankkort'"
        )
        self.naeste_input = QLineEdit(self.opgave.naeste_handling)
        self.naeste_input.setPlaceholderText("Fx 'Ringer til medarbejderen fredag'")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("Opgave", self.navn_input)
        form.addRow("Udstyr", self.udstyr_input)
        form.addRow("Ansvarlig", self.ansvarlig_input)
        form.addRow("Frist", self.frist_input)
        form.addRow("Status", self.status_input)
        form.addRow("", self.obligatorisk_input)
        form.addRow("Begrundelse", self.begrundelse_input)
        form.addRow("Næste handling", self.naeste_input)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        gem_knap = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem_knap.setText("Gem")
        gem_knap.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        bund = QHBoxLayout()
        if not self.ny:
            slet_knap = lav_knap("Slet opgave", "danger")
            slet_knap.clicked.connect(self._slet)
            bund.addWidget(slet_knap)
        bund.addStretch()
        bund.addWidget(knapper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(self.fejl_label)
        layout.addLayout(bund)

    def fokuser_begrundelse(self):
        self.begrundelse_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _slet(self):
        self.slettet = True
        super().accept()

    def accept(self):
        navn = self.navn_input.text().strip()
        status = self.status_input.currentText()
        begrundelse = self.begrundelse_input.text().strip()
        if not navn:
            self.fejl_label.setText("Opgaven skal have et navn.")
            return
        if status == Opgave.UNDTAGET and not begrundelse:
            self.fejl_label.setText("Skriv hvorfor opgaven er undtaget.")
            self.fokuser_begrundelse()
            return

        self.opgave.navn = navn
        self.opgave.udstyr = self.udstyr_input.text().strip()
        self.opgave.ansvarlig = self.ansvarlig_input.currentText().strip()
        self.opgave.frist = self.frist_input.date().toString("yyyy-MM-dd")
        self.opgave.status = status
        self.opgave.obligatorisk = self.obligatorisk_input.isChecked()
        self.opgave.begrundelse = begrundelse
        self.opgave.naeste_handling = self.naeste_input.text().strip()
        super().accept()
