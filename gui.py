from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QGridLayout,
    QFrame,
    QListWidget,
    QProgressBar,
)

from medarbejder import Medarbejder
import data_manager


class MedarbejderDialog(QDialog):
    def __init__(self, parent=None, medarbejder=None):
        super().__init__(parent)

        self.setWindowTitle("Opret medarbejder" if medarbejder is None else "Rediger medarbejder")
        self.setMinimumWidth(400)

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
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Medarbejdernavn", self.navn_input)
        form.addRow("Fratrædelsesdato", self.dato_input)
        form.addRow("Status", self.status_input)
        form.addRow("Kommentar", self.kommentar_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if medarbejder is not None:
            self.loennr_input.setText(str(medarbejder.loennr))
            self.navn_input.setText(medarbejder.navn)
            self.kommentar_input.setText(str(medarbejder.kommentar))

            dato = QDate.fromString(medarbejder.fratraedelsesdato, "yyyy-MM-dd")
            if dato.isValid():
                self.dato_input.setDate(dato)

            status_index = self.status_input.findText(medarbejder.status)
            if status_index >= 0:
                self.status_input.setCurrentIndex(status_index)

    def hent_data(self):
        return {
            "loennr": self.loennr_input.text().strip(),
            "navn": self.navn_input.text().strip(),
            "fratraedelsesdato": self.dato_input.date().toString("yyyy-MM-dd"),
            "status": self.status_input.currentText(),
            "kommentar": self.kommentar_input.text().strip(),
        }


class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder
    NOTIFIKATIONSDAGE = 14
    KOMMENDE_FRATRAEDELSESDAGE = 7

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Medarbejderafvikling")
        self.resize(1150, 780)

        # Programmets aktive medarbejdere og arkiv indlæses ved opstart.
        self.medarbejdere_liste = data_manager.hent_medarbejdere()
        self.medarbejdere_liste_arkiv = (data_manager.hent_arkiverede_medarbejdere())

        self.opbyg_gui()
        self.opdaterings_timer = QTimer(self)
        self.opdaterings_timer.setInterval(self.OPDATERINGS_INTERVAL)
        self.opdaterings_timer.timeout.connect(self.opdater_alle_visninger)
        self.opdaterings_timer.start()

    def opbyg_gui(self):
        self.faner = QTabWidget()
        self.setCentralWidget(self.faner)

        self.hovedside = QWidget()
        self.arkivside = QWidget()
        self.dashboard_side = QWidget()

        self.faner.addTab(self.hovedside, "Hovedside")
        self.faner.addTab(self.arkivside, "Arkiv")
        self.faner.addTab(self.dashboard_side, "Dashboard")

        self.opbyg_hovedside()
        self.opbyg_arkivside()
        self.opbyg_dashboard()

        self.opdater_alle_visninger()
        self.faner.currentChanged.connect(self.fane_skiftet)

    def opbyg_hovedside(self):
        hoved_layout = QVBoxLayout(self.hovedside)
        hoved_layout.setContentsMargins(18, 18, 18, 18)
        hoved_layout.setSpacing(12)

        titel = QLabel("Medarbejderafvikling")
        titel.setStyleSheet("font-size: 24px; font-weight: bold;")

        info = QLabel("V0.4")
        info.setStyleSheet("color: #64748B;")

        knap_layout = QHBoxLayout()
        self.opret_knap = QPushButton("Opret medarbejder")
        self.rediger_knap = QPushButton("Rediger")
        self.status_knap = QPushButton("Skift status")
        self.arkiver_knap = QPushButton("Arkiver")

        self.opret_knap.clicked.connect(self.opret_medarbejder)
        self.rediger_knap.clicked.connect(self.rediger_medarbejder)
        self.status_knap.clicked.connect(self.skift_status)
        self.arkiver_knap.clicked.connect(self.arkiver_medarbejder)

        knap_layout.addWidget(self.opret_knap)
        knap_layout.addWidget(self.rediger_knap)
        knap_layout.addWidget(self.status_knap)
        knap_layout.addWidget(self.arkiver_knap)
        knap_layout.addStretch()

        self.tabel = self.opret_medarbejder_tabel()

        hoved_layout.addWidget(titel)
        hoved_layout.addWidget(info)
        hoved_layout.addLayout(knap_layout)
        hoved_layout.addWidget(self.tabel)

    def opbyg_arkivside(self):
        arkiv_layout = QVBoxLayout(self.arkivside)
        arkiv_layout.setContentsMargins(18, 18, 18, 18)
        arkiv_layout.setSpacing(12)

        titel_arkiv = QLabel("Arkiverede medarbejdere")
        titel_arkiv.setStyleSheet("font-size: 24px; font-weight: bold;")

        knap_layout = QHBoxLayout()
        self.goer_aktiv_knap = QPushButton("Gør medarbejder aktiv")
        self.slet_knap = QPushButton("Slet medarbejder")

        self.goer_aktiv_knap.clicked.connect(self.aktiver_medarbejder)
        self.slet_knap.clicked.connect(self.slet_medarbejder)

        knap_layout.addWidget(self.goer_aktiv_knap)
        knap_layout.addWidget(self.slet_knap)
        knap_layout.addStretch()

        self.tabel_arkiv = self.opret_medarbejder_tabel()

        arkiv_layout.addWidget(titel_arkiv)
        arkiv_layout.addLayout(knap_layout)
        arkiv_layout.addWidget(self.tabel_arkiv)

    def opret_medarbejder_tabel(self):
        tabel = QTableWidget()
        tabel.setColumnCount(5)
        tabel.setHorizontalHeaderLabels([
            "Lønnr.",
            "Medarbejdernavn",
            "Fratrædelsesdato",
            "Status",
            "Kommentar",
        ])
        tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabel.horizontalHeader().setStretchLastSection(True)
        tabel.setAlternatingRowColors(True)
        return tabel

    def opbyg_dashboard(self):
        dashboard_layout = QVBoxLayout(self.dashboard_side)
        dashboard_layout.setContentsMargins(18, 18, 18, 18)
        dashboard_layout.setSpacing(14)

        titel = QLabel("Dashboard")
        titel.setStyleSheet("font-size: 24px; font-weight: bold;")

        undertitel = QLabel("Overblik over udstyr, fratrædelser og opgaver, der kræver opmærksomhed.")
        undertitel.setStyleSheet("color: #64748B;")

        dashboard_layout.addWidget(titel)
        dashboard_layout.addWidget(undertitel)

        kort_layout = QGridLayout()
        kort_layout.setSpacing(12)

        self.kort_aktive = self.opret_statistik_kort(
            kort_layout, "Aktive medarbejdere", 0, 0
        )
        self.kort_afventer = self.opret_statistik_kort(
            kort_layout, "Afventer udstyr", 0, 1
        )
        self.kort_delvist = self.opret_statistik_kort(
            kort_layout, "Delvist afleveret", 0, 2
        )
        self.kort_afviklet = self.opret_statistik_kort(
            kort_layout, "Afviklet", 1, 0
        )
        self.kort_arkiverede = self.opret_statistik_kort(
            kort_layout, "Arkiverede medarbejdere", 1, 1
        )

        dashboard_layout.addLayout(kort_layout)

        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_frame.setStyleSheet(
            "QFrame#statusFrame {"
            "background-color: #FFFFFF; border: 1px solid #D8DEE8;"
            "border-radius: 10px;"
            "}"
        )
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(14, 12, 14, 14)
        status_layout.setSpacing(10)

        status_titel = QLabel("Statusfordeling")
        status_titel.setStyleSheet("font-size: 18px; font-weight: bold;")
        status_layout.addWidget(status_titel)

        self.bar_afventer = self.opret_status_bar(
            status_layout, "Afventer udstyr", "#DC5454"
        )
        self.bar_delvist = self.opret_status_bar(
            status_layout, "Delvist afleveret", "#D7A52B"
        )
        self.bar_afviklet = self.opret_status_bar(
            status_layout, "Afviklet", "#3D9B70"
        )

        dashboard_layout.addWidget(status_frame)

        # To lister ved siden af hinanden.
        lister_layout = QHBoxLayout()
        lister_layout.setSpacing(12)

        notifikation_frame = QFrame()
        notifikation_frame.setFrameShape(QFrame.Shape.StyledPanel)
        notifikation_layout = QVBoxLayout(notifikation_frame)
        notifikation_layout.setContentsMargins(12, 12, 12, 12)

        notifikation_titel = QLabel("Kræver opmærksomhed")
        notifikation_titel.setStyleSheet("font-size: 17px; font-weight: bold; color: #B91C1C;")
        self.notifikations_liste = QListWidget()
        self.notifikations_liste.setAlternatingRowColors(True)
        self.notifikations_liste.setWordWrap(True)
        self.notifikations_liste.setMinimumHeight(140)
        notifikation_layout.addWidget(notifikation_titel)
        notifikation_layout.addWidget(self.notifikations_liste)

        kommende_frame = QFrame()
        kommende_frame.setFrameShape(QFrame.Shape.StyledPanel)
        kommende_layout = QVBoxLayout(kommende_frame)
        kommende_layout.setContentsMargins(12, 12, 12, 12)

        kommende_titel = QLabel("Fratræder inden for 7 dage")
        kommende_titel.setStyleSheet("font-size: 17px; font-weight: bold;")
        self.kommende_liste = QListWidget()
        self.kommende_liste.setAlternatingRowColors(True)
        self.kommende_liste.setWordWrap(True)
        self.kommende_liste.setMinimumHeight(140)
        kommende_layout.addWidget(kommende_titel)
        kommende_layout.addWidget(self.kommende_liste)

        lister_layout.addWidget(notifikation_frame, 1)
        lister_layout.addWidget(kommende_frame, 1)
        dashboard_layout.addLayout(lister_layout, 1)

    def opret_statistik_kort(self, layout, titel, raekke, kolonne):
        kort = QFrame()
        kort.setObjectName("statistikKort")
        kort.setFrameShape(QFrame.Shape.StyledPanel)
        kort.setMinimumHeight(90)
        kort.setStyleSheet(
            "QFrame#statistikKort {"
            "background-color: #F8FAFC; border: 1px solid #D8DEE8;"
            "border-radius: 10px;"
            "}"
            "QLabel#kortTitel {border: none; color: #475569; font-size: 12px;}"
            "QLabel#kortVaerdi {border: none; color: #0F172A;"
            "font-size: 27px; font-weight: bold;}"
        )

        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(14, 12, 14, 12)
        kort_layout.setSpacing(6)

        titel_label = QLabel(titel)
        titel_label.setObjectName("kortTitel")
        vaerdi_label = QLabel("0")
        vaerdi_label.setObjectName("kortVaerdi")

        kort_layout.addWidget(titel_label)
        kort_layout.addWidget(vaerdi_label)
        layout.addWidget(kort, raekke, kolonne)

        return vaerdi_label

    def opret_status_bar(self, layout, titel, farve):
        raekke = QHBoxLayout()
        titel_label = QLabel(titel)
        titel_label.setMinimumWidth(145)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setFormat("0 medarbejdere (0%)")
        progress.setMinimumHeight(24)
        progress.setStyleSheet(
            "QProgressBar {border: 1px solid #D1D5DB; border-radius: 5px;"
            "text-align: center; background-color: #F1F5F9;}"
            f"QProgressBar::chunk {{background-color: {farve}; border-radius: 4px;}}"
        )

        raekke.addWidget(titel_label)
        raekke.addWidget(progress, 1)
        layout.addLayout(raekke)
        return progress


    def opdater_tabel(self, visning, indholdliste):
        if visning == "tabel":
            tabel = self.tabel
        elif visning == "tabel_arkiv":
            tabel = self.tabel_arkiv
        else:
            raise ValueError(f"Ukendt tabelvisning: {visning}")

        # Bevar markering og scrollposition ved automatisk opdatering.
        valgt_loennr = None
        valgt_raekke = tabel.currentRow()
        if valgt_raekke >= 0:
            valgt_item = tabel.item(valgt_raekke, 0)
            if valgt_item is not None:
                valgt_loennr = valgt_item.text()

        scroll_position = tabel.verticalScrollBar().value()
        tabel.setUpdatesEnabled(False)

        try:
            tabel.setRowCount(0)

            for medarbejder in indholdliste:
                row = tabel.rowCount()
                tabel.insertRow(row)

                tabel.setItem(row, 0, QTableWidgetItem(str(medarbejder.loennr)))
                tabel.setItem(row, 1, QTableWidgetItem(str(medarbejder.navn)))

                dato = QDate.fromString(
                    str(medarbejder.fratraedelsesdato),
                    "yyyy-MM-dd"
                )
                vis_dato = (
                    dato.toString("dd-MM-yyyy")
                    if dato.isValid()
                    else str(medarbejder.fratraedelsesdato)
                )

                tabel.setItem(row, 2, QTableWidgetItem(vis_dato))
                tabel.setItem(row, 3, QTableWidgetItem(str(medarbejder.status)))
                tabel.setItem(row, 4, QTableWidgetItem(str(medarbejder.kommentar)))

                status_item = tabel.item(row, 3)
                if status_item is not None:
                    if status_item.text() == "Afventer Udstyr":
                        status_item.setForeground(QColor("white"))
                        status_item.setBackground(QColor("#DC5454"))
                    elif status_item.text() == "Delvist afleveret":
                        status_item.setForeground(QColor("black"))
                        status_item.setBackground(QColor("#F2CF58"))
                    elif status_item.text() == "Afviklet":
                        status_item.setForeground(QColor("white"))
                        status_item.setBackground(QColor("#3D9B70"))
        finally:
            tabel.setUpdatesEnabled(True)

        # Gendan markering ved at matche lønnr. igen.
        if valgt_loennr is not None:
            for row in range(tabel.rowCount()):
                item = tabel.item(row, 0)
                if item is not None and item.text() == valgt_loennr:
                    tabel.selectRow(row)
                    tabel.setCurrentCell(row, 0)
                    break

        tabel.verticalScrollBar().setValue(scroll_position)

    def valgt_medarbejder(self, visning):
        if visning == "tabel":
            tabel = self.tabel
            liste = self.medarbejdere_liste
        elif visning == "tabel_arkiv":
            tabel = self.tabel_arkiv
            liste = self.medarbejdere_liste_arkiv
        else:
            return None

        row = tabel.currentRow()
        if row < 0 or row >= len(liste):
            return None
        return liste[row]


    def opret_medarbejder(self):
        dialog = MedarbejderDialog(self)

        if not dialog.exec():
            return

        data = dialog.hent_data()
        if not data["loennr"] or not data["navn"]:
            QMessageBox.warning(
                self,
                "Manglende oplysninger",
                "Lønnr. og medarbejdernavn skal udfyldes."
            )
            return

        # Forebyg dubletter af lønnr. i den aktive liste og arkivet.
        alle_loennumre = {
            str(m.loennr)
            for m in self.medarbejdere_liste + self.medarbejdere_liste_arkiv
        }
        if data["loennr"] in alle_loennumre:
            QMessageBox.warning(
                self,
                "Lønnr. findes allerede",
                "Der findes allerede en medarbejder med dette lønnr."
            )
            return

        ny_medarbejder = Medarbejder(
            data["loennr"],
            data["navn"],
            data["fratraedelsesdato"],
            data["status"],
            data["kommentar"],
        )
        self.medarbejdere_liste.append(ny_medarbejder)
        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self.opdater_alle_visninger()

    def rediger_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel")
        if medarbejder is None:
            QMessageBox.information(
                self, "Ingen valgt", "Vælg en medarbejder først."
            )
            return

        dialog = MedarbejderDialog(self, medarbejder)
        if not dialog.exec():
            return

        data = dialog.hent_data()
        if not data["loennr"] or not data["navn"]:
            QMessageBox.warning(
                self,
                "Manglende oplysninger",
                "Lønnr. og medarbejdernavn skal udfyldes."
            )
            return

        # Kontrollér om lønnr. bruges af en anden medarbejder.
        for anden in self.medarbejdere_liste + self.medarbejdere_liste_arkiv:
            if anden is not medarbejder and str(anden.loennr) == data["loennr"]:
                QMessageBox.warning(
                    self,
                    "Lønnr. findes allerede",
                    "En anden medarbejder bruger allerede dette lønnr."
                )
                return

        medarbejder.loennr = data["loennr"]
        medarbejder.navn = data["navn"]
        medarbejder.fratraedelsesdato = data["fratraedelsesdato"]
        medarbejder.status = data["status"]
        medarbejder.kommentar = data["kommentar"]

        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self.opdater_alle_visninger()

    def skift_status(self):
        medarbejder = self.valgt_medarbejder("tabel")
        if medarbejder is None:
            QMessageBox.information(
                self, "Ingen valgt", "Vælg en medarbejder først."
            )
            return

        statuser = list(Medarbejder.STATUSER)
        try:
            nuvaerende_index = statuser.index(medarbejder.status)
        except ValueError:
            nuvaerende_index = -1

        medarbejder.status = statuser[(nuvaerende_index + 1) % len(statuser)]

        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self.opdater_alle_visninger()

    def arkiver_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel")
        if medarbejder is None:
            QMessageBox.information(
                self, "Ingen valgt", "Vælg en medarbejder først."
            )
            return

        svar = QMessageBox.question(
            self,
            "Arkiver medarbejder",
            f"Vil du arkivere {medarbejder.navn}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return

        data_manager.arkiver_medarbejder(medarbejder)
        self.medarbejdere_liste.remove(medarbejder)
        self.medarbejdere_liste_arkiv.append(medarbejder)
        # Arkivet gemmes af arkiveringsmetoden; gem den opdaterede aktivliste her.
        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self.opdater_alle_visninger()

    def aktiver_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel_arkiv")
        if medarbejder is None:
            QMessageBox.information(
                self, "Ingen valgt", "Vælg en medarbejder først."
            )
            return

        svar = QMessageBox.question(
            self,
            "Aktivér medarbejder",
            f"Vil du gøre {medarbejder.navn} aktiv igen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return

        data_manager.aktiver_medarbejder(medarbejder)
        self.medarbejdere_liste_arkiv.remove(medarbejder)
        self.medarbejdere_liste.append(medarbejder)
        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self.opdater_alle_visninger()

    def slet_medarbejder(self):
        ### Afventer
        QMessageBox.information(self, "Ikke implementeret", "Permanent sletning fra arkivet er endnu ikke implementeret.")



    def opdater_dashboard(self):
        aktive = self.medarbejdere_liste
        antal_aktive = len(aktive)

        antal_afventer = sum(
            1 for medarbejder in aktive
            if medarbejder.status == "Afventer Udstyr"
        )
        antal_delvist = sum(
            1 for medarbejder in aktive
            if medarbejder.status == "Delvist afleveret"
        )
        antal_afviklet = sum(
            1 for medarbejder in aktive
            if medarbejder.status == "Afviklet"
        )
        antal_arkiverede = len(self.medarbejdere_liste_arkiv)

        self.kort_aktive.setText(str(antal_aktive))
        self.kort_afventer.setText(str(antal_afventer))
        self.kort_delvist.setText(str(antal_delvist))
        self.kort_afviklet.setText(str(antal_afviklet))
        self.kort_arkiverede.setText(str(antal_arkiverede))

        self.opdater_status_bar(self.bar_afventer, antal_afventer, antal_aktive)
        self.opdater_status_bar(self.bar_delvist, antal_delvist, antal_aktive)
        self.opdater_status_bar(self.bar_afviklet, antal_afviklet, antal_aktive)

    @staticmethod
    def opdater_status_bar(bar, antal, total):
        procent = round(antal / total * 100) if total > 0 else 0
        bar.setValue(procent)
        bar.setFormat(f"{antal} medarbejdere ({procent}%)")

    def opdater_notifikationer(self):
        self.notifikations_liste.clear()
        i_dag = QDate.currentDate()
        notifikationer = []

        for medarbejder in self.medarbejdere_liste:
            if medarbejder.status != "Afventer Udstyr":
                continue

            dato = QDate.fromString(
                str(medarbejder.fratraedelsesdato),
                "yyyy-MM-dd"
            )
            if not dato.isValid():
                continue

            dage_siden = dato.daysTo(i_dag)
            if dage_siden >= self.NOTIFIKATIONSDAGE:
                tekst = (
                    f"{medarbejder.navn} (lønnr. {medarbejder.loennr}) - "
                    f"fratrådt {dato.toString('dd-MM-yyyy')} - "
                    f"{dage_siden} dage siden"
                )
                notifikationer.append((dage_siden, tekst))

        # Mest overskredne fratrædelser vises øverst.
        notifikationer.sort(key=lambda element: element[0], reverse=True)

        for _, tekst in notifikationer:
            self.notifikations_liste.addItem(tekst)

        if not notifikationer:
            self.notifikations_liste.addItem(
                "Ingen medarbejdere kræver opmærksomhed."
            )

    def opdater_kommende_fratraedelser(self):
        self.kommende_liste.clear()
        i_dag = QDate.currentDate()
        kommende = []

        for medarbejder in self.medarbejdere_liste:
            dato = QDate.fromString(
                str(medarbejder.fratraedelsesdato),
                "yyyy-MM-dd"
            )
            if not dato.isValid():
                continue

            dage_til = i_dag.daysTo(dato)
            if 0 <= dage_til <= self.KOMMENDE_FRATRAEDELSESDAGE:
                kommende.append((dato, dage_til, medarbejder))

        kommende.sort(key=lambda element: element[0].toJulianDay())

        for dato, dage_til, medarbejder in kommende:
            if dage_til == 0:
                tidspunkt = "Fratræder i dag"
            elif dage_til == 1:
                tidspunkt = "Fratræder i morgen"
            else:
                tidspunkt = f"Fratræder om {dage_til} dage"

            tekst = (
                f"{medarbejder.navn} (lønnr. {medarbejder.loennr}) - "
                f"{dato.toString('dd-MM-yyyy')} - {tidspunkt}"
            )
            self.kommende_liste.addItem(tekst)

        if not kommende:
            self.kommende_liste.addItem("Ingen kommende fratrædelser inden for 7 dage.")


    def fane_skiftet(self, index):
        if self.faner.widget(index) == self.dashboard_side:
            self.opdater_dashboard_visning()

    def opdater_dashboard_visning(self):
        self.opdater_dashboard()
        self.opdater_notifikationer()
        self.opdater_kommende_fratraedelser()

    def opdater_alle_visninger(self):
        self.opdater_tabel("tabel", self.medarbejdere_liste)
        self.opdater_tabel("tabel_arkiv", self.medarbejdere_liste_arkiv)
        self.opdater_dashboard_visning()
