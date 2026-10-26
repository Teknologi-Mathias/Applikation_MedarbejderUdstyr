"""Opret/rediger et onboardingforløb: grundoplysninger og HR's behovsregistrering.

Formularen er delt i sektioner (grundoplysninger, arbejdstøj, telefon, e-mail,
firmabil, oplæring) og ændrer sig efter valgene: fravalgte felter deaktiveres,
og udstyr, som stillingen ikke kan få, er låst. Ved redigering vises status på
de opgaver, behovet har skabt – behovet er ikke det samme som udførelsen.

Dialogen indsamler kun data. Reglerne (validering, betingede opgaver, kritisk
overstyring, annullering) håndhæves af OnboardingService.
"""
from datetime import date

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain import arbejdsspor as sp
from app.domain import behov as bh
from app.domain.onboarding import OnboardingForloeb as OB
from app.services.onboarding_service import (
    BEHOV_REGISTRERET,
    BOOKING,
    OPLAERING_BOOKET,
    booking_tekst,
    opgave_med_noegle,
)
from app.ui.hjaelpere import laes_dato


class OnboardingDialog(QDialog):
    def __init__(self, parent, forloeb=None, skabeloner=(), omraader=(), ansvarlige=()):
        """skabeloner: aktive onboarding-skabeloner (filtreres efter stilling)."""
        super().__init__(parent)
        self.ny = forloeb is None
        self.forloeb = forloeb
        self.alle_skabeloner = list(skabeloner)
        self.setWindowTitle("Opret kandidat" if self.ny else "Rediger onboardingforløb")
        self.setMinimumWidth(620)
        self.resize(660, 760)

        indhold = QWidget()
        self.layout_indhold = QVBoxLayout(indhold)
        self.layout_indhold.setContentsMargins(24, 22, 24, 12)
        self.layout_indhold.setSpacing(10)
        self._opbyg_grundoplysninger(omraader, ansvarlige)
        self._opbyg_toej()
        self._opbyg_telefon_mail_bil()
        self._opbyg_oplaering()
        if not self.ny:
            self.layout_indhold.addLayout(self._opbyg_status())
        self.layout_indhold.addStretch()

        rul = QScrollArea()
        rul.setWidgetResizable(True)
        rul.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rul.setWidget(indhold)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Opret forløb" if self.ny else "Gem")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.addWidget(rul, 1)
        bund = QVBoxLayout()
        bund.setContentsMargins(24, 0, 24, 0)
        bund.addWidget(self.fejl_label)
        bund.addWidget(knapper)
        layout.addLayout(bund)

        if forloeb is not None:
            self._udfyld(forloeb)
        else:
            self._fyld_skabeloner()
        self.stilling_input.currentTextChanged.connect(self._opdater_valg)
        self._opdater_valg()

    ### ----- sektioner -------------------------------------------------------

    def _sektion(self, titel, hjaelp=""):
        label = QLabel(titel)
        label.setObjectName("sektionTitel")
        self.layout_indhold.addWidget(label)
        if hjaelp:
            tekst = QLabel(hjaelp)
            tekst.setObjectName("hjaelpTekst")
            tekst.setWordWrap(True)
            self.layout_indhold.addWidget(tekst)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        self.layout_indhold.addLayout(form)
        return form

    def _opgavestatus(self, form, *noegler):
        """Status på de opgaver, et behov har skabt (kun ved redigering)."""
        if self.ny:
            return
        linjer = []
        for noegle in noegler:
            opgave = opgave_med_noegle(self.forloeb, noegle)
            if opgave is None:
                continue
            status = sp.visningsstatus(self.forloeb, opgave, date.today())
            linje = f"{opgave.navn}: {status}"
            if status == sp.BLOKERET:
                linje += f" ({self.forloeb.blokeringsaarsag(opgave)})"
            linjer.append(linje)
        if linjer:
            label = QLabel("\n".join(linjer))
            label.setObjectName("hjaelpTekst")
            label.setWordWrap(True)
            form.addRow("Opgaver", label)

    def _opbyg_grundoplysninger(self, omraader, ansvarlige):
        form = self._sektion("Grundoplysninger")
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
        self.email_input.setPlaceholderText("Medarbejderens egen e-mail (kontakt)")
        self.ansaettelse_input = self._dato_felt()
        self.foerste_valgt = QCheckBox("Første arbejdsdag er en anden dag")
        self.foerste_input = self._dato_felt()
        self.foerste_valgt.toggled.connect(self.foerste_input.setEnabled)
        self.foerste_input.setEnabled(False)
        self.kommentar_input = QLineEdit()

        form.addRow("Navn", self.navn_input)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Stillingskategori", self.stilling_input)
        form.addRow("Ønsket område", self.omraade_input)
        form.addRow("Proceskoordinator", self.ansvarlig_input)
        form.addRow("Kontakt-e-mail", self.email_input)
        form.addRow("Ansættelsesdato", self.ansaettelse_input)
        form.addRow("", self.foerste_valgt)
        form.addRow("Første arbejdsdag", self.foerste_input)
        if self.ny:
            self.skabelon_input = QComboBox()
            form.addRow("Skabelon", self.skabelon_input)
            self.stilling_input.currentTextChanged.connect(self._fyld_skabeloner)
        form.addRow("Kommentar", self.kommentar_input)

    def _opbyg_toej(self):
        form = self._sektion("Arbejdstøj",
                             f"Vælg polo og/eller fleece. Antal 1-{bh.MAKS_ANTAL}; større "
                             "behov skrives i bemærkningen.")
        self.toej = {}
        for noegle, navn in bh.BEKLAEDNING.items():
            valgt = QCheckBox(navn)
            stoerrelse = QComboBox()
            stoerrelse.addItem("Vælg størrelse", "")
            for s in bh.STOERRELSER:
                stoerrelse.addItem(s, s)
            antal = QSpinBox()
            antal.setRange(1, bh.MAKS_ANTAL)
            raekke = QWidget()
            raekke_layout = QFormLayout(raekke)
            raekke_layout.setContentsMargins(0, 0, 0, 0)
            raekke_layout.addRow("Størrelse", stoerrelse)
            raekke_layout.addRow("Antal", antal)
            valgt.toggled.connect(raekke.setEnabled)
            raekke.setEnabled(False)
            form.addRow(valgt, raekke)
            self.toej[noegle] = (valgt, stoerrelse, antal)
        self.toej_bemaerkning = QLineEdit()
        form.addRow("Bemærkning", self.toej_bemaerkning)
        self._opgavestatus(form, *bh.BEKLAEDNING)

    def _opbyg_telefon_mail_bil(self):
        form = self._sektion("Telefon og abonnement")
        self.mobil_input = QCheckBox("Medarbejderen skal have mobiltelefon")
        self.abonnement_input = QComboBox()
        self.mobil_input.toggled.connect(self._opdater_valg)
        form.addRow(self.mobil_input)
        form.addRow("Abonnement", self.abonnement_input)
        self._opgavestatus(form, "telefon")

        kun = ", ".join(bh.UDVIDET_UDSTYR)
        form = self._sektion("E-mailkonto", f"Kun for {kun}.")
        self.mail_input = QCheckBox("Medarbejderen skal have en e-mailkonto")
        form.addRow(self.mail_input)
        self._opgavestatus(form, "email")

        form = self._sektion("Firmabil", f"Kun for {kun}. Administrationen får en opgave, når "
                                         "kontrakten er retur.")
        self.bil_input = QCheckBox("Medarbejderen skal have firmabil")
        self.bil_bemaerkning = QLineEdit()
        self.bil_bemaerkning.setPlaceholderText("Fx ønsket dato eller særlige behov")
        self.bil_input.toggled.connect(self._opdater_valg)
        form.addRow(self.bil_input)
        form.addRow("Bemærkning", self.bil_bemaerkning)
        self._opgavestatus(form, "firmabil")

    def _opbyg_oplaering(self):
        form = self._sektion("Oplæring",
                             "HR koordinerer vagten med oplæringsansvarlig. Et tidspunkt er "
                             "ikke en booking – bookingstatus vælges særskilt.")
        self.tid_valgt = QCheckBox("Tidspunkt for oplæringsvagt er aftalt")
        self.tid_input = QDateTimeEdit()
        self.tid_input.setCalendarPopup(True)
        self.tid_input.setDisplayFormat("dd-MM-yyyy HH:mm")
        self.tid_input.setDateTime(QDateTime(QDate.currentDate().addDays(14), QTime(8, 0)))
        self.tid_input.setEnabled(False)
        self.tid_valgt.toggled.connect(self.tid_input.setEnabled)
        self.booking_input = QComboBox()
        self.booking_input.addItems(list(BOOKING))
        form.addRow(self.tid_valgt)
        form.addRow("Tidspunkt", self.tid_input)
        form.addRow("Bookingstatus", self.booking_input)
        self._opgavestatus(form, OPLAERING_BOOKET, "oplaering_gennemfoert")

        afklaret = None if self.ny else opgave_med_noegle(self.forloeb, BEHOV_REGISTRERET)
        self.afklaret_input = QCheckBox("Behovet er afklaret (HR-opgaven markeres som udført)")
        if afklaret is not None and afklaret.afsluttet:
            self.afklaret_input.setChecked(True)
            self.afklaret_input.setEnabled(False)
        self.layout_indhold.addWidget(self.afklaret_input)

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

    ### ----- betinget visning ------------------------------------------------

    def _opdater_valg(self):
        """Låser udstyr, stillingen ikke kan få, og felter, der ikke er relevante."""
        stilling = self.stilling_input.currentText()
        udvidet = bh.tilladt_udvidet(stilling)
        for felt in (self.mail_input, self.bil_input):
            if not udvidet:
                felt.setChecked(False)
            felt.setEnabled(udvidet)
        tilladte = bh.tilladte_abonnementer(stilling)
        valgt = self.abonnement_input.currentData()
        self.abonnement_input.blockSignals(True)
        self.abonnement_input.clear()
        self.abonnement_input.addItem("Vælg abonnement", "")
        for a in tilladte:
            self.abonnement_input.addItem(a, a)
        index = self.abonnement_input.findData(valgt)
        self.abonnement_input.setCurrentIndex(index if index >= 0 else
                                              (1 if len(tilladte) == 1 else 0))
        self.abonnement_input.blockSignals(False)
        self.abonnement_input.setEnabled(self.mobil_input.isChecked())
        self.bil_bemaerkning.setEnabled(self.bil_input.isChecked())

    ### ----- status (kun redigering) -----------------------------------------

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

    ### ----- data ------------------------------------------------------------

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

        b = f.behov
        for noegle, (valgt, stoerrelse, antal) in self.toej.items():
            t = b.toej(noegle)
            valgt.setChecked(t.valgt)
            stoerrelse.setCurrentIndex(max(stoerrelse.findData(t.stoerrelse), 0))
            antal.setValue(t.antal or 1)
        self.toej_bemaerkning.setText(b.toej_bemaerkning)
        self.mobil_input.setChecked(b.mobil)
        self._opdater_valg()
        index = self.abonnement_input.findData(b.abonnement)
        if index >= 0:
            self.abonnement_input.setCurrentIndex(index)
        self.mail_input.setChecked(b.email)
        self.bil_input.setChecked(b.firmabil)
        self.bil_bemaerkning.setText(b.firmabil_bemaerkning)

        booket = opgave_med_noegle(f, OPLAERING_BOOKET)
        if booket is not None:
            tid = QDateTime.fromString(booket.planlagt[:16], "yyyy-MM-ddTHH:mm")
            if tid.isValid():
                self.tid_valgt.setChecked(True)
                self.tid_input.setDateTime(tid)
            if booking_tekst(booket) in BOOKING:
                self.booking_input.setCurrentText(booking_tekst(booket))
        else:
            for felt in (self.tid_valgt, self.tid_input, self.booking_input):
                felt.setEnabled(False)

    def hent_behov(self) -> bh.Behov:
        return bh.Behov(
            **{noegle: bh.Toej(valgt.isChecked(), stoerrelse.currentData() or "",
                               antal.value())
               for noegle, (valgt, stoerrelse, antal) in self.toej.items()},
            toej_bemaerkning=self.toej_bemaerkning.text().strip(),
            mobil=self.mobil_input.isChecked(),
            abonnement=self.abonnement_input.currentData() or "",
            email=self.mail_input.isChecked(),
            firmabil=self.bil_input.isChecked(),
            firmabil_bemaerkning=self.bil_bemaerkning.text().strip(),
        )

    def accept(self):
        fejl = []
        if not self.navn_input.text().strip():
            fejl.append("Navn skal udfyldes.")
        fejl += self.hent_behov().valider(self.stilling_input.currentText())
        if not self.ny and self.laas_input.isChecked() and not self.begrundelse_input.text().strip():
            fejl.append("En manuel status kræver en begrundelse.")
        if fejl:
            self.fejl_label.setText(" ".join(fejl))
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
            "behov": self.hent_behov().til_dict(),
            "behov_afklaret": self.afklaret_input.isChecked()
            and self.afklaret_input.isEnabled(),
        }
        if self.booking_input.isEnabled():
            data["oplaering_planlagt"] = (
                self.tid_input.dateTime().toString("yyyy-MM-ddTHH:mm:00")
                if self.tid_valgt.isChecked() else "")
            data["oplaering_booking"] = self.booking_input.currentText()
        if self.ny:
            index = self.skabelon_input.currentIndex()
            data["skabelon"] = self.skabeloner[index] if 0 <= index < len(self.skabeloner) else None
        else:
            manuel = self.laas_input.isChecked()
            data["status_manuel"] = self.status_input.currentText() if manuel else None
            data["status_begrundelse"] = self.begrundelse_input.text().strip() if manuel else ""
        return data
