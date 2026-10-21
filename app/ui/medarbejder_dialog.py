"""Dialog til at oprette og redigere en medarbejder, inkl. udstyr."""
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.medarbejder import Medarbejder
from app.ui.hjaelpere import laes_dato


class MedarbejderDialog(QDialog):
    def __init__(self, parent=None, medarbejder=None, optagede_loennumre=()):
        super().__init__(parent)

        self.optagede_loennumre = {str(x) for x in optagede_loennumre}

        self.setWindowTitle(
            "Opret medarbejder" if medarbejder is None else "Rediger medarbejder"
        )
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(self._opbyg_stamdata())
        layout.addLayout(self._opbyg_udstyr())

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        layout.addWidget(self.fejl_label)
        layout.addWidget(self._opbyg_knapper())

        if medarbejder is not None:
            self._udfyld(medarbejder)
        self._opdater_udstyr_status()

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_stamdata(self):
        self.loennr_input = QLineEdit()
        self.navn_input = QLineEdit()

        self.dato_input = QDateEdit()
        self.dato_input.setCalendarPopup(True)
        self.dato_input.setDisplayFormat("dd-MM-yyyy")
        self.dato_input.setDate(QDate.currentDate())

        self.status_input = QComboBox()
        self.status_input.addItems(Medarbejder.STATUSER)

        self.kommentar_input = QLineEdit()

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Medarbejdernavn", self.navn_input)
        form.addRow("Fratrædelsesdato", self.dato_input)
        form.addRow("Status", self.status_input)
        form.addRow("Kommentar", self.kommentar_input)
        return form

    def _opbyg_udstyr(self):
        """Én række pr. udstyr: [x] Har udstyr  [x] Afleveret  (+ felt til Andet)."""
        boks = QVBoxLayout()
        boks.setSpacing(6)

        titel = QLabel("Udstyr")
        titel.setObjectName("sektionTitel")
        hjaelp = QLabel(
            "Kryds af hvad medarbejderen har, og marker det, når det er afleveret."
        )
        hjaelp.setObjectName("hjaelpTekst")
        self.udstyr_status_label = QLabel("")
        self.udstyr_status_label.setObjectName("hjaelpTekst")

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(2, 1)

        self.andet_input = QLineEdit()
        self.andet_input.setPlaceholderText("Hvad dækker 'Andet' over? fx nøgler, pc")

        self.udstyr_felter = {}
        for raekke, (noegle, navn) in enumerate(Medarbejder.UDSTYR):
            har = QCheckBox(navn)
            afleveret = QCheckBox("Afleveret")
            har.setCursor(Qt.CursorShape.PointingHandCursor)
            afleveret.setCursor(Qt.CursorShape.PointingHandCursor)
            har.toggled.connect(self._opdater_udstyr_status)
            afleveret.toggled.connect(self._opdater_udstyr_status)

            grid.addWidget(har, raekke, 0)
            grid.addWidget(afleveret, raekke, 1)
            if noegle == "andet":
                grid.addWidget(self.andet_input, raekke, 2)
            self.udstyr_felter[noegle] = (har, afleveret)

        boks.addWidget(titel)
        boks.addWidget(hjaelp)
        boks.addSpacing(4)
        boks.addLayout(grid)
        boks.addWidget(self.udstyr_status_label)
        return boks

    def _opbyg_knapper(self):
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        gem_knap = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem_knap.setText("Gem")
        gem_knap.setProperty("variant", "primary")
        gem_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        annuller_knap = knapper.button(QDialogButtonBox.StandardButton.Cancel)
        annuller_knap.setText("Annuller")
        annuller_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        return knapper

    def _udfyld(self, medarbejder):
        self.loennr_input.setText(str(medarbejder.loennr))
        self.navn_input.setText(medarbejder.navn)
        self.kommentar_input.setText(str(medarbejder.kommentar))

        dato = laes_dato(medarbejder.fratraedelsesdato)
        if dato.isValid():
            self.dato_input.setDate(dato)

        status_index = self.status_input.findText(medarbejder.status)
        if status_index >= 0:
            self.status_input.setCurrentIndex(status_index)

        for noegle, (har, afleveret) in self.udstyr_felter.items():
            post = medarbejder.udstyr[noegle]
            har.setChecked(post["har"])
            afleveret.setChecked(post["afleveret"])
        self.andet_input.setText(medarbejder.andet_beskrivelse)

    ### ----- udstyr ---------------------------------------------------------

    def _opdater_udstyr_status(self):
        """Holder "Afleveret"-felterne i trit med "Har udstyr" og viser x/y."""
        afleveret_antal = total = 0
        for noegle, (har, afleveret) in self.udstyr_felter.items():
            afleveret.setEnabled(har.isChecked())
            if not har.isChecked():
                afleveret.setChecked(False)
            if noegle == "andet":
                self.andet_input.setEnabled(har.isChecked())
            if har.isChecked():
                total += 1
                afleveret_antal += afleveret.isChecked()

        if total:
            self.udstyr_status_label.setText(f"{afleveret_antal}/{total} afleveret")
        else:
            self.udstyr_status_label.setText("Intet udstyr krydset af")

    ### ----- gem ------------------------------------------------------------

    def accept(self):
        data = self.hent_data()
        if not data["loennr"] or not data["navn"]:
            self.fejl_label.setText("Lønnr. og medarbejdernavn skal udfyldes.")
            return
        if data["loennr"] in self.optagede_loennumre:
            self.fejl_label.setText(
                "Der findes allerede en medarbejder med dette lønnr. "
                "(aktiv eller arkiveret)."
            )
            return
        if data["udstyr"]["andet"]["har"] and not data["andet_beskrivelse"]:
            self.fejl_label.setText("Skriv hvad 'Andet' dækker over.")
            self.andet_input.setFocus()
            return
        super().accept()

    def hent_data(self):
        """Samme format som Medarbejder.til_dict(), så fra_dict() kan bruges."""
        return {
            "loennr": self.loennr_input.text().strip(),
            "navn": self.navn_input.text().strip(),
            "fratraedelsesdato": self.dato_input.date().toString("yyyy-MM-dd"),
            "status": self.status_input.currentText(),
            "kommentar": self.kommentar_input.text().strip(),
            "udstyr": {
                noegle: {"har": har.isChecked(), "afleveret": afleveret.isChecked()}
                for noegle, (har, afleveret) in self.udstyr_felter.items()
            },
            "andet_beskrivelse": self.andet_input.text().strip(),
        }
