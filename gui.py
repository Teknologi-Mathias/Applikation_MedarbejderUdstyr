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

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

        if medarbejder is not None:
            self.loennr_input.setText(str(medarbejder.loennr))
            self.navn_input.setText(medarbejder.navn)

            dato = QDate.fromString(medarbejder.fratraedelsesdato, "yyyy-MM-dd")
            if dato.isValid():
                self.dato_input.setDate(dato)

            index = self.status_input.findText(medarbejder.status)
            if index >= 0:
                self.status_input.setCurrentIndex(index)

            self.kommentar_input.setText(str(medarbejder.kommentar))


    def hent_data(self):

        ### TODO: Senere mere inputvalidering her.

        return {
            "loennr": self.loennr_input.text().strip(),
            "navn": self.navn_input.text().strip(),
            "fratraedelsesdato": self.dato_input.date().toString("yyyy-MM-dd"),
            "status": self.status_input.currentText(),
            "kommentar": self.kommentar_input.text(),
        }



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Medarbejderafvikling")
        self.resize(1100, 700)

        ### Dette er programmets aktive liste.
        self.medarbejdere_liste = data_manager.hent_medarbejdere()
        ### Dette er programmets aktive arkiv.
        self.medarbejdere_liste_arkiv = data_manager.hent_arkiverede_medarbejdere()

        self.opbyg_gui()
         ### TIMER TIL OPDATERING AUTOMATISK
        self.opdaterings_timer = QTimer(self)

        self.opdaterings_timer.timeout.connect(
            self.opdater_alle_visninger
        )

        # Opdater hvert 60. sekund.
        self.opdaterings_timer.start(60_000)


    def opbyg_gui(self):
        self.faner = QTabWidget()
        self.setCentralWidget(self.faner)

        self.hovedside = QWidget()
        self.arkivside = QWidget()
        self.dashboard_side = QWidget()

        self.faner.addTab(self.hovedside, "Hovedside")
        self.faner.addTab(self.arkivside, "Arkiv")
        self.faner.addTab(self.dashboard_side, "Dashboard")

        self.central = self.hovedside

        self.opbyg_hovedside()
        self.opbyg_arkivside()
        self.opbyg_dashboard()

        # Alle widgets eksisterer nu.
        self.opdater_alle_visninger()

        self.faner.currentChanged.connect(self.fane_skiftet)



    def opdater_tabel(self, visning, indholdliste):

        if visning == "tabel":
            self.tabel.setRowCount(0)


            for medarbejder in indholdliste:
                row = self.tabel.rowCount()
                self.tabel.insertRow(row)

                self.tabel.setItem(row, 0, QTableWidgetItem(str(medarbejder.loennr)))
                self.tabel.setItem(row, 1, QTableWidgetItem(medarbejder.navn))

                dato = QDate.fromString(medarbejder.fratraedelsesdato, "yyyy-MM-dd")
                vis_dato = dato.toString("dd-MM-yyyy") if dato.isValid() else medarbejder.fratraedelsesdato
                self.tabel.setItem(row, 2, QTableWidgetItem(vis_dato))
                self.tabel.setItem(row, 3, QTableWidgetItem(medarbejder.status))
                self.tabel.setItem(row, 4, QTableWidgetItem(medarbejder.kommentar)) ### Vender omvendt, grundet medarbejder klassen standard variabel værdi i initialiseringen


                item = self.tabel.item(row, 3)
                if item and item.text() == "Afventer Udstyr":
                    item.setForeground(QColor("white"))
                    item.setBackground(QColor("red"))
                if item and item.text() == "Delvist afleveret":
                    item.setForeground(QColor("black"))
                    item.setBackground(QColor("yellow"))              
                if item and item.text() == "Afviklet":
                    item.setForeground(QColor("white"))
                    item.setBackground(QColor("green"))
        elif visning == "tabel_arkiv":
            self.tabel_arkiv.setRowCount(0)


            for medarbejder in indholdliste:
                row = self.tabel_arkiv.rowCount()
                self.tabel_arkiv.insertRow(row)

                self.tabel_arkiv.setItem(row, 0, QTableWidgetItem(str(medarbejder.loennr)))
                self.tabel_arkiv.setItem(row, 1, QTableWidgetItem(medarbejder.navn))

                dato = QDate.fromString(medarbejder.fratraedelsesdato, "yyyy-MM-dd")
                vis_dato = dato.toString("dd-MM-yyyy") if dato.isValid() else medarbejder.fratraedelsesdato
                self.tabel_arkiv.setItem(row, 2, QTableWidgetItem(vis_dato))
                self.tabel_arkiv.setItem(row, 3, QTableWidgetItem(medarbejder.status))
                self.tabel_arkiv.setItem(row, 4, QTableWidgetItem(medarbejder.kommentar)) ### Vender omvendt, grundet medarbejder klassen standard variabel værdi i initialiseringen


                item = self.tabel_arkiv.item(row, 3)
                if item and item.text() == "Afventer Udstyr":
                    item.setForeground(QColor("white"))
                    item.setBackground(QColor("red"))
                if item and item.text() == "Delvist afleveret":
                    item.setForeground(QColor("black"))
                    item.setBackground(QColor("yellow"))              
                if item and item.text() == "Afviklet":
                    item.setForeground(QColor("white"))
                    item.setBackground(QColor("green"))

    def valgt_medarbejder(self, visning):

        ### TODO: Koble tabelrækken til objektet på en sikker måde.
        if visning == "tabel":
            row = self.tabel.currentRow()
            if row < 0:
                return None

            if row >= len(self.medarbejdere_liste):
                return None

            return self.medarbejdere_liste[row]
        elif visning == "tabel_arkiv":
            row = self.tabel_arkiv.currentRow()
            if row < 0:
                return None

            if row >= len(self.medarbejdere_liste_arkiv):
                return None

            return self.medarbejdere_liste_arkiv[row]

    def opret_medarbejder(self):
        dialog = MedarbejderDialog(self)

        if dialog.exec():
            data = dialog.hent_data()

            loennr = data["loennr"]
            navn = data["navn"]
            fratraedelsesdato = data["fratraedelsesdato"]
            status = data["status"]
            kommentar = data["kommentar"]

            ny_medarbejder = Medarbejder(loennr, navn, fratraedelsesdato, status, kommentar)
            self.medarbejdere_liste.append(ny_medarbejder)
            data_manager.gem_medarbejdere(self.medarbejdere_liste)  

            self.opdater_alle_visninger()


    def rediger_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel")
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        dialog = MedarbejderDialog(self, medarbejder)

        if dialog.exec():
            data = dialog.hent_data()

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
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        if medarbejder.status == "Afventer Udstyr":
            medarbejder.status = "Delvist afleveret"
            data_manager.gem_medarbejdere(self.medarbejdere_liste)  
            self.opdater_alle_visninger()
        elif medarbejder.status == "Delvist afleveret":
            medarbejder.status = "Afviklet"
            data_manager.gem_medarbejdere(self.medarbejdere_liste)  
            self.opdater_alle_visninger()
        else: 
            medarbejder.status = "Afventer Udstyr"
            data_manager.gem_medarbejdere(self.medarbejdere_liste)  
            self.opdater_alle_visninger()

        #TODO: Denne ændring skal også afspejles i JSON filerne. 


    def arkiver_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel")
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        svar = QMessageBox.question(self, "Arkiver medarbejder", f"Vil du arkivere {medarbejder.navn}?",)

        if svar == QMessageBox.Yes:

            data_manager.arkiver_medarbejder(medarbejder)

            self.medarbejdere_liste_arkiv.append(medarbejder)
            self.medarbejdere_liste.remove(medarbejder)

            self.opdater_alle_visninger()


    def opbyg_hovedside(self):
        hoved_layout = QVBoxLayout()

        titel = QLabel("Medarbejderafvikling")
        titel.setStyleSheet("font-size: 24px; font-weight: bold;")

        info = QLabel("V0.3") ### VERSION

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

        self.tabel = QTableWidget()
        self.tabel.setColumnCount(5)
        self.tabel.setHorizontalHeaderLabels([
            "Lønnr.",
            "Medarbejdernavn",
            "Fratrædelsesdato",
            "Status",
            "Kommentar",
        ])
        self.tabel.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabel.setSelectionMode(QTableWidget.SingleSelection)
        self.tabel.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        self.tabel.setAlternatingRowColors(True)

        hoved_layout.addWidget(titel)
        hoved_layout.addWidget(info)
        hoved_layout.addLayout(knap_layout)
        hoved_layout.addWidget(self.tabel)
            

            
        self.central.setLayout(hoved_layout)


    def opbyg_arkivside(self):
        arkiv_layout = QVBoxLayout(self.arkivside)

        titel_arkiv = QLabel("Arkiverede medarejdere")
        titel_arkiv.setStyleSheet("font-size: 24px; font-weight: bold;")

        knap_layout = QHBoxLayout()

        self.goer_aktiv_knap = QPushButton("Gør medarbejder aktiv")
        self.slet_knap = QPushButton("Slet medarbejder")

        self.goer_aktiv_knap.clicked.connect(self.aktiver_medarbejder)
        self.slet_knap.clicked.connect(self.slet_medarbejder)

        knap_layout.addWidget(self.goer_aktiv_knap)
        knap_layout.addWidget(self.slet_knap)

        self.tabel_arkiv = QTableWidget()
        self.tabel_arkiv.setColumnCount(5)
        self.tabel_arkiv.setHorizontalHeaderLabels([
            "Lønnr.",
            "Medarbejdernavn",
            "Fratrædelsesdato",
            "Status",
            "Kommentar",
        ])
        self.tabel_arkiv.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabel_arkiv.setSelectionMode(QTableWidget.SingleSelection)
        self.tabel_arkiv.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabel_arkiv.horizontalHeader().setStretchLastSection(True)
        self.tabel_arkiv.setAlternatingRowColors(True)

        arkiv_layout.addWidget(titel_arkiv)
        arkiv_layout.addLayout(knap_layout)
        arkiv_layout.addWidget(self.tabel_arkiv)



    def aktiver_medarbejder(self):
        medarbejder = self.valgt_medarbejder("tabel_arkiv")
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        svar = QMessageBox.question(self, "Aktiver medarbejder", f"Vil du aktiver {medarbejder.navn} igen?",)

        if svar == QMessageBox.Yes:

            data_manager.aktiver_medarbejder(medarbejder)

            self.medarbejdere_liste_arkiv.remove(medarbejder)
            self.medarbejdere_liste.append(medarbejder)

            self.opdater_alle_visninger()

    def slet_medarbejder(self):
        pass


    def opbyg_dashboard(self):
        dashboard_layout = QVBoxLayout(self.dashboard_side)

        titel = QLabel("Dashboard")
        titel.setStyleSheet("font-size: 24px; font-weight: bold;")
        dashboard_layout.addWidget(titel)

        kort_layout = QGridLayout()
        kort_layout.setSpacing(12)

        self.kort_aktive = self.opret_statistik_kort(
            kort_layout, "Aktive medarbejdere", 0, 0
        )

        self.kort_afventer = self.opret_statistik_kort(
            kort_layout, "Afventer Udstyr", 0, 1
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

        notifikation_titel = QLabel("Kræver opmærksomhed")
        notifikation_titel.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.notifikations_liste = QListWidget()

        dashboard_layout.addWidget(notifikation_titel)
        dashboard_layout.addWidget(self.notifikations_liste)



    def opret_statistik_kort(self, layout, titel, raekke, kolonne):
        kort = QFrame()
        kort.setFrameShape(QFrame.Shape.StyledPanel)

        kort_layout = QVBoxLayout(kort)

        titel_label = QLabel(titel)
        vaerdi_label = QLabel("0")
        vaerdi_label.setStyleSheet("font-size: 26px; font-weight: bold;")

        kort_layout.addWidget(titel_label)
        kort_layout.addWidget(vaerdi_label)

        layout.addWidget(kort, raekke, kolonne)

        return vaerdi_label
    

    def opdater_dashboard(self):
        aktive = self.medarbejdere_liste
        arkiv = self.medarbejdere_liste_arkiv

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

        antal_arkiverede = len(arkiv)

        self.kort_aktive.setText(str(antal_aktive))
        self.kort_afventer.setText(str(antal_afventer))
        self.kort_delvist.setText(str(antal_delvist))
        self.kort_afviklet.setText(str(antal_afviklet))
        self.kort_arkiverede.setText(str(antal_arkiverede))

    def opdater_notifikationer(self):
        self.notifikations_liste.clear()

        i_dag = QDate.currentDate()
        antal_notifikationer = 0

        for medarbejder in self.medarbejdere_liste:

            if medarbejder.status != "Afventer Udstyr":
                continue

            dato = QDate.fromString(
                medarbejder.fratraedelsesdato,
                "yyyy-MM-dd"
            )

            if not dato.isValid():
                continue

            dage_siden = dato.daysTo(i_dag)

            if dage_siden >= 14:
                tekst = (
                    f"{medarbejder.navn} "
                    f"(lønnr. {medarbejder.loennr}) - "
                    f"fratrådt {dato.toString('dd-MM-yyyy')} - "
                    f"{dage_siden} dage siden"
                )

                self.notifikations_liste.addItem(tekst)
                antal_notifikationer += 1

        if antal_notifikationer == 0:
            self.notifikations_liste.addItem(
                "Ingen medarbejdere kræver opmærksomhed."
            )

    def fane_skiftet(self, index):
        if self.faner.widget(index) == self.dashboard_side:
            self.opdater_dashboard_visning()
           

    def opdater_dashboard_visning(self):
        self.opdater_dashboard()
        self.opdater_notifikationer()
    
    def opdater_alle_visninger(self):
        # Hovedside
        self.opdater_tabel("tabel", self.medarbejdere_liste)

        # Arkiv
        self.opdater_tabel("tabel_arkiv",self.medarbejdere_liste_arkiv)

        # Dashboard
        self.opdater_dashboard()
        self.opdater_notifikationer()