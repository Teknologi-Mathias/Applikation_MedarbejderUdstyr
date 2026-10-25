"""Siden Data & sikkerhed: sikkerhedskopier, gendannelse, slettepolitik og adgang.

Sikkerhedskopier af filer findes kun i JSON-tilstanden (tjenester.backup).
I Supabase-tilstand tager Supabase backup af databasen; siden forklarer det.
"""
from datetime import date

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.backup_service import udloebne
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved, vis_dato

_AARSAGER = {
    "daglig": "Daglig (automatisk)",
    "manuel": "Manuel",
    "foer-gendannelse": "Før gendannelse",
    "foer-migrering": "Før migrering",
}


def _kort(titel, forklaring):
    kort = lav_kort()
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


class DataSide(QWidget):
    # Udsendes når data er ændret her (gendannelse/sletning), så vinduet genindlæser.
    data_aendret = Signal()

    def __init__(self, tjenester, hent_arkiv):
        """hent_arkiv: () -> arkiverede sager fra begge moduler."""
        super().__init__()
        self.t = tjenester
        self.hent_arkiv = hent_arkiv

        ydre = QVBoxLayout(self)
        ydre.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        ydre.addWidget(scroll)
        indre = QWidget()
        indre.setObjectName("scrollInner")
        scroll.setWidget(indre)

        layout = QVBoxLayout(indre)
        layout.setContentsMargins(0, 12, 8, 12)
        layout.setSpacing(18)
        hoved, _ = lav_sidehoved(
            "Data & sikkerhed",
            "Sikkerhedskopier, gendannelse og opbevaring af persondata.",
        )
        layout.addLayout(hoved)
        layout.addWidget(self._opbyg_backup() if self.t.backup else self._opbyg_database_backup())
        layout.addWidget(self._opbyg_opbevaring())
        layout.addWidget(self._opbyg_adgang())
        layout.addStretch()

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_backup(self):
        kort, layout = _kort(
            "Sikkerhedskopier",
            "Der tages automatisk én backup om dagen. Hver backup testes, så snart "
            "den er taget. Ved gendannelse gemmes de nuværende data først som en "
            "ny backup, så intet går tabt.",
        )

        mappe_raekke = QHBoxLayout()
        self.mappe_felt = QLineEdit()
        self.mappe_felt.setReadOnly(True)
        skift = lav_knap("Skift mappe…")
        skift.clicked.connect(self._skift_mappe)
        aabn = lav_knap("Åbn mappe")
        aabn.clicked.connect(self._aabn_backupmappe)
        mappe_raekke.addWidget(QLabel("Placering"))
        mappe_raekke.addWidget(self.mappe_felt, 1)
        mappe_raekke.addWidget(skift)
        mappe_raekke.addWidget(aabn)
        layout.addLayout(mappe_raekke)

        antal_raekke = QHBoxLayout()
        self.antal_input = QSpinBox()
        self.antal_input.setRange(3, 365)
        self.antal_input.setSuffix(" backups")
        gem_antal = lav_knap("Gem")
        gem_antal.clicked.connect(self._gem_antal)
        antal_raekke.addWidget(QLabel("Behold de nyeste"))
        antal_raekke.addWidget(self.antal_input)
        antal_raekke.addWidget(gem_antal)
        antal_raekke.addStretch()
        layout.addLayout(antal_raekke)

        knapper = QHBoxLayout()
        tag = lav_knap("Tag backup nu", "primary")
        test = lav_knap("Test valgt backup")
        gendan = lav_knap("Gendan valgt backup…", "danger")
        tag.clicked.connect(self._tag_backup)
        test.clicked.connect(self._test_backup)
        gendan.clicked.connect(self._gendan)
        for knap in (tag, test):
            knapper.addWidget(knap)
        knapper.addStretch()
        knapper.addWidget(gendan)
        layout.addLayout(knapper)

        self.backup_tabel = QTableWidget(0, 5)
        self.backup_tabel.setHorizontalHeaderLabels(
            ["Tidspunkt", "Type", "Bruger", "Aktive (offboarding)", "Arkiv · onboarding"]
        )
        self.backup_tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.backup_tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.backup_tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.backup_tabel.setShowGrid(False)
        self.backup_tabel.setAlternatingRowColors(True)
        self.backup_tabel.verticalHeader().setVisible(False)
        self.backup_tabel.horizontalHeader().setStretchLastSection(True)
        self.backup_tabel.setMinimumHeight(240)
        for kolonne, bredde in enumerate((170, 170, 140, 90)):
            self.backup_tabel.setColumnWidth(kolonne, bredde)
        layout.addWidget(self.backup_tabel)

        self.backup_status = QLabel("")
        self.backup_status.setObjectName("info")
        self.backup_status.setWordWrap(True)
        self.backup_status.setVisible(False)
        layout.addWidget(self.backup_status)
        return kort

    def _opbyg_database_backup(self):
        kort, _ = _kort(
            "Sikkerhedskopier",
            "Data ligger i den fælles Supabase-database. Sikkerhedskopier tages af "
            "Supabase (Dashboard → Database → Backups) – ikke af programmet – og "
            "gendannelse sker dér af projektets ejer. Programmet gemmer ingen "
            "lokale kopier af persondata.",
        )
        return kort

    def _opbyg_opbevaring(self):
        kort, layout = _kort(
            "Opbevaring og sletning",
            "Oplysninger om tidligere medarbejdere må ikke gemmes længere end "
            "nødvendigt. Arkiverede sager slettes, når opbevaringsperioden er "
            "udløbet – regnet fra arkiveringsdatoen (eller sidste arbejdsdag, "
            "hvis sagen er arkiveret før denne funktion fandtes). Aftal perioden "
            "med HR. Sletning sker først, når du bekræfter.",
        )
        raekke = QHBoxLayout()
        self.maaneder_input = QSpinBox()
        self.maaneder_input.setRange(1, 120)
        self.maaneder_input.setSuffix(" måneder")
        gem = lav_knap("Gem")
        gem.clicked.connect(self._gem_maaneder)
        raekke.addWidget(QLabel("Slet arkiverede sager efter"))
        raekke.addWidget(self.maaneder_input)
        raekke.addWidget(gem)
        raekke.addStretch()
        layout.addLayout(raekke)

        self.udloebne_label = QLabel("")
        self.udloebne_label.setObjectName("cardTitle")
        self.udloebne_liste = QListWidget()
        self.udloebne_liste.setMaximumHeight(160)
        self.slet_knap = lav_knap("Slet udløbne sager permanent…", "danger")
        self.slet_knap.clicked.connect(self._slet_udloebne)
        layout.addWidget(self.udloebne_label)
        layout.addWidget(self.udloebne_liste)
        layout.addWidget(self.slet_knap)
        return kort

    def _opbyg_adgang(self):
        if self.t.datakilde is None:
            kort, _ = _kort(
                "Adgang til persondata",
                "Adgang styres af databasen: kun brugere med en aktiv IN-BASE-profil kan "
                "logge på og se sager (Row Level Security). En deaktiveret bruger mister "
                "straks adgangen. Kun administratorer kan ændre opsætning, administrere "
                "brugere og slette sager permanent. Tidslinjen kan ikke ændres eller "
                "slettes af brugerne.",
            )
            return kort
        kort, layout = _kort(
            "Adgang til persondata",
            "Navne, e-mailadresser, tracking-links og tidslinjer ligger i "
            "datamappen nedenfor. Log på og roller i IN-BASE er BETA og beskytter "
            "ikke selve filerne – den reelle adgang styres af Windows-rettighederne "
            "på mappen: giv kun de medarbejdere, der arbejder med afviklinger, "
            "læse- og skriveadgang, og læg backupmappen et sted med samme "
            "begrænsning. Backups indeholder de samme persondata og slettes "
            "automatisk, når de er ældre end det valgte antal.",
        )
        raekke = QHBoxLayout()
        mappe = self.t.datakilde.central_mappe
        felt = QLineEdit(str(mappe))
        felt.setReadOnly(True)
        aabn = lav_knap("Åbn datamappe")
        aabn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(mappe))))
        raekke.addWidget(felt, 1)
        raekke.addWidget(aabn)
        layout.addLayout(raekke)
        return kort

    ### ----- visning --------------------------------------------------------

    def opdater(self):
        ind = self.t.indstillinger.hent()
        self.maaneder_input.setValue(int(ind["opbevaring_maaneder"]))
        if self.t.backup:
            self._vis_backups(ind)
        self.udloebne = udloebne(self.hent_arkiv(), ind["opbevaring_maaneder"], date.today())
        self._opdater_udloebne()

    def _vis_backups(self, ind):
        self.mappe_felt.setText(str(self.t.backup.mappe()))
        self.antal_input.setValue(int(ind["backup_antal"]))
        self.backups = self.t.backup.liste()
        self.backup_tabel.setRowCount(len(self.backups))
        for raekke, b in enumerate(self.backups):
            celler = (
                f"{vis_dato(b.tid.date().isoformat())} {b.tid:%H:%M:%S}",
                _AARSAGER.get(b.aarsag, b.aarsag),
                b.bruger,
                str(b.antal_aktive),
                f"{b.antal_arkiv} · onboarding {b.antal_onboarding}",
            )
            for kolonne, tekst in enumerate(celler):
                self.backup_tabel.setItem(raekke, kolonne, QTableWidgetItem(tekst))

    def _opdater_udloebne(self):
        self.udloebne_label.setText(
            f"{len(self.udloebne)} arkiverede sager har overskredet opbevaringsperioden"
        )
        self.udloebne_liste.clear()
        for m, dato in self.udloebne:
            self.udloebne_liste.addItem(
                f"{m.navn} ({m.PROCES}, lønnr. {m.loennr or '–'}) – kunne slettes fra {dato:%d-%m-%Y}"
            )
        self.udloebne_liste.setVisible(bool(self.udloebne))
        self.slet_knap.setEnabled(bool(self.udloebne))

    def _vis_status(self, tekst, fejl=False):
        self.backup_status.setObjectName("advarsel" if fejl else "info")
        self.backup_status.style().unpolish(self.backup_status)
        self.backup_status.style().polish(self.backup_status)
        self.backup_status.setText(tekst)
        self.backup_status.setVisible(True)

    def _valgt_backup(self):
        rows = self.backup_tabel.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Ingen valgt", "Vælg en backup i listen først.")
            return None
        return self.backups[rows[0].row()]

    ### ----- handlinger -----------------------------------------------------

    def _skift_mappe(self):
        mappe = QFileDialog.getExistingDirectory(
            self, "Vælg mappe til sikkerhedskopier", str(self.t.backup.mappe())
        )
        if mappe and udfoer(self, self.t.indstillinger.opdater, backup_mappe=mappe) is not FEJL:
            self.opdater()

    def _aabn_backupmappe(self):
        mappe = self.t.backup.mappe()
        mappe.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(mappe)))

    def _gem_antal(self):
        if udfoer(self, self.t.indstillinger.opdater,
                  backup_antal=self.antal_input.value()) is not FEJL:
            self.t.backup.ryd_gamle()
            self.opdater()

    def _gem_maaneder(self):
        if udfoer(self, self.t.indstillinger.opdater,
                  opbevaring_maaneder=self.maaneder_input.value()) is not FEJL:
            self.opdater()

    def _tag_backup(self):
        info = udfoer(self, self.t.backup.tag_backup, "manuel")
        if info is FEJL:
            self._vis_status("Backup mislykkedes – se fejlbeskeden.", fejl=True)
            return
        self.opdater()
        self._vis_status(f"Backup taget og testet: {info.sti.name}")

    def _test_backup(self):
        valgt = self._valgt_backup()
        if valgt:
            ok, besked = self.t.backup.test_backup(valgt.sti)
            self._vis_status(("✓ " if ok else "✗ ") + besked, fejl=not ok)

    def _gendan(self):
        valgt = self._valgt_backup()
        if valgt is None:
            return
        svar = QMessageBox.warning(
            self,
            "Gendan backup",
            f"Vil du erstatte de nuværende data med backuppen fra "
            f"{valgt.tid:%d-%m-%Y %H:%M}?\n\n"
            "De nuværende data gemmes først som en ny backup ('Før gendannelse'), "
            "så handlingen kan fortrydes ved at gendanne den.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return
        besked = udfoer(self, self.t.backup.gendan, valgt.sti)
        if besked is FEJL:
            self._vis_status("Gendannelse mislykkedes – de nuværende data er urørte.", fejl=True)
            return
        self.data_aendret.emit()
        self.opdater()
        self._vis_status(f"Backup gendannet. {besked}")

    def _slet_udloebne(self):
        if not self.udloebne:
            return
        navne = "\n".join(f"• {m.navn} (lønnr. {m.loennr})" for m, _ in self.udloebne[:15])
        if len(self.udloebne) > 15:
            navne += f"\n… og {len(self.udloebne) - 15} mere"
        svar = QMessageBox.warning(
            self,
            "Slet udløbne sager",
            f"Følgende {len(self.udloebne)} sager slettes permanent, inkl. "
            f"tidslinje og kontaktoplysninger:\n\n{navne}\n\n"
            "De forsvinder også fra backups, efterhånden som de gamle backups slettes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return
        for sag, _ in self.udloebne:
            udfoer(self, self.t.modul(sag.PROCES).slet, sag)
        self.data_aendret.emit()
        self.opdater()
