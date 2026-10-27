"""Opret/rediger et onboardingforløb i én dialog med tre områder:

1. Kandidat: navn, stilling, område, koordinator, kontakt og arbejdsgang.
2. Udstyr: HR's behov. Ved oprettelse indlæses stillingens standardprofil
   (Indstillinger → Organisation), når stillingen vælges; HR tilpasser og
   udfylder det personlige (størrelser, bemærkninger). Udstyr, stillingen ikke
   kan få, er skjult og låst. Et behov er ikke en bestilling.
3. Senere planlægning (foldet sammen ved oprettelse): lønnr., datoer og
   oplæringsdag – oplysninger, der først er kendt senere i forløbet.

Stillingen skal vælges aktivt, datoer er "Ikke fastlagt", til de er aftalt, og
er der kun én arbejdsgangsskabelon til stillingen, vælges den automatisk.

Dialogen indsamler kun data. Reglerne (fasebaseret validering, betingede
opgaver, kritisk overstyring, annullering) håndhæves af OnboardingService.
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import arbejdsspor as sp
from app.domain import behov as bh
from app.domain.onboarding import OnboardingForloeb as OB
from app.services.onboarding_service import (
    BOOKING,
    OPLAERING_BOOKET,
    booking_tekst,
    opgave_med_noegle,
    toej_fastlagt,
)
from app.ui.hjaelpere import laes_dato, lav_knap

# Datofelter viser denne tekst, indtil en dato er aftalt (minimumsdatoen = ingen dato).
_INGEN_DATO = QDate(2000, 1, 1)


def _raekke(*widgets, stretch_sidste=False) -> QWidget:
    boks = QWidget()
    lag = QHBoxLayout(boks)
    lag.setContentsMargins(0, 0, 0, 0)
    lag.setSpacing(8)
    for i, w in enumerate(widgets):
        lag.addWidget(w, 1 if stretch_sidste and i == len(widgets) - 1 else 0)
    if not stretch_sidste:
        lag.addStretch()
    return boks


class OnboardingDialog(QDialog):
    def __init__(self, parent, forloeb=None, skabeloner=(), omraader=(), ansvarlige=(),
                 profiler=None):
        """skabeloner: aktive onboarding-skabeloner (filtreres efter stilling).
        profiler: {stilling: Behov} – standardprofilerne for udstyr."""
        super().__init__(parent)
        self.ny = forloeb is None
        self.forloeb = forloeb
        self.alle_skabeloner = list(skabeloner)
        self.skabeloner = []
        self.profiler = dict(profiler or {})
        self._indlaeser = False          # profilen sættes – ikke HR's egne ændringer
        self._udstyr_roert = False
        self.setWindowTitle("Opret kandidat" if self.ny else "Rediger onboardingforløb")
        self.setMinimumWidth(640)
        self.resize(680, 720)

        indhold = QWidget()
        self.layout_indhold = QVBoxLayout(indhold)
        self.layout_indhold.setContentsMargins(24, 22, 24, 12)
        self.layout_indhold.setSpacing(10)
        self._opbyg_kandidat(omraader, ansvarlige)
        self._opbyg_udstyr()
        self._opbyg_planlaegning()
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
        gem.setText("Opret kandidat" if self.ny else "Gem")
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
        self.stilling_input.currentIndexChanged.connect(lambda _i: self._stilling_valgt())
        self._stilling_valgt(indlaes=self.ny)
        self.navn_input.setFocus()

    def stilling(self) -> str:
        return self.stilling_input.currentData() or ""

    ### ----- sektioner -------------------------------------------------------

    def _sektion(self, titel, hjaelp="", lag=None):
        lag = lag or self.layout_indhold
        label = QLabel(titel)
        label.setObjectName("sektionTitel")
        lag.addWidget(label)
        tekst = None
        if hjaelp:
            tekst = QLabel(hjaelp)
            tekst.setObjectName("hjaelpTekst")
            tekst.setWordWrap(True)
            lag.addWidget(tekst)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        lag.addLayout(form)
        return form, tekst

    def _opbyg_kandidat(self, omraader, ansvarlige):
        form, _ = self._sektion("Kandidat")
        self.navn_input = QLineEdit()
        self.stilling_input = QComboBox()
        if self.ny:
            # Ingen forvalgt stilling: profil og arbejdsgang følger valget.
            self.stilling_input.addItem("Vælg stilling…", "")
        for stilling in OB.STILLINGER:
            self.stilling_input.addItem(stilling, stilling)
        self.omraade_input = QComboBox()
        self.omraade_input.setEditable(True)
        self.omraade_input.addItems(list(omraader))
        self.ansvarlig_input = QComboBox()
        self.ansvarlig_input.setEditable(True)
        self.ansvarlig_input.addItems(list(ansvarlige))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Kandidatens egen e-mail (kontakt)")
        self.kommentar_input = QLineEdit()

        # HR tildeler lønnr., når medarbejderen oprettes i ERP – derfor her.
        self.loennr_input = QLineEdit()
        self.loennr_input.setPlaceholderText("Fra ERP – skal være tildelt, før kontrakten sendes")
        form.addRow("Navn", self.navn_input)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Stillingskategori", self.stilling_input)
        form.addRow("Ønsket område", self.omraade_input)
        if not self.ny:
            # Ingen koordinatorrolle: HR opretter, og ejerskabet ligger pr. opgave
            # hos afdelingerne. Feltet vises kun for forløb, der allerede har en.
            form.addRow("Proceskoordinator", self.ansvarlig_input)
        form.addRow("Kontakt-e-mail", self.email_input)
        if self.ny:
            self.skabelon_input = QComboBox()
            self.skabelon_label = QLabel("")
            self.skabelon_label.setObjectName("hjaelpTekst")
            self.skabelon_label.setWordWrap(True)
            form.addRow("Arbejdsgang", _raekke(self.skabelon_input, self.skabelon_label,
                                               stretch_sidste=True))
        form.addRow("Kommentar", self.kommentar_input)

    def _opbyg_udstyr(self):
        form, self.profil_label = self._sektion(
            "Udstyr", "Vælg stilling for at indlæse standardprofilen.")
        self.udstyr_form = form
        self.toej = {}
        for noegle, navn in bh.BEKLAEDNING.items():
            valgt = QCheckBox(navn)
            stoerrelse = QComboBox()
            stoerrelse.addItem("Størrelse senere", "")
            for s in bh.STOERRELSER:
                stoerrelse.addItem(s, s)
            antal = QSpinBox()
            antal.setRange(1, bh.MAKS_ANTAL)
            antal.setSuffix(" stk.")
            for felt in (stoerrelse, antal):
                felt.setEnabled(False)
                valgt.toggled.connect(felt.setEnabled)
            valgt.toggled.connect(self._udstyr_aendret)
            antal.valueChanged.connect(self._udstyr_aendret)
            form.addRow("Arbejdstøj" if not self.toej else "", _raekke(valgt, stoerrelse, antal))
            self.toej[noegle] = (valgt, stoerrelse, antal)
        self.toej_bemaerkning = QLineEdit()
        self.toej_bemaerkning.setPlaceholderText(f"Fx mere end {bh.MAKS_ANTAL} stk. eller "
                                                 "særlige ønsker")
        form.addRow("Tøj, bemærkning", self.toej_bemaerkning)

        self.mobil_input = QCheckBox("Mobiltelefon")
        self.abonnement_input = QComboBox()
        self.mobil_input.toggled.connect(self._opdater_valg)
        self.mobil_input.toggled.connect(self._udstyr_aendret)
        self.abonnement_input.currentIndexChanged.connect(self._udstyr_aendret)
        form.addRow("Telefon", _raekke(self.mobil_input, self.abonnement_input))
        self.mail_input = QCheckBox("E-mailkonto")
        self.mail_input.toggled.connect(self._udstyr_aendret)
        form.addRow("E-mail", self.mail_input)
        self.bil_input = QCheckBox("Firmabil")
        self.bil_bemaerkning = QLineEdit()
        self.bil_bemaerkning.setPlaceholderText("Fx ønsket dato eller særlige behov")
        self.bil_input.toggled.connect(self._opdater_valg)
        self.bil_input.toggled.connect(self._udstyr_aendret)
        form.addRow("Firmabil", _raekke(self.bil_input, self.bil_bemaerkning,
                                        stretch_sidste=True))
        self._opgavestatus(form)

        self.profil_knap = lav_knap("Indlæs standardprofil")
        self.profil_knap.setToolTip("Erstat udstyrsvalgene med stillingens standardprofil")
        self.profil_knap.clicked.connect(lambda: self._indlaes_profil(tving=True))

        # Behovet er registreret, når HR gemmer – der er intet at krydse af bagefter.
        form.addRow("", _raekke(self.profil_knap))

    def _opgavestatus(self, form):
        """Status på de opgaver, behovet har skabt (kun ved redigering) – behovet er
        ikke det samme som udførelsen."""
        if self.ny:
            return
        linjer = []
        # Det samlede "Udstyr sendt" + firmabil (ældre forløb: tøj, telefon, e-mail hver for sig).
        for noegle in ("udstyr", *bh.BEKLAEDNING, "telefon", "email", "firmabil"):
            opgave = opgave_med_noegle(self.forloeb, noegle)
            if opgave is None or opgave.status == "Undtaget":
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

    def _opbyg_planlaegning(self):
        self.planlaegning_knap = QToolButton()
        self.planlaegning_knap.setCheckable(True)
        self.planlaegning_knap.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.planlaegning_knap.setArrowType(Qt.ArrowType.RightArrow)
        self.planlaegning_knap.setText("Senere planlægning – datoer og oplæring")
        self.planlaegning_knap.setObjectName("sektionKnap")
        self.planlaegning_knap.setStyleSheet("QToolButton { border: none; font-weight: 700; "
                                             "font-size: 14px; padding: 8px 0; }")
        self.planlaegning_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.planlaegning_knap.toggled.connect(self._vis_planlaegning)
        self.layout_indhold.addWidget(self.planlaegning_knap)

        self.planlaegning = QWidget()
        lag = QVBoxLayout(self.planlaegning)
        lag.setContentsMargins(0, 0, 0, 0)
        tekst = QLabel("Udfyldes, når det er aftalt. Frister beregnes ud fra "
                       "ansættelsesdatoen, når den er fastlagt; den skal kendes, før "
                       "kontrakten sendes.")
        tekst.setObjectName("hjaelpTekst")
        tekst.setWordWrap(True)
        lag.addWidget(tekst)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        lag.addLayout(form)
        self.ansaettelse_valgt, self.ansaettelse_input = self._valgfri_dato("Aftalt")
        self.foerste_valgt, self.foerste_input = self._valgfri_dato(
            "En anden dag end ansættelsen")
        self.foerste_valgt.toggled.connect(self._foerste_valgt)
        form.addRow("Ansættelsesdato", _raekke(self.ansaettelse_valgt, self.ansaettelse_input))
        form.addRow("Første arbejdsdag", _raekke(self.foerste_valgt, self.foerste_input))

        self.tid_valgt = QCheckBox("Aftalt")
        self.tid_input = QDateTimeEdit()
        self.tid_input.setCalendarPopup(True)
        self.tid_input.setDisplayFormat("dd-MM-yyyy HH:mm")
        self.tid_input.setMinimumDateTime(QDateTime(_INGEN_DATO, QTime(0, 0)))
        self.tid_input.setSpecialValueText("Ikke aftalt")
        self.tid_input.setDateTime(self.tid_input.minimumDateTime())
        self.tid_input.setEnabled(False)
        self.tid_valgt.toggled.connect(self._tid_valgt)
        self.booking_input = QComboBox()
        self.booking_input.addItems(list(BOOKING))
        self.booking_input.setToolTip("Et tidspunkt er ikke en booking – bookingstatus "
                                      "vælges særskilt.")
        form.addRow("Oplæringsdag", _raekke(self.tid_valgt, self.tid_input))
        form.addRow("Bookingstatus", self.booking_input)
        if not self.ny:
            for noegle in (OPLAERING_BOOKET,):
                opgave = opgave_med_noegle(self.forloeb, noegle)
                if opgave is not None:
                    status = sp.visningsstatus(self.forloeb, opgave, date.today())
                    form.addRow("", QLabel(f"{opgave.navn}: {status}"))
        self.layout_indhold.addWidget(self.planlaegning)
        # Ved redigering er planlægningen typisk aktuel – ved oprettelse sjældent.
        self.planlaegning_knap.setChecked(not self.ny)
        self._vis_planlaegning(not self.ny)

    def _vis_planlaegning(self, aaben):
        self.planlaegning.setVisible(aaben)
        self.planlaegning_knap.setArrowType(Qt.ArrowType.DownArrow if aaben
                                            else Qt.ArrowType.RightArrow)

    @staticmethod
    def _valgfri_dato(tekst):
        """(afkrydsning, datofelt): "Ikke fastlagt", indtil afkrydsningen sættes."""
        valgt = QCheckBox(tekst)
        felt = QDateEdit()
        felt.setCalendarPopup(True)
        felt.setDisplayFormat("dd-MM-yyyy")
        felt.setMinimumDate(_INGEN_DATO)
        felt.setSpecialValueText("Ikke fastlagt")
        felt.setDate(_INGEN_DATO)
        felt.setEnabled(False)

        def skift(til):
            felt.setEnabled(til)
            if not til:
                felt.setDate(_INGEN_DATO)
            elif felt.date() == _INGEN_DATO:
                felt.setDate(QDate.currentDate())
        valgt.toggled.connect(skift)
        return valgt, felt

    def _foerste_valgt(self, til):
        if til and self.ansaettelse_valgt.isChecked():
            self.foerste_input.setDate(self.ansaettelse_input.date())

    def _tid_valgt(self, til):
        self.tid_input.setEnabled(til)
        if not til:
            self.tid_input.setDateTime(self.tid_input.minimumDateTime())
        elif self.tid_input.date() == _INGEN_DATO:
            self.tid_input.setDateTime(QDateTime(QDate.currentDate(), QTime(8, 0)))

    ### ----- stilling, profil og arbejdsgang ---------------------------------

    def _stilling_valgt(self, indlaes=True):
        stilling = self.stilling()
        if self.ny:
            self._fyld_skabeloner()
        # Udstyret kan først vælges, når stillingen (og dermed begrænsningerne) kendes.
        valgt = bool(stilling)
        for raekke in range(self.udstyr_form.rowCount()):
            for rolle in (QFormLayout.ItemRole.FieldRole, QFormLayout.ItemRole.SpanningRole):
                item = self.udstyr_form.itemAt(raekke, rolle)
                if item and item.widget():
                    item.widget().setEnabled(valgt)
        if indlaes and valgt:
            self._indlaes_profil()
        elif not valgt:
            self.profil_label.setText("Vælg stilling for at indlæse standardprofilen.")
        self._opdater_valg()

    def _indlaes_profil(self, tving=False):
        """Stillingens standardprofil – men aldrig over HR's egne ændringer, medmindre
        HR selv beder om det. Størrelser, som allerede er valgt, bevares."""
        stilling = self.stilling()
        profil = self.profiler.get(stilling)
        if self._udstyr_roert and not tving:
            self.profil_label.setText(f"Udstyret er tilpasset – standardprofilen for {stilling} "
                                      "er ikke indlæst. Tryk 'Indlæs standardprofil' for at "
                                      "bruge den.")
            return
        self._indlaeser = True
        try:
            p = profil or bh.Behov()
            for noegle, (valgt, _stoerrelse, antal) in self.toej.items():
                t = p.toej(noegle)
                valgt.setChecked(t.valgt)
                antal.setValue(t.antal or 1)
            self.mobil_input.setChecked(p.mobil)
            self._opdater_valg()
            index = self.abonnement_input.findData(p.abonnement)
            if index >= 0:
                self.abonnement_input.setCurrentIndex(index)
            self.mail_input.setChecked(p.email)
            self.bil_input.setChecked(p.firmabil)
        finally:
            self._indlaeser = False
        self._udstyr_roert = False
        self.profil_label.setText(
            f"Standardprofilen for {stilling} er indlæst – tilpas efter behov og vælg "
            "størrelser, når de kendes. Valgt udstyr er et behov, ikke en bestilling."
            if profil and profil != bh.Behov() else
            f"Der er ingen standardprofil for {stilling} (Indstillinger → Organisation). "
            "Vælg udstyret her.")

    def _udstyr_aendret(self, *_):
        if not self._indlaeser:
            self._udstyr_roert = True

    def _fyld_skabeloner(self):
        """Én relevant skabelon vælges automatisk; flere giver et valg."""
        stilling = self.stilling()
        self.skabeloner = [s for s in self.alle_skabeloner if stilling and
                           (not s.get("stillinger") or stilling in s["stillinger"])]
        self.skabelon_input.clear()
        for s in self.skabeloner:
            self.skabelon_input.addItem(f"{s['navn']} (v{s.get('version', 1)})")
        self.skabelon_input.addItem("Ingen skabelon")
        flere = len(self.skabeloner) > 1
        self.skabelon_input.setVisible(flere)
        self.skabelon_label.setVisible(not flere)
        if not stilling:
            self.skabelon_label.setText("Vælges ud fra stillingen.")
        elif len(self.skabeloner) == 1:
            s = self.skabeloner[0]
            self.skabelon_label.setText(f"{s['navn']} (v{s.get('version', 1)})")
        elif not self.skabeloner:
            self.skabelon_label.setText("Ingen arbejdsgangsskabelon til stillingen – "
                                        "forløbet oprettes uden opgaver.")

    ### ----- betinget visning ------------------------------------------------

    def _opdater_valg(self):
        """Skjuler og låser udstyr, stillingen ikke kan få, og felter, der ikke er relevante."""
        stilling = self.stilling()
        udvidet = bh.tilladt_udvidet(stilling)
        for felt in (self.mail_input, self.bil_input):
            if not udvidet:
                felt.setChecked(False)
            felt.setEnabled(udvidet)
        for felt in (self.mail_input, self.bil_input):
            # Vis kun e-mail og firmabil for stillinger, der kan få dem.
            self.udstyr_form.setRowVisible(felt.parentWidget() if felt is self.bil_input
                                           else felt, udvidet or not stilling)
        tilladte = bh.tilladte_abonnementer(stilling)
        valgt = self.abonnement_input.currentData()
        self.abonnement_input.blockSignals(True)
        self.abonnement_input.clear()
        self.abonnement_input.addItem("Vælg abonnement", "")
        for a in tilladte:
            self.abonnement_input.addItem(a, a)
        # Et tidligere valg bevares, hvis det stadig er tilladt; ét tilladt = forvalgt.
        index = self.abonnement_input.findData(valgt) if valgt else -1
        self.abonnement_input.setCurrentIndex(index if index >= 0 else
                                              (1 if len(tilladte) == 1 else 0))
        self.abonnement_input.blockSignals(False)
        self.abonnement_input.setEnabled(bool(stilling) and self.mobil_input.isChecked())
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
        index = self.stilling_input.findData(f.stilling)
        if index >= 0:
            self.stilling_input.setCurrentIndex(index)
        self.omraade_input.setCurrentText(f.omraade)
        self.ansvarlig_input.setCurrentText(f.ansvarlig)
        self.email_input.setText(f.email)
        self.kommentar_input.setText(f.kommentar)
        for valgt, felt, vaerdi in ((self.ansaettelse_valgt, self.ansaettelse_input,
                                     f.ansaettelsesdato),
                                    (self.foerste_valgt, self.foerste_input,
                                     f.foerste_arbejdsdag)):
            dato = laes_dato(vaerdi)
            if dato.isValid():
                valgt.setChecked(True)
                felt.setDate(dato)

        self._indlaeser = True
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
        self._indlaeser = False
        self._udstyr_roert = True       # det registrerede behov overskrives aldrig af sig selv
        self.profil_label.setText("Det registrerede behov. Ændringer gør betingede opgaver "
                                  "relevante eller ej – påbegyndte opgaver ændres aldrig.")

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

    def _kraev_stoerrelse(self) -> bool:
        """Samme fase-regel som OnboardingService: størrelser, når udstyret er på vej."""
        return not self.ny and toej_fastlagt(self.forloeb)

    def accept(self):
        fejl = []
        if not self.navn_input.text().strip():
            fejl.append("Navn skal udfyldes.")
        if not self.stilling():
            fejl.append("Vælg en stillingskategori.")
        else:
            fejl += self.hent_behov().valider(self.stilling(), self._kraev_stoerrelse())
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
            "stilling": self.stilling(),
            "omraade": self.omraade_input.currentText().strip(),
            "ansvarlig": "" if self.ny else self.ansvarlig_input.currentText().strip(),
            "email": self.email_input.text().strip(),
            "ansaettelsesdato": self.ansaettelse_input.date().toString("yyyy-MM-dd")
            if self.ansaettelse_valgt.isChecked() else "",
            "foerste_arbejdsdag": self.foerste_input.date().toString("yyyy-MM-dd")
            if self.foerste_valgt.isChecked() else "",
            "kommentar": self.kommentar_input.text().strip(),
            "behov": self.hent_behov().til_dict(),
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
