"""Indstillinger → Opdateringer (kun administratorer): udgiv nye versioner af IN-BASE.

Byg installeren med scripts\\build_windows.ps1, og træk
release\\IN-BASE-Setup-v<version>.exe hertil (eller vælg filen). Siden kontrollerer
pakken (OpdateringService.kontroller_pakke), uploader den i baggrunden og udgiver
den til pilotkanalen. Herfra frigives den til alle (evt. en andel), trækkes
tilbage eller gøres til mindste version. Reglerne ligger i servicen – siden viser
og spørger kun. Databasen tillader kun administratorer at udgive (RLS, migrering 019).
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import opdatering as op
from app.infrastructure import stier
from app.ui.baggrund import koer_i_baggrund
from app.ui.fejl import FEJL, udfoer, vis_fejl
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved, vis_dato

_KOLONNER = ("Version", "Kanal", "Andel", "Status", "Størrelse", "Udgivet", "Af", "Commit", "Noter")


def _mb(antal: int) -> str:
    return f"{antal / 1024 / 1024:.1f} MB".replace(".", ",")


def _installer(urls) -> str | None:
    """Den første lokale .exe blandt de trukne filer."""
    for url in urls:
        sti = url.toLocalFile()
        if sti.lower().endswith(".exe"):
            return sti
    return None


class Slipfelt(QFrame):
    """Feltet, man trækker installeren ind i (eller klikker "Vælg fil…")."""
    fil_valgt = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("slipfelt")
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tekst = QLabel("Træk IN-BASE-Setup-v<version>.exe hertil")
        tekst.setObjectName("cardTitle")
        tekst.setAlignment(Qt.AlignmentFlag.AlignCenter)
        under = QLabel("Installeren fra release-mappen (bygget med scripts\\build_windows.ps1)")
        under.setObjectName("hjaelpTekst")
        under.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vaelg = lav_knap("Vælg fil…")
        vaelg.clicked.connect(self._vaelg)
        layout.addWidget(tekst)
        layout.addWidget(under)
        layout.addWidget(vaelg, 0, Qt.AlignmentFlag.AlignCenter)

    def _marker(self, aktiv: bool) -> None:
        self.setProperty("aktiv", aktiv)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and _installer(event.mimeData().urls()):
            event.acceptProposedAction()
            self._marker(True)

    def dragLeaveEvent(self, event):
        self._marker(False)

    def dropEvent(self, event):
        self._marker(False)
        sti = _installer(event.mimeData().urls())
        if sti:
            event.acceptProposedAction()
            self.fil_valgt.emit(sti)

    def _vaelg(self):
        mappe = stier.PROGRAM_MAPPE / "release"
        sti, _ = QFileDialog.getOpenFileName(self, "Vælg installer",
                                             str(mappe if mappe.is_dir() else Path.home()),
                                             "IN-BASE-installer (IN-BASE-Setup-v*.exe)")
        if sti:
            self.fil_valgt.emit(sti)


def _kort(titel: str, forklaring: str):
    kort = lav_kort(skygge=False)
    layout = QVBoxLayout(kort)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)
    titel_label = QLabel(titel)
    titel_label.setObjectName("cardTitle")
    tekst = QLabel(forklaring)
    tekst.setObjectName("cardSub")
    tekst.setWordWrap(True)
    layout.addWidget(titel_label)
    layout.addWidget(tekst)
    return kort, layout


class OpdateringPanel(QWidget):
    def __init__(self, tjenester):
        super().__init__()
        self.service = tjenester.opdatering
        self._pakke = None
        self._udgivelser: list[op.Udgivelse] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        hoved, _ = lav_sidehoved("Opdateringer",
                                 "Udgiv en ny version til alle IN-BASE-klienter – de opdaterer sig selv.")
        layout.addLayout(hoved)
        if self.service is None:
            tekst = QLabel("Den centrale opdatering findes kun, når IN-BASE bruger Supabase.")
            tekst.setObjectName("hjaelpTekst")
            layout.addWidget(tekst)
            layout.addStretch()
            return
        self.krav_label = QLabel("")
        self.krav_label.setObjectName("hjaelpTekst")
        layout.addWidget(self.krav_label)
        layout.addWidget(self._opbyg_ny())
        layout.addWidget(self._opbyg_liste(), 1)

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_ny(self):
        kort, lag = _kort(
            "Ny version",
            "Pakken kontrolleres, før den sendes: versionen inde i exe-filen, kontrolsum, "
            "størrelse (højst 50 MB) og at databasen har det skema, versionen kræver. Den "
            "udgives først til pilotbrugerne (Indstillinger → Brugere → Pilotkanal).")
        self.slipfelt = Slipfelt()
        self.slipfelt.fil_valgt.connect(self.vaelg_fil)
        lag.addWidget(self.slipfelt)
        self.pakke_label = QLabel("")
        self.pakke_label.setWordWrap(True)
        self.advarsel_label = QLabel("")
        self.advarsel_label.setObjectName("advarsel")
        self.advarsel_label.setWordWrap(True)
        self.noter_input = QLineEdit()
        self.noter_input.setPlaceholderText("Hvad er nyt? (vises for brugerne i opdateringsdialogen)")
        self.tvungen_input = QCheckBox("Påkrævet – brugerne skal opdatere, før de kan arbejde videre")
        self.udgiv_knap = lav_knap("Udgiv til pilot", "primary")
        self.udgiv_knap.clicked.connect(self._udgiv)
        self.fremdrift = QProgressBar()
        self.fremdrift.setObjectName("fremdrift")
        self.fremdrift.setTextVisible(False)
        self.fremdrift.setFixedHeight(6)
        self.fremdrift.setRange(0, 0)                  # upload: ukendt varighed
        raekke = QHBoxLayout()
        raekke.addWidget(self.tvungen_input)
        raekke.addStretch()
        raekke.addWidget(self.udgiv_knap)
        for widget in (self.pakke_label, self.advarsel_label, self.noter_input):
            lag.addWidget(widget)
        lag.addLayout(raekke)
        lag.addWidget(self.fremdrift)
        self._nulstil()
        return kort

    def _opbyg_liste(self):
        kort, lag = _kort(
            "Udgivne versioner",
            "Pilot → afprøv → Frigiv til alle. En dårlig version: Træk tilbage – klienterne går "
            "selv tilbage til den nyeste gyldige. Supabase Free har begrænset udgående trafik: "
            "frigiv samlet, ikke hver build.")
        knapper = QHBoxLayout()
        frigiv = lav_knap("Frigiv til alle…", "primary")
        tilbage = lav_knap("Træk tilbage / gyldig igen", "danger")
        minimum = lav_knap("Kræv som mindste version…",
                           tooltip="Ældre klienter skal opdatere, før de kan arbejde videre")
        ryd = lav_knap("Ryd gamle installere…", tooltip="Sparer plads i Storage")
        frigiv.clicked.connect(self._frigiv)
        tilbage.clicked.connect(self._tilbagetraek)
        minimum.clicked.connect(self._minimum)
        ryd.clicked.connect(self._ryd)
        for knap in (frigiv, minimum, ryd):
            knapper.addWidget(knap)
        knapper.addStretch()
        knapper.addWidget(tilbage)
        lag.addLayout(knapper)
        self.tabel = QTableWidget(0, len(_KOLONNER))
        self.tabel.setHorizontalHeaderLabels(_KOLONNER)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        self.tabel.setMinimumHeight(220)
        for kolonne, bredde in enumerate((90, 80, 70, 130, 90, 130, 90, 110)):
            self.tabel.setColumnWidth(kolonne, bredde)
        lag.addWidget(self.tabel, 1)
        return kort

    ### ----- visning --------------------------------------------------------

    def opdater(self):
        if self.service is None:
            return
        krav = udfoer(self, self.service.krav)
        udgivelser = udfoer(self, self.service.udgivelser)
        if krav is FEJL or udgivelser is FEJL:
            return
        self.krav_label.setText(f"Du kører version {self.service.version} · databasens skema "
                                f"{krav.skema} · mindste klientversion {krav.min_klient}")
        self._udgivelser = udgivelser
        self.tabel.setRowCount(len(udgivelser))
        for raekke, u in enumerate(udgivelser):
            status = "Trukket tilbage" if u.trukket_tilbage else ("Påkrævet" if u.tvungen else "Gyldig")
            celler = (u.version, "Stabil" if u.kanal == op.STABIL else "Pilot",
                      f"{u.udrulning} %" if u.kanal == op.STABIL else "–", status,
                      _mb(u.stoerrelse), f"{vis_dato(u.oprettet[:10])} {u.oprettet[11:16]}".strip(),
                      u.oprettet_af, u.commit or "–", u.noter)
            for kolonne, tekst in enumerate(celler):
                item = QTableWidgetItem(tekst)
                item.setToolTip(u.noter or "")
                self.tabel.setItem(raekke, kolonne, item)

    def _nulstil(self):
        self._pakke = None
        self.pakke_label.setText("Ingen pakke valgt endnu.")
        self.advarsel_label.setVisible(False)
        self.noter_input.clear()
        self.tvungen_input.setChecked(False)
        self.udgiv_knap.setEnabled(False)
        self.udgiv_knap.setText("Udgiv til pilot")
        self.fremdrift.setVisible(False)
        self.slipfelt.setEnabled(True)

    ### ----- ny version -----------------------------------------------------

    def vaelg_fil(self, sti: str):
        self._nulstil()
        pakke = udfoer(self, self.service.kontroller_pakke, Path(sti))
        if pakke is FEJL:
            return
        self._pakke = pakke
        self.pakke_label.setText(
            f"✓ {pakke.sti.name} – version {pakke.version}, {_mb(pakke.stoerrelse)}, kræver "
            f"databaseskema {pakke.kraevet_skema}, commit {pakke.commit or 'ukendt'}.")
        self.advarsel_label.setText("\n".join(f"⚠ {a}" for a in pakke.advarsler))
        self.advarsel_label.setVisible(bool(pakke.advarsler))
        self.udgiv_knap.setText(f"Udgiv {pakke.version} til pilot")
        self.udgiv_knap.setEnabled(True)

    def _udgiv(self):
        pakke = self._pakke
        if pakke is None:
            return
        tekst = (f"Udgiv version {pakke.version} til pilotkanalen?\n\nPilotbrugerne får den ved "
                 "næste tjek (log på eller inden for 4 timer). Alle andre først, når du "
                 "frigiver den.")
        if QMessageBox.question(self, "Udgiv version", tekst) != QMessageBox.StandardButton.Yes:
            return
        self.udgiv_knap.setEnabled(False)
        self.udgiv_knap.setText("Uploader…")
        self.slipfelt.setEnabled(False)
        self.fremdrift.setVisible(True)
        koer_i_baggrund(self.service.udgiv, pakke, self.noter_input.text(),
                        self.tvungen_input.isChecked(),
                        naar_faerdig=self._udgivet, ved_fejl=self._udgiv_fejlede)

    def _udgivet(self, udgivelse: op.Udgivelse):
        self._nulstil()
        QMessageBox.information(self, "Udgivet",
                                f"Version {udgivelse.version} er udgivet til pilotkanalen.\n\n"
                                "Frigiv den til alle her, når den er afprøvet.")
        self.opdater()

    def _udgiv_fejlede(self, fejl: Exception):
        pakke = self._pakke
        self.fremdrift.setVisible(False)
        self.slipfelt.setEnabled(True)
        self.udgiv_knap.setEnabled(pakke is not None)
        self.udgiv_knap.setText(f"Udgiv {pakke.version} til pilot" if pakke else "Udgiv til pilot")
        vis_fejl(self, fejl, "udgive versionen")

    ### ----- udgivne versioner ----------------------------------------------

    def _valgt(self) -> op.Udgivelse | None:
        raekker = self.tabel.selectionModel().selectedRows()
        if not raekker:
            QMessageBox.information(self, "Ingen valgt", "Vælg en version i listen først.")
            return None
        return self._udgivelser[raekker[0].row()]

    def _frigiv(self):
        u = self._valgt()
        if u is None:
            return
        if u.trukket_tilbage:
            QMessageBox.information(self, "Frigiv", f"Version {u.version} er trukket tilbage. "
                                    "Gør den gyldig igen først.")
            return
        procent, ok = QInputDialog.getInt(
            self, f"Frigiv {u.version}",
            "Hvor stor en andel af brugerne skal have versionen?\n"
            "100 % = alle. Start evt. lavere og hæv senere.", 100, 1, 100, 25)
        if ok and udfoer(self, self.service.frigiv, u.version, procent) is not FEJL:
            self.opdater()

    def _tilbagetraek(self):
        u = self._valgt()
        if u is None:
            return
        tekst = (f"Gør version {u.version} gyldig igen?" if u.trukket_tilbage else
                 f"Træk version {u.version} tilbage?\n\nDen installeres ikke længere, og "
                 "klienter, der kører den, går selv tilbage til den nyeste gyldige version.")
        if QMessageBox.question(self, "Træk tilbage", tekst) != QMessageBox.StandardButton.Yes:
            return
        if udfoer(self, self.service.tilbagetraek, u.version, u.trukket_tilbage) is not FEJL:
            self.opdater()

    def _minimum(self):
        u = self._valgt()
        if u is None:
            return
        if u.kanal != op.STABIL or u.trukket_tilbage or u.udrulning < 100:
            QMessageBox.information(self, "Mindste version",
                                    f"Frigiv version {u.version} til alle (100 %) først – ellers "
                                    "kan nogle klienter ikke få den version, de kræves at have.")
            return
        tekst = (f"Kræv mindst version {u.version}?\n\nKlienter med en ældre version skal "
                 "opdatere, før de kan arbejde videre. Sæt det kun, når versionen virker.")
        if QMessageBox.question(self, "Mindste version", tekst) != QMessageBox.StandardButton.Yes:
            return
        if udfoer(self, self.service.saet_minimum, u.version) is not FEJL:
            self.opdater()

    def _ryd(self):
        tekst = ("Slet installerne for gamle versioner fra Storage?\n\nDe 5 nyeste og den nyeste "
                 "stabile beholdes. Tilbagetrukne versioner beholder rækken.")
        if QMessageBox.question(self, "Ryd gamle installere", tekst) != QMessageBox.StandardButton.Yes:
            return
        resultat = udfoer(self, self.service.ryd)
        if resultat is not FEJL:
            QMessageBox.information(self, "Ryd gamle installere",
                                    "\n".join(resultat) or "Der var intet at rydde.")
            self.opdater()
