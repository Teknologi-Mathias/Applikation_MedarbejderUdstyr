"""Dialoger til Ønsker & Udvikling: ny indmelding og detaljevisning.

Dialogerne viser og indsamler data; regler og rettigheder ligger i
IndmeldingService (og i databasen). Hvad brugeren må redigere, spørges
servicen om (kan_redigere_tekst / er_administrator) – ikke afgjort her.
"""
import html

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
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.domain import indmelding as im
from app.repositories.fejl import ValideringsFejl
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, lav_pille, vis_dato
from app.ui.theme import prioritet_stil, status_stil

# Tekstfelterne i formularen: (domænefelt, etiket, pladsholder, linjer – 0 = én linje).
# Bevidst kort: detaljerne afklares bagefter med indsenderen. Domænets øvrige
# tekstfelter (problem, effekt …) findes stadig, men udfyldes ikke herfra.
TEKST_FORMULAR = (
    ("titel", "Titel *", "Kort og præcis, fx \"Eksport af sager til Excel fejler\"", 0),
    ("beskrivelse", "Beskrivelse *", "Hvad drejer det sig om? Et par linjer er nok.", 6),
)


def _tekstfelt(linjer: int, pladsholder: str):
    if linjer == 0:
        felt = QLineEdit()
        felt.setMaxLength(im.MAKS_TITEL)
    else:
        felt = QPlainTextEdit()
        felt.setTabChangesFocus(True)
        felt.setFixedHeight(28 + 20 * linjer)
    felt.setPlaceholderText(pladsholder)
    return felt


def _tekst(felt) -> str:
    return felt.text() if isinstance(felt, QLineEdit) else felt.toPlainText()


def _saet_tekst(felt, tekst: str) -> None:
    if isinstance(felt, QLineEdit):
        felt.setText(tekst)
    else:
        felt.setPlainText(tekst)


def _tid(tekst: str) -> str:
    """"2026-10-25T14:03:00" -> "25-10-2026 14:03"."""
    return f"{vis_dato(tekst[:10])} {tekst[11:16]}".strip() if tekst else ""


def _kald(dialog, funktion, *args, efter_konflikt=None):
    """Kører en servicefunktion: regelbrud vises i dialogens fejlfelt, alt andet
    håndteres ens via udfoer (konflikt, forbindelse, udløbet session)."""
    def kald():
        try:
            return funktion(*args)
        except ValideringsFejl as fejl:
            dialog.fejl_label.setText(str(fejl))
            return FEJL
    dialog.fejl_label.setText("")
    return udfoer(dialog, kald, efter_konflikt=efter_konflikt)


class NyIndmeldingDialog(QDialog):
    """Efter exec(): self.indmelding er den oprettede indmelding."""

    def __init__(self, parent, service):
        super().__init__(parent)
        self.service = service
        self.indmelding = None
        self.setWindowTitle("Ny indmelding – Ønsker & Udvikling")
        self.setMinimumWidth(620)

        intro = QLabel("Beskriv kort fejlen, ønsket eller forbedringen. "
                       "Detaljerne tager vi med dig bagefter.")
        intro.setObjectName("hjaelpTekst")
        intro.setWordWrap(True)

        self.felter = {}
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.kategori_input = QComboBox()
        self.kategori_input.addItems(im.KATEGORIER)
        for noegle, etiket, pladsholder, linjer in TEKST_FORMULAR:
            self.felter[noegle] = _tekstfelt(linjer, pladsholder)
            form.addRow(etiket, self.felter[noegle])
            if noegle == "titel":
                form.addRow("Kategori *", self.kategori_input)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Send indmelding")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.fejl_label)
        layout.addWidget(knapper)
        self.felter["titel"].setFocus()

    def data(self) -> dict:
        return {"kategori": self.kategori_input.currentText(),
                **{noegle: _tekst(felt) for noegle, felt in self.felter.items()}}

    def accept(self):
        resultat = _kald(self, self.service.opret, self.data())
        if resultat is FEJL:
            return
        self.indmelding = resultat
        super().accept()


class IndmeldingDialog(QDialog):
    """Detaljer, behandling, kommentarer og historik for én indmelding.

    self.aendret er True, hvis noget er gemt (så listen kan opdateres).
    """

    FANE_DETALJER, FANE_BEHANDLING, FANE_KOMMENTARER, FANE_HISTORIK = range(4)

    def __init__(self, parent, service, detaljer, brugernavne=()):
        super().__init__(parent)
        self.service = service
        self.brugernavne = list(brugernavne)
        self.aendret = False
        self.setMinimumSize(760, 640)

        self.titel_label = QLabel("")
        self.titel_label.setObjectName("pageTitle")
        self.titel_label.setWordWrap(True)
        self.under_label = QLabel("")
        self.under_label.setObjectName("pageSub")
        self.under_label.setWordWrap(True)
        self.piller = QHBoxLayout()
        self.piller.setSpacing(8)

        self.faner = QTabWidget()
        self.faner.addTab(self._opbyg_detaljer(), "Detaljer")
        self.faner.addTab(self._opbyg_behandling(), "Behandling")
        self.faner.addTab(self._opbyg_kommentarer(), "Kommentarer")
        self.faner.addTab(self._opbyg_historik(), "Historik")

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        self.gem_knap = lav_knap("Gem ændringer", "primary")
        self.gem_knap.clicked.connect(self._gem)
        luk = lav_knap("Luk")
        luk.clicked.connect(self.accept)
        bund = QHBoxLayout()
        bund.addWidget(self.fejl_label, 1)
        bund.addWidget(self.gem_knap)
        bund.addWidget(luk)

        hoved = QHBoxLayout()
        tekst = QVBoxLayout()
        tekst.setSpacing(2)
        tekst.addWidget(self.titel_label)
        tekst.addWidget(self.under_label)
        hoved.addLayout(tekst, 1)
        hoved.addLayout(self.piller)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addLayout(hoved)
        layout.addWidget(self.faner, 1)
        layout.addLayout(bund)

        self._vis(detaljer)

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_detaljer(self) -> QWidget:
        side = QWidget()
        form = QFormLayout(side)
        form.setContentsMargins(12, 14, 12, 8)
        form.setVerticalSpacing(10)
        self.felter = {}
        self.kategori_input = QComboBox()
        self.kategori_input.addItems(im.KATEGORIER)
        for noegle, etiket, pladsholder, linjer in TEKST_FORMULAR:
            self.felter[noegle] = _tekstfelt(linjer, "")
            form.addRow(etiket.rstrip(" *"), self.felter[noegle])
            if noegle == "titel":
                form.addRow("Kategori", self.kategori_input)
        self.tekst_hjaelp = QLabel("")
        self.tekst_hjaelp.setObjectName("hjaelpTekst")
        self.tekst_hjaelp.setWordWrap(True)
        form.addRow("", self.tekst_hjaelp)
        return side

    def _opbyg_behandling(self) -> QWidget:
        side = QWidget()
        form = QFormLayout(side)
        form.setContentsMargins(12, 14, 12, 8)
        form.setVerticalSpacing(10)
        self.status_input = QComboBox()
        self.prioritet_input = QComboBox()
        self.prioritet_input.addItems(im.PRIORITETER)
        self.ansvarlig_input = QComboBox()
        self.version_input = QLineEdit()
        self.version_input.setMaxLength(im.MAKS_VERSION)
        self.version_input.setPlaceholderText("fx V0.8")
        self.loesning_input = QPlainTextEdit()
        self.loesning_input.setPlaceholderText(
            "Hvordan er indmeldingen løst – eller hvorfor er den afvist?")
        self.loesning_input.setFixedHeight(120)
        form.addRow("Status", self.status_input)
        form.addRow("Prioritet", self.prioritet_input)
        form.addRow("Ansvarlig", self.ansvarlig_input)
        form.addRow("Planlagt version", self.version_input)
        form.addRow("Løsning / begrundelse", self.loesning_input)
        self.behandling_hjaelp = QLabel("")
        self.behandling_hjaelp.setObjectName("hjaelpTekst")
        self.behandling_hjaelp.setWordWrap(True)
        form.addRow("", self.behandling_hjaelp)
        return side

    def _opbyg_kommentarer(self) -> QWidget:
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 12, 12, 8)
        self.kommentar_visning = QTextBrowser()
        self.kommentar_visning.setOpenExternalLinks(False)
        self.kommentar_input = QPlainTextEdit()
        self.kommentar_input.setPlaceholderText("Skriv en kommentar …")
        self.kommentar_input.setFixedHeight(80)
        self.intern_input = QCheckBox("Intern note (kun synlig for administratorer)")
        tilfoej = QPushButton("Tilføj kommentar")
        tilfoej.setCursor(Qt.CursorShape.PointingHandCursor)
        tilfoej.clicked.connect(self._tilfoej_kommentar)
        raekke = QHBoxLayout()
        raekke.addWidget(self.intern_input)
        raekke.addStretch()
        raekke.addWidget(tilfoej)
        layout.addWidget(self.kommentar_visning, 1)
        layout.addWidget(self.kommentar_input)
        layout.addLayout(raekke)
        return side

    def _opbyg_historik(self) -> QWidget:
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 12, 12, 8)
        self.historik_tabel = QTableWidget(0, 3)
        self.historik_tabel.setHorizontalHeaderLabels(["Tidspunkt", "Bruger", "Ændring"])
        self.historik_tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.historik_tabel.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.historik_tabel.verticalHeader().setVisible(False)
        self.historik_tabel.horizontalHeader().setStretchLastSection(True)
        self.historik_tabel.setColumnWidth(0, 140)
        self.historik_tabel.setColumnWidth(1, 110)
        self.historik_tabel.setShowGrid(False)
        self.historik_tabel.setAlternatingRowColors(True)
        layout.addWidget(self.historik_tabel)
        return side

    ### ----- visning --------------------------------------------------------

    def _vis(self, detaljer) -> None:
        self.detaljer = detaljer
        ind = detaljer.indmelding
        admin = self.service.er_administrator()
        kan_tekst = self.service.kan_redigere_tekst(ind)

        self.setWindowTitle(f"{ind.visningsnummer} {ind.titel} – Ønsker & Udvikling")
        self.titel_label.setText(f"{ind.visningsnummer}  {ind.titel}")
        self.under_label.setText(
            f"{ind.kategori} · indsendt af {ind.indsender} {_tid(ind.oprettet)} · "
            f"senest ændret {_tid(ind.opdateret)}"
            + (f" · ansvarlig {ind.ansvarlig}" if ind.ansvarlig else ""))
        while self.piller.count():
            gammel = self.piller.takeAt(0).widget()
            if gammel:
                gammel.deleteLater()
        self.piller.addWidget(lav_pille(ind.status, status_stil(ind.status)))
        self.piller.addWidget(lav_pille(ind.prioritet, prioritet_stil(ind.prioritet)))

        # Detaljer
        for noegle, felt in self.felter.items():
            _saet_tekst(felt, getattr(ind, noegle))
            felt.setReadOnly(not kan_tekst)
        self.kategori_input.setCurrentText(ind.kategori)
        self.kategori_input.setEnabled(kan_tekst)
        self.tekst_hjaelp.setText(
            "" if kan_tekst else
            "Teksten kan kun rettes af indsenderen, mens indmeldingen har status Indsendt, "
            "og af administratorer. Skriv en kommentar for at tilføje oplysninger.")

        # Behandling
        self.status_input.clear()
        self.status_input.addItems(im.tilladte_statusser(ind.status))
        self.status_input.setCurrentText(ind.status)
        self.prioritet_input.setCurrentText(ind.prioritet)
        self.ansvarlig_input.clear()
        self.ansvarlig_input.addItem("")
        self.ansvarlig_input.addItems(
            self.brugernavne + ([ind.ansvarlig] if ind.ansvarlig
                                and ind.ansvarlig not in self.brugernavne else []))
        self.ansvarlig_input.setCurrentText(ind.ansvarlig)
        self.version_input.setText(ind.planlagt_version)
        self.loesning_input.setPlainText(ind.loesning)
        for felt in (self.status_input, self.prioritet_input, self.ansvarlig_input):
            felt.setEnabled(admin)
        for felt in (self.version_input, self.loesning_input):
            felt.setReadOnly(not admin)
        self.behandling_hjaelp.setText(
            "Status kan kun skifte til de viste trin. Afvisning kræver en begrundelse."
            if admin else "Behandlingen varetages af en administrator.")
        self.gem_knap.setVisible(admin or kan_tekst)

        # Kommentarer
        self.intern_input.setVisible(admin)
        self.intern_input.setChecked(False)
        self.faner.setTabText(self.FANE_KOMMENTARER, f"Kommentarer ({len(detaljer.kommentarer)})")
        if not detaljer.kommentarer:
            self.kommentar_visning.setHtml("<p><i>Ingen kommentarer endnu.</i></p>")
        else:
            dele = []
            for k in detaljer.kommentarer:
                maerke = " · <b>Intern note</b>" if k.intern else ""
                tekst = html.escape(k.tekst).replace("\n", "<br>")
                dele.append(f"<p><b>{html.escape(k.forfatter)}</b> · {_tid(k.oprettet)}{maerke}"
                            f"<br>{tekst}</p>")
            self.kommentar_visning.setHtml("<hr>".join(dele))

        # Historik (nyeste øverst)
        historik = list(reversed(detaljer.historik))
        self.historik_tabel.setRowCount(len(historik))
        for raekke, a in enumerate(historik):
            for kolonne, tekst in enumerate((_tid(a.tidspunkt), a.bruger, a.tekst)):
                self.historik_tabel.setItem(raekke, kolonne, QTableWidgetItem(tekst))

    def _genindlaes(self) -> None:
        detaljer = udfoer(self, self.service.detaljer, self.detaljer.indmelding.id)
        if detaljer is FEJL:
            return
        if detaljer is None:
            self.fejl_label.setText("Indmeldingen findes ikke længere (slettet af en anden).")
            self.gem_knap.setVisible(False)
            return
        self._vis(detaljer)

    ### ----- handlinger -----------------------------------------------------

    def aendringer(self) -> dict:
        """De værdier, brugeren må ændre (servicen sorterer de uændrede fra)."""
        ind = self.detaljer.indmelding
        aendringer = {}
        if self.service.kan_redigere_tekst(ind):
            aendringer.update({noegle: _tekst(felt) for noegle, felt in self.felter.items()})
            aendringer["kategori"] = self.kategori_input.currentText()
        if self.service.er_administrator():
            aendringer.update({
                "status": self.status_input.currentText(),
                "prioritet": self.prioritet_input.currentText(),
                "ansvarlig": self.ansvarlig_input.currentText(),
                "planlagt_version": self.version_input.text(),
                "loesning": self.loesning_input.toPlainText(),
            })
        return aendringer

    def _gem(self):
        ind = self.detaljer.indmelding
        resultat = _kald(self, self.service.opdater, ind, self.aendringer(),
                         efter_konflikt=self._genindlaes)
        if resultat is FEJL:
            return
        if resultat is not ind:
            self.aendret = True
            self.fejl_label.setText("Ændringerne er gemt.")
        self._genindlaes()

    def _tilfoej_kommentar(self):
        resultat = _kald(self, self.service.tilfoej_kommentar, self.detaljer.indmelding.id,
                         self.kommentar_input.toPlainText(), self.intern_input.isChecked())
        if resultat is FEJL:
            return
        self.kommentar_input.clear()
        self._genindlaes()
        self.faner.setCurrentIndex(self.FANE_KOMMENTARER)
