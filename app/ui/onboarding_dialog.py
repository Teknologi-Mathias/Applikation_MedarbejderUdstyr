"""Opret/rediger et onboardingforløb (kandidat → aktiv medarbejder).

Dialogen indsamler kun data. Reglerne (validering, kritisk overstyring,
annullering) håndhæves af OnboardingService, som controlleren kalder.
"""
from PySide6.QtCore import QDate
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

from app.domain.onboarding import OnboardingForloeb as OB
from app.ui.hjaelpere import laes_dato


class OnboardingDialog(QDialog):
    def __init__(self, parent, forloeb=None, skabeloner=(), omraader=(), ansvarlige=()):
        """skabeloner: aktive onboarding-skabeloner (filtreres efter stilling)."""
        super().__init__(parent)
        self.ny = forloeb is None
        self.forloeb = forloeb
        self.alle_skabeloner = list(skabeloner)
        self.setWindowTitle("Opret kandidat" if self.ny else "Rediger onboardingforløb")
        self.setMinimumWidth(560)

        self.navn_input = QLineEdit()
        self.loennr_input = QLineEdit()
        self.loennr_input.setPlaceholderText("Kan udfyldes senere")
        self.stilling_input = QComboBox()
        self.stilling_input.addItems(OB.STILLINGER)
        self.omraade_input = QComboBox()
        self.omraade_input.setEditable(True)
        self.omraade_input.addItems(list(omraader))
        self.ansvarlig_input = QComboBox()
        self.ansvarlig_input.setEditable(True)
        self.ansvarlig_input.addItems(list(ansvarlige))
        self.email_input = QLineEdit()
        self.ansaettelse_input = self._dato_felt()
        self.foerste_valgt = QCheckBox("Første arbejdsdag er en anden dag")
        self.foerste_input = self._dato_felt()
        self.foerste_valgt.toggled.connect(self.foerste_input.setEnabled)
        self.foerste_input.setEnabled(False)
        self.kommentar_input = QLineEdit()

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Navn", self.navn_input)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Stilling", self.stilling_input)
        form.addRow("Område", self.omraade_input)
        form.addRow("Ansvarlig", self.ansvarlig_input)
        form.addRow("E-mail", self.email_input)
        form.addRow("Ansættelsesdato", self.ansaettelse_input)
        form.addRow("", self.foerste_valgt)
        form.addRow("Første arbejdsdag", self.foerste_input)
        if self.ny:
            self.skabelon_input = QComboBox()
            form.addRow("Skabelon", self.skabelon_input)
            self.stilling_input.currentTextChanged.connect(self._fyld_skabeloner)
        form.addRow("Kommentar", self.kommentar_input)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(form)
        if not self.ny:
            layout.addLayout(self._opbyg_status())

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        layout.addWidget(self.fejl_label)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Opret forløb" if self.ny else "Gem")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        layout.addWidget(knapper)

        if forloeb is not None:
            self._udfyld(forloeb)
        else:
            self._fyld_skabeloner()

    @staticmethod
    def _dato_felt():
        felt = QDateEdit()
        felt.setCalendarPopup(True)
        felt.setDisplayFormat("dd-MM-yyyy")
        felt.setDate(QDate.currentDate().addDays(14))
        return felt

    def _fyld_skabeloner(self):
        stilling = self.stilling_input.currentText()
        self.skabeloner = [s for s in self.alle_skabeloner
                           if not s.get("stillinger") or stilling in s["stillinger"]]
        self.skabelon_input.clear()
        for s in self.skabeloner:
            self.skabelon_input.addItem(f"{s['navn']} (v{s.get('version', 1)})")
        self.skabelon_input.addItem("Ingen skabelon")

    def _opbyg_status(self):
        boks = QVBoxLayout()
        titel = QLabel("Status")
        titel.setObjectName("sektionTitel")
        f = self.forloeb
        forklaring = QLabel(
            f"Beregnes ud fra milepælene (lige nu: {f.beregnet_status()}). Springer en "
            "manuel status over manglende krav, er det en kritisk overstyring, som "
            "registreres i tidslinjen. Annullering flytter forløbet til arkivet."
        )
        forklaring.setObjectName("hjaelpTekst")
        forklaring.setWordWrap(True)
        self.laas_input = QCheckBox("Sæt status manuelt")
        self.status_input = QComboBox()
        self.status_input.addItems(OB.STATUSER)
        self.status_input.setCurrentText(f.status)
        self.begrundelse_input = QLineEdit(f.status_begrundelse)
        self.begrundelse_input.setPlaceholderText("Begrundelse (påkrævet)")
        self.overstyring_label = QLabel("")
        self.overstyring_label.setObjectName("advarsel")
        self.overstyring_label.setWordWrap(True)
        self.laas_input.toggled.connect(self._status_aendret)
        self.status_input.currentTextChanged.connect(self._status_aendret)
        self.laas_input.setChecked(bool(f.status_manuel))
        form = QFormLayout()
        form.addRow("Status", self.status_input)
        form.addRow("Begrundelse", self.begrundelse_input)
        for widget in (titel, forklaring, self.laas_input):
            boks.addWidget(widget)
        boks.addLayout(form)
        boks.addWidget(self.overstyring_label)
        self._status_aendret()
        return boks

    def _status_aendret(self):
        aktiv = self.laas_input.isChecked()
        self.status_input.setEnabled(aktiv)
        self.begrundelse_input.setEnabled(aktiv)
        status = self.status_input.currentText()
        mangler = self.forloeb.mangler_for(status) if aktiv else []
        if aktiv and self.forloeb.kraever_overstyring(status):
            self.overstyring_label.setText(
                "Kritisk overstyring – disse krav er ikke opfyldt: " + ", ".join(mangler)
            )
        elif aktiv and status == OB.STATUS_ANNULLERET:
            self.overstyring_label.setText("Forløbet annulleres og flyttes til arkivet.")
        else:
            self.overstyring_label.setText("")
        self.overstyring_label.setVisible(bool(self.overstyring_label.text()))

    def _udfyld(self, f):
        self.navn_input.setText(f.navn)
        self.loennr_input.setText(f.loennr)
        self.stilling_input.setCurrentText(f.stilling)
        self.omraade_input.setCurrentText(f.omraade)
        self.ansvarlig_input.setCurrentText(f.ansvarlig)
        self.email_input.setText(f.email)
        self.kommentar_input.setText(f.kommentar)
        for felt, vaerdi in ((self.ansaettelse_input, f.ansaettelsesdato),
                             (self.foerste_input, f.foerste_arbejdsdag)):
            dato = laes_dato(vaerdi)
            if dato.isValid():
                felt.setDate(dato)
        self.foerste_valgt.setChecked(bool(f.foerste_arbejdsdag))

    def accept(self):
        if not self.navn_input.text().strip():
            self.fejl_label.setText("Navn skal udfyldes.")
            return
        if not self.ny and self.laas_input.isChecked() and not self.begrundelse_input.text().strip():
            self.fejl_label.setText("En manuel status kræver en begrundelse.")
            return
        super().accept()

    def hent_data(self) -> dict:
        data = {
            "navn": self.navn_input.text().strip(),
            "loennr": self.loennr_input.text().strip(),
            "stilling": self.stilling_input.currentText(),
            "omraade": self.omraade_input.currentText().strip(),
            "ansvarlig": self.ansvarlig_input.currentText().strip(),
            "email": self.email_input.text().strip(),
            "ansaettelsesdato": self.ansaettelse_input.date().toString("yyyy-MM-dd"),
            "foerste_arbejdsdag": self.foerste_input.date().toString("yyyy-MM-dd")
            if self.foerste_valgt.isChecked() else "",
            "kommentar": self.kommentar_input.text().strip(),
        }
        if self.ny:
            index = self.skabelon_input.currentIndex()
            data["skabelon"] = self.skabeloner[index] if 0 <= index < len(self.skabeloner) else None
        else:
            manuel = self.laas_input.isChecked()
            data["status_manuel"] = self.status_input.currentText() if manuel else None
            data["status_begrundelse"] = self.begrundelse_input.text().strip() if manuel else ""
        return data

