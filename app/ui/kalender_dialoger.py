"""Dialoger til Kalender: begivenhed, kalender og import af .ics.

Regler ligger i KalenderService – dialogerne viser og indsamler. Begivenheds-
dialogen gemmer gennem en funktion fra siden (gem/slet), så dialogen bliver
åben, hvis gemningen afvises (fx en valideringsfejl).
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import kalender as kl
from app.domain.kalender import Begivenhed, Kalender
from app.services.kalender_import import laes_filer
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap

DATO_FORMAT = "dd-MM-yyyy"
TID_FORMAT = "dd-MM-yyyy  HH:mm"
_UGEDAGE = ("Ma", "Ti", "On", "To", "Fr", "Lø", "Sø")
_ALDRIG, _ANTAL, _DATO = range(3)
_INGEN_PAAMINDELSE = -1         # Qt kan ikke slå None op som data i en combobox


def farve_ikon(hex_farve: str, stoerrelse: int = 12) -> QIcon:
    pixmap = QPixmap(stoerrelse, stoerrelse)
    pixmap.fill(Qt.GlobalColor.transparent)
    maler = QPainter(pixmap)
    maler.setRenderHint(QPainter.RenderHint.Antialiasing)
    maler.setPen(Qt.PenStyle.NoPen)
    maler.setBrush(QColor(hex_farve))
    maler.drawEllipse(0, 0, stoerrelse, stoerrelse)
    maler.end()
    return QIcon(pixmap)


def _qdt(tid: datetime) -> QDateTime:
    return QDateTime(QDate(tid.year, tid.month, tid.day), QTime(tid.hour, tid.minute))


def _dt(qdt: QDateTime) -> datetime:
    d, t = qdt.date(), qdt.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())


def spoerg_omfang(parent, handling: str) -> str | None:
    """En gentaget begivenhed: kun denne, denne og fremtidige eller hele serien (None = fortryd)."""
    boks = QMessageBox(parent)
    boks.setWindowTitle(f"{handling} gentaget begivenhed")
    boks.setIcon(QMessageBox.Icon.Question)
    boks.setText(f"{handling} kun denne forekomst, denne og de fremtidige, eller hele serien?")
    knapper = {
        boks.addButton("Kun denne", QMessageBox.ButtonRole.AcceptRole): kl.KUN_DENNE,
        boks.addButton("Denne og fremtidige", QMessageBox.ButtonRole.AcceptRole): kl.FREMTIDIGE,
        boks.addButton("Hele serien", QMessageBox.ButtonRole.AcceptRole): kl.HELE_SERIEN,
    }
    boks.addButton("Fortryd", QMessageBox.ButtonRole.RejectRole)
    boks.exec()
    return knapper.get(boks.clickedButton())


class BegivenhedDialog(QDialog):
    """Ny eller ret begivenhed.

    begivenhed: udgangspunktet (for en forekomst i en serie med forekomstens start/slut og
    seriens gentagelse). gem(resultat) og slet() returnerer True, når det lykkedes."""

    def __init__(self, parent, kalendre: list[Kalender], begivenhed: Begivenhed, gem, slet=None):
        super().__init__(parent)
        self.begivenhed = begivenhed
        self._gem, self._slet = gem, slet
        ny = not begivenhed.version
        self.setWindowTitle("Ny begivenhed" if ny else begivenhed.titel)
        self.setMinimumWidth(520)

        self.titel = QLineEdit(begivenhed.titel)
        self.titel.setMaxLength(kl.MAKS_TITEL)
        self.titel.setPlaceholderText("Tilføj titel")
        self.kalender = QComboBox()
        for k in kalendre:
            self.kalender.addItem(farve_ikon(k.farve), k.navn, k.id)
        self.kalender.setCurrentIndex(max(0, self.kalender.findData(begivenhed.kalender_id)))
        self.kalender.setEnabled(ny or not (begivenhed.gentages or begivenhed.gentagelse_af))

        self.heldag = QCheckBox("Hele dagen")
        self.start, self.slut = QDateTimeEdit(), QDateTimeEdit()
        for felt in (self.start, self.slut):
            felt.setCalendarPopup(True)
        self.start.setDateTime(_qdt(begivenhed.start))
        vist_slut = begivenhed.slut - timedelta(days=1) if begivenhed.heldag else begivenhed.slut
        self.slut.setDateTime(_qdt(max(vist_slut, begivenhed.start)))
        self.heldag.setChecked(begivenhed.heldag)
        self._varighed = self._dt_slut() - self._dt_start()
        self.start.dateTimeChanged.connect(self._start_flyttet)
        self.slut.dateTimeChanged.connect(self._slut_flyttet)
        self.heldag.toggled.connect(self._heldag_skiftet)
        tid = QHBoxLayout()
        tid.addWidget(self.start, 1)
        tid.addWidget(QLabel("til"))
        tid.addWidget(self.slut, 1)
        tid.addWidget(self.heldag)

        self._byg_gentagelse(begivenhed)

        self.paamindelse = QComboBox()
        for minutter, tekst in kl.PAAMINDELSER:
            self.paamindelse.addItem(tekst, _INGEN_PAAMINDELSE if minutter is None else minutter)
        valgt = _INGEN_PAAMINDELSE if begivenhed.paamindelse is None else begivenhed.paamindelse
        if self.paamindelse.findData(valgt) < 0:     # fx fra en import
            self.paamindelse.addItem(f"{valgt} minutter før", valgt)
        self.paamindelse.setCurrentIndex(self.paamindelse.findData(valgt))
        self.privat = QCheckBox("Privat – andre ser kun 'Optaget'")
        self.privat.setChecked(begivenhed.privat)
        self.sted = QLineEdit(begivenhed.sted)
        self.sted.setMaxLength(kl.MAKS_STED)
        self.sted.setPlaceholderText("Sted eller mødelink")
        self.beskrivelse = QPlainTextEdit(begivenhed.beskrivelse)
        self.beskrivelse.setFixedHeight(90)
        self.beskrivelse.setTabChangesFocus(True)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Titel *", self.titel)
        form.addRow("Tid", tid)
        form.addRow("Gentagelse", self.gentagelse_boks)
        form.addRow("Påmindelse", self.paamindelse)
        form.addRow("Kalender", self.kalender)
        form.addRow("Sted", self.sted)
        form.addRow("Beskrivelse", self.beskrivelse)
        form.addRow("", self.privat)

        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        knapper.button(QDialogButtonBox.StandardButton.Save).setText("Gem")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annullér")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        bund = QHBoxLayout()
        if slet is not None and not ny:
            slet_knap = lav_knap("Slet", "danger")
            slet_knap.clicked.connect(self._slet_klik)
            bund.addWidget(slet_knap)
        bund.addStretch()
        bund.addWidget(knapper)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(bund)
        self._heldag_skiftet(begivenhed.heldag)
        self.titel.setFocus()

    ### ----- gentagelse -----------------------------------------------------

    def _byg_gentagelse(self, begivenhed: Begivenhed) -> None:
        valg = kl.fra_rrule(begivenhed.gentagelse)
        self._raa = valg.raa
        self.frekvens = QComboBox()
        for noegle, tekst in kl.FREKVENSER:
            self.frekvens.addItem(tekst, noegle)
        if valg.raa:
            self.frekvens.addItem(kl.beskriv_gentagelse(valg.raa, begivenhed.start), "raa")
        self.frekvens.setCurrentIndex(self.frekvens.findData("raa" if valg.raa else valg.frekvens))
        self.frekvens.setEnabled(not begivenhed.gentagelse_af)  # en rettet forekomst gentages ikke

        self.interval = QSpinBox()
        self.interval.setRange(1, 99)
        self.interval.setValue(valg.interval)
        self.interval.setPrefix("hver ")
        self.ugedage = [QCheckBox(navn) for navn in _UGEDAGE]
        valgte = valg.ugedage or (begivenhed.start.weekday(),)
        for i, boks in enumerate(self.ugedage):
            boks.setChecked(i in valgte)
        self.slut_type = QComboBox()
        self.slut_type.addItems(["Slutter aldrig", "Slutter efter", "Slutter den"])
        self.antal = QSpinBox()
        self.antal.setRange(1, 999)
        self.antal.setSuffix(" gange")
        self.antal.setValue(valg.antal or 10)
        self.til = QDateEdit()
        self.til.setCalendarPopup(True)
        self.til.setDisplayFormat(DATO_FORMAT)
        til = valg.til or (begivenhed.start + timedelta(days=90)).date()
        self.til.setDate(QDate(til.year, til.month, til.day))
        self.slut_type.setCurrentIndex(_ANTAL if valg.antal else _DATO if valg.til else _ALDRIG)

        linje1 = QHBoxLayout()
        linje1.addWidget(self.frekvens, 1)
        linje1.addWidget(self.interval)
        self.ugedag_raekke = QWidget()
        dage = QHBoxLayout(self.ugedag_raekke)
        dage.setContentsMargins(0, 0, 0, 0)
        for boks in self.ugedage:
            dage.addWidget(boks)
        dage.addStretch()
        self.slut_raekke = QWidget()
        slut = QHBoxLayout(self.slut_raekke)
        slut.setContentsMargins(0, 0, 0, 0)
        slut.addWidget(self.slut_type)
        slut.addWidget(self.antal)
        slut.addWidget(self.til)
        slut.addStretch()
        self.gentagelse_boks = QVBoxLayout()
        self.gentagelse_boks.addLayout(linje1)
        self.gentagelse_boks.addWidget(self.ugedag_raekke)
        self.gentagelse_boks.addWidget(self.slut_raekke)
        self.frekvens.currentIndexChanged.connect(self._vis_gentagelse)
        self.slut_type.currentIndexChanged.connect(self._vis_gentagelse)
        self._vis_gentagelse()

    def _vis_gentagelse(self) -> None:
        frekvens = self.frekvens.currentData()
        almindelig = frekvens not in (kl.INGEN, kl.HVERDAGE, "raa")
        self.interval.setVisible(almindelig)
        enhed = {kl.DAGLIG: ". dag", kl.UGENTLIG: ". uge", kl.MAANEDLIG: ". måned",
                 kl.AARLIG: ". år"}.get(frekvens, "")
        self.interval.setSuffix(enhed)
        self.ugedag_raekke.setVisible(frekvens == kl.UGENTLIG)
        self.slut_raekke.setVisible(frekvens not in (kl.INGEN, "raa"))
        self.antal.setVisible(self.slut_type.currentIndex() == _ANTAL)
        self.til.setVisible(self.slut_type.currentIndex() == _DATO)

    def _rrule(self) -> str:
        frekvens = self.frekvens.currentData()
        if frekvens == "raa":
            return self._raa
        if frekvens == kl.INGEN:
            return ""
        return kl.Gentagelse(
            frekvens, self.interval.value(),
            tuple(i for i, boks in enumerate(self.ugedage) if boks.isChecked()),
            antal=self.antal.value() if self.slut_type.currentIndex() == _ANTAL else None,
            til=self.til.date().toPython() if self.slut_type.currentIndex() == _DATO else None,
        ).til_rrule()

    ### ----- tid ------------------------------------------------------------

    def _dt_start(self) -> datetime:
        return _dt(self.start.dateTime())

    def _dt_slut(self) -> datetime:
        return _dt(self.slut.dateTime())

    def _start_flyttet(self, _qdt_ny) -> None:
        """Slut flytter med, så varigheden bevares."""
        self.slut.blockSignals(True)
        self.slut.setDateTime(_qdt(self._dt_start() + self._varighed))
        self.slut.blockSignals(False)

    def _slut_flyttet(self, _qdt_ny) -> None:
        self._varighed = max(timedelta(), self._dt_slut() - self._dt_start())

    def _heldag_skiftet(self, heldag: bool) -> None:
        for felt in (self.start, self.slut):
            felt.setDisplayFormat(DATO_FORMAT if heldag else TID_FORMAT)

    ### ----- gem/slet -------------------------------------------------------

    def resultat(self) -> Begivenhed:
        heldag = self.heldag.isChecked()
        start, slut = self._dt_start(), self._dt_slut()
        if heldag:      # slutdatoen vises inklusiv, men gemmes eksklusiv (dagen efter kl. 00:00)
            start = kl.dagens_start(start.date())
            slut = kl.dagens_start(slut.date() + timedelta(days=1))
        return self.begivenhed.kopi(
            kalender_id=self.kalender.currentData() or "", titel=self.titel.text().strip(),
            start=start, slut=slut, heldag=heldag, sted=self.sted.text().strip(),
            beskrivelse=self.beskrivelse.toPlainText().rstrip(), privat=self.privat.isChecked(),
            paamindelse=None if self.paamindelse.currentData() == _INGEN_PAAMINDELSE
            else self.paamindelse.currentData(), gentagelse=self._rrule())

    def accept(self) -> None:
        if self._gem(self.resultat()):
            super().accept()

    def _slet_klik(self) -> None:
        if self._slet():
            super().accept()


class KalenderDialog(QDialog):
    """Ny kalender (kalender=None) eller ret navn og farve. Efter exec(): self.resultat."""

    def __init__(self, parent, service, kalender: Kalender | None = None, brugte_farver=()):
        super().__init__(parent)
        self.service = service
        self.kalender = kalender
        self.resultat = None
        self.setWindowTitle("Ny kalender" if kalender is None else f"Kalender – {kalender.navn}")
        self.setMinimumWidth(380)
        self.navn = QLineEdit(kalender.navn if kalender else "")
        self.navn.setMaxLength(kl.MAKS_KALENDERNAVN)
        self.navn.setPlaceholderText("Fx Ferie, Vagtplan eller Projekt X")
        self.farve = QComboBox()
        for farve in kl.FARVER:
            self.farve.addItem(farve_ikon(farve, 14), "", farve)
        standard = kalender.farve if kalender else next(
            (f for f in kl.FARVER if f not in set(brugte_farver)), kl.FARVER[0])
        self.farve.setCurrentIndex(max(0, self.farve.findData(standard)))
        form = QFormLayout()
        form.addRow("Navn *", self.navn)
        form.addRow("Farve", self.farve)
        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        knapper.button(QDialogButtonBox.StandardButton.Save).setText("Gem")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annullér")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(knapper)

    def accept(self) -> None:
        gammel = self.kalender or Kalender("")
        resultat = udfoer(self, self.service.gem_kalender,
                          Kalender(self.navn.text(), self.farve.currentData(), gammel.ejer,
                                   gammel.id, gammel.version))
        if resultat is not FEJL:
            self.resultat = resultat
            super().accept()


_GRAENSER = (("Alle begivenheder", None), ("Fra det seneste år", 365),
             ("Fra de seneste 2 år", 2 * 365), ("Fra de seneste 5 år", 5 * 365))


class ImportDialog(QDialog):
    """Importér .ics-filer (fx Google Takeout) til nye eller eksisterende kalendere."""

    def __init__(self, parent, service, kalendre: list[Kalender]):
        super().__init__(parent)
        self.service = service
        self.kalendre = kalendre
        self.kilder = []
        self.resultat = None
        self.setWindowTitle("Importér kalender (.ics)")
        self.setMinimumSize(640, 420)

        hjaelp = QLabel(
            "Fra Google Kalender: gå til Google Takeout, vælg kun Kalender, og hent .zip-filen. "
            "Vælg den her (eller én eller flere .ics-filer). Hver kalender i filen kan blive en "
            "ny kalender i IN-BASE eller lægges i en eksisterende. Begivenheder, der allerede er "
            "importeret, springes over.")
        hjaelp.setWordWrap(True)
        hjaelp.setObjectName("hjaelpTekst")
        vaelg = lav_knap("Vælg filer…")
        vaelg.clicked.connect(self._vaelg_filer)
        self.tabel = QTableWidget(0, 3)
        self.tabel.setHorizontalHeaderLabels(["Kalender i filen", "Begivenheder", "Importér til"])
        self.tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.graense = QComboBox()
        for tekst, dage in _GRAENSER:
            self.graense.addItem(tekst, dage)

        self.import_knap = QPushButton("Importér")
        self.import_knap.setProperty("variant", "primary")
        self.import_knap.setEnabled(False)
        self.import_knap.clicked.connect(self._importer)
        annuller = lav_knap("Luk")
        annuller.clicked.connect(self.reject)
        bund = QHBoxLayout()
        bund.addWidget(QLabel("Medtag:"))
        bund.addWidget(self.graense)
        bund.addStretch()
        bund.addWidget(annuller)
        bund.addWidget(self.import_knap)

        top = QHBoxLayout()
        top.addWidget(vaelg)
        top.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(hjaelp)
        layout.addLayout(top)
        layout.addWidget(self.tabel, 1)
        layout.addLayout(bund)

    def _vaelg_filer(self) -> None:
        stier, _ = QFileDialog.getOpenFileNames(self, "Vælg kalenderfiler", "",
                                                "Kalender (*.ics *.zip)")
        if not stier:
            return
        kilder = udfoer(self, laes_filer, stier)
        if kilder is FEJL:
            return
        self.kilder = kilder
        self.tabel.setRowCount(len(kilder))
        for raekke, kilde in enumerate(kilder):
            self.tabel.setItem(raekke, 0, QTableWidgetItem(kilde.navn))
            antal = QTableWidgetItem(str(len(kilde.begivenheder)))
            antal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(raekke, 1, antal)
            maal = QComboBox()
            maal.addItem(f"Ny kalender: {kilde.navn}", "")
            for k in self.kalendre:
                maal.addItem(farve_ikon(k.farve), k.navn, k.id)
            self.tabel.setCellWidget(raekke, 2, maal)
        self.import_knap.setEnabled(bool(kilder))

    def _importer(self) -> None:
        valg = [(kilde, self.tabel.cellWidget(i, 2).currentData())
                for i, kilde in enumerate(self.kilder)]
        dage = self.graense.currentData()
        graense = datetime.now() - timedelta(days=dage) if dage else None
        resultat = udfoer(self, self.service.importer, valg, graense)
        if resultat is FEJL:
            return
        self.resultat = resultat
        QMessageBox.information(
            self, "Import færdig",
            f"Importeret: {resultat.importeret} begivenheder"
            + (f" i {resultat.nye_kalendere} nye kalendere" if resultat.nye_kalendere else "")
            + f".\nFandtes allerede: {resultat.dubletter}.\n"
            f"Sprunget over (aflyste, for gamle eller ulæselige): {resultat.sprunget_over}.")
        super().accept()
