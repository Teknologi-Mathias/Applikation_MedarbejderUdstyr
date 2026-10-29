"""Dialog til at oprette og redigere en medarbejders stamdata og status.

Opgaverne redigeres i afviklingssagen (sag_dialog.py), ikke her.
"""
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.domain.offboarding import Medarbejder
from app.domain.skabelon import gyldig_email
from app.ui.hjaelpere import laes_dato


class MedarbejderDialog(QDialog):
    def __init__(self, parent=None, medarbejder=None, optagede_loennumre=(),
                 skabeloner=()):
        super().__init__(parent)

        self.optagede_loennumre = {str(x) for x in optagede_loennumre}
        self.skabeloner = list(skabeloner)
        self.ny = medarbejder is None

        self.setWindowTitle("Opret medarbejder" if self.ny else "Rediger medarbejder")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(self._opbyg_stamdata())
        layout.addLayout(self._opbyg_status(medarbejder))

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        layout.addWidget(self.fejl_label)
        layout.addWidget(self._opbyg_knapper())

        if medarbejder is not None:
            self._udfyld(medarbejder)
        self._laas_skiftet()

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_stamdata(self):
        self.loennr_input = QLineEdit()
        self.navn_input = QLineEdit()

        self.dato_input = QDateEdit()
        self.dato_input.setCalendarPopup(True)
        self.dato_input.setDisplayFormat("dd-MM-yyyy")
        self.dato_input.setDate(QDate.currentDate())

        self.kommentar_input = QLineEdit()
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Bruges til rykkere, fx privat e-mail")
        self.tracking_input = QLineEdit()
        self.tracking_input.setPlaceholderText("Link til sporing af returpakken (valgfrit)")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Medarbejdernavn", self.navn_input)
        form.addRow("E-mail", self.email_input)
        form.addRow("Sidste arbejdsdag", self.dato_input)

        if self.ny:
            self.skabelon_input = QComboBox()
            self.skabelon_input.addItems([s["navn"] for s in self.skabeloner])
            form.addRow("Skabelon", self.skabelon_input)
            hjaelp = QLabel(
                "Afviklingssagens opgaver oprettes ud fra skabelonen, med frister "
                "regnet fra sidste arbejdsdag. Skabeloner rettes på siden Skabeloner."
            )
            hjaelp.setObjectName("hjaelpTekst")
            hjaelp.setWordWrap(True)
            form.addRow("", hjaelp)
        else:
            hjaelp = QLabel("Ændres datoen, flyttes åbne opgavers frister tilsvarende.")
            hjaelp.setObjectName("hjaelpTekst")
            form.addRow("", hjaelp)

        # Aflevering (returpakke og kommentar) er under udvikling: felterne vises
        # låst, og eksisterende værdier bevares uændret ved gem.
        for felt in (self.tracking_input, self.kommentar_input):
            felt.setEnabled(False)
        form.addRow("Tracking-link", self.tracking_input)
        form.addRow("Kommentar", self.kommentar_input)
        udvikling = QLabel("Aflevering (tracking og kommentar) er under udvikling.")
        udvikling.setObjectName("hjaelpTekst")
        form.addRow("", udvikling)
        return form

    def _opbyg_status(self, medarbejder):
        boks = QVBoxLayout()
        boks.setSpacing(8)

        titel = QLabel("Status")
        titel.setObjectName("sektionTitel")
        beregnet = (
            medarbejder.beregnet_status() if medarbejder is not None
            else Medarbejder.STATUS_AFVENTER
        )
        forklaring = QLabel(
            f"Beregnes automatisk ud fra opgaverne (lige nu: {beregnet})."
        )
        forklaring.setObjectName("hjaelpTekst")

        self.laas_input = QCheckBox("Lås status manuelt")
        self.laas_input.setCursor(Qt.CursorShape.PointingHandCursor)
        self.laas_input.toggled.connect(self._laas_skiftet)

        self.status_input = QComboBox()
        self.status_input.addItems(Medarbejder.STATUSER)
        self.status_input.setCurrentText(beregnet)
        self.begrundelse_input = QLineEdit()
        self.begrundelse_input.setPlaceholderText("Begrundelse (påkrævet)")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Låst status", self.status_input)
        form.addRow("Begrundelse", self.begrundelse_input)

        boks.addWidget(titel)
        boks.addWidget(forklaring)
        boks.addWidget(self.laas_input)
        boks.addLayout(form)
        return boks

    def _opbyg_knapper(self):
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        gem_knap = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem_knap.setText("Opret sag" if self.ny else "Gem")
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
        self.email_input.setText(medarbejder.email)
        self.tracking_input.setText(medarbejder.tracking_link)

        dato = laes_dato(medarbejder.fratraedelsesdato)
        if dato.isValid():
            self.dato_input.setDate(dato)

        if medarbejder.status_manuel:
            self.laas_input.setChecked(True)
            self.status_input.setCurrentText(medarbejder.status_manuel)
            self.begrundelse_input.setText(medarbejder.status_begrundelse)

    def _laas_skiftet(self):
        laast = self.laas_input.isChecked()
        self.status_input.setEnabled(laast)
        self.begrundelse_input.setEnabled(laast)

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
        if data["email"] and not gyldig_email(data["email"]):
            self.fejl_label.setText("E-mailadressen ser ikke gyldig ud.")
            self.email_input.setFocus()
            return
        if data["status_manuel"] and not data["status_begrundelse"]:
            self.fejl_label.setText("Skriv hvorfor status låses manuelt.")
            self.begrundelse_input.setFocus()
            return
        super().accept()

    def hent_data(self):
        laast = self.laas_input.isChecked()
        skabelon = None
        if self.ny and self.skabeloner:
            skabelon = self.skabeloner[self.skabelon_input.currentIndex()]
        return {
            "loennr": self.loennr_input.text().strip(),
            "navn": self.navn_input.text().strip(),
            "fratraedelsesdato": self.dato_input.date().toString("yyyy-MM-dd"),
            "kommentar": self.kommentar_input.text().strip(),
            "email": self.email_input.text().strip(),
            "tracking_link": self.tracking_input.text().strip(),
            "skabelon": skabelon,
            "status_manuel": self.status_input.currentText() if laast else None,
            "status_begrundelse": self.begrundelse_input.text().strip() if laast else "",
        }
