from PySide6.QtCore import QDate, Qt
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

    def hent_data(self):
        """Returnerer indtastningerne.

        TODO: Du kan senere placere mere inputvalidering her.
        """
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
        self.medarbejdere_liste_arkiv = []

        self.opbyg_gui()
        # self.indlaes_testdata()

    def opbyg_gui(self):
        central = QWidget()
        self.setCentralWidget(central)

        hoved_layout = QVBoxLayout()

        titel = QLabel("Medarbejderafvikling")
        titel.setStyleSheet("font-size: 24px; font-weight: bold;")

        info = QLabel(
            "V0.2"
        )

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

        ### Reserveret område til dashboard senere.
        dashboard_note = QLabel("Dashboard: kommer i en senere version")
        dashboard_note.setAlignment(Qt.AlignCenter)
        dashboard_note.setMinimumHeight(60)

        hoved_layout.addWidget(titel)
        hoved_layout.addWidget(info)
        hoved_layout.addLayout(knap_layout)
        hoved_layout.addWidget(self.tabel)
        hoved_layout.addWidget(dashboard_note)

        central.setLayout(hoved_layout)

    # def indlaes_testdata(self):
    #     """Midlertidig testdata, så GUI'en har noget at vise."""
    #     self.medarbejdere_liste = [
    #         Medarbejder("10025", "Jens Jensen", "2026-10-15", "Test 1"),
    #         Medarbejder("10118", "Anna Hansen", "2026-10-20", "Test 2 Test 2 Test 2 Test 2 Test 2 Test 2 Test 2 "),
    #         Medarbejder("10344", "Peter Nielsen", "2026-09-15", ""),
    #     ]

        self.opdater_tabel()

    def opdater_tabel(self):

        self.tabel.setRowCount(0)


        for medarbejder in self.medarbejdere_liste:
            row = self.tabel.rowCount()
            self.tabel.insertRow(row)

            self.tabel.setItem(row, 0, QTableWidgetItem(str(medarbejder.loennr)))
            self.tabel.setItem(row, 1, QTableWidgetItem(medarbejder.navn))

            dato = QDate.fromString(medarbejder.fratraedelsesdato, "yyyy-MM-dd")
            vis_dato = dato.toString("dd-MM-yyyy") if dato.isValid() else medarbejder.fratraedelsesdato
            self.tabel.setItem(row, 2, QTableWidgetItem(vis_dato))
            self.tabel.setItem(row, 4, QTableWidgetItem(medarbejder.kommentar)) ### Vender omvendt, grundet medarbejder klassen standard variabel værdi i initialiseringen
            self.tabel.setItem(row, 3, QTableWidgetItem(medarbejder.status))

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

    def valgt_medarbejder(self):

        ### TODO: Koble tabelrækken til objektet på en sikker måde.

        row = self.tabel.currentRow()
        if row < 0:
            return None

        if row >= len(self.medarbejdere_liste):
            return None

        return self.medarbejdere_liste[row]

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

            self.opdater_tabel()


    def rediger_medarbejder(self):
        medarbejder = self.valgt_medarbejder()
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        dialog = MedarbejderDialog(self, medarbejder)

        if dialog.exec():
            data = dialog.hent_data()

            medarbejder.loennr = data["loennr"]
            medarbejder.navn = data["navn"]
            medarbejder.fratraedelsesdato = data["fratraedelsesdato"]
            medarbejder.kommentar = data["kommentar"] 
            medarbejder.status = data["status"] 


            data_manager.gem_medarbejdere(self.medarbejdere_liste)  
            self.opdater_tabel()

    def skift_status(self):
        medarbejder = self.valgt_medarbejder()
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        if medarbejder.status == "Afventer Udstyr":
            medarbejder.status = "Delvist afleveret"
            self.opdater_tabel()
        elif medarbejder.status == "Delvist afleveret":
            medarbejder.status = "Afviklet"
            self.opdater_tabel()
        else: 
            medarbejder.status = "Afventer Udstyr"
            self.opdater_tabel()

        #TODO: Denne ændring skal også afspejles i JSON filerne. 


    def arkiver_medarbejder(self):
        medarbejder = self.valgt_medarbejder()
        if medarbejder is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return

        svar = QMessageBox.question(self, "Arkiver medarbejder", f"Vil du arkivere {medarbejder.navn}?",)

        if svar == QMessageBox.Yes:

            data_manager.arkiver_medarbejder(medarbejder)

            self.medarbejdere_liste_arkiv.append(medarbejder)
            self.medarbejdere_liste.remove(medarbejder)

            self.opdater_tabel()
        
            

            

