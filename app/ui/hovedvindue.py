"""Hovedvinduet: sidebar, sider og alle handlinger på medarbejdere."""
from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import VERSION, data_manager, skabeloner
from app.data_manager import DataFejl
from app.medarbejder import Medarbejder
from app.ui.dashboard_side import DashboardSide
from app.ui.hjaelpere import lav_app_ikon, lav_knap
from app.ui.medarbejder_dialog import MedarbejderDialog
from app.ui.medarbejder_side import MedarbejderSide
from app.ui.notifikationer import Notifikationer
from app.ui.sag_dialog import SagDialog


class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder

    SIDE_DASHBOARD = 0
    SIDE_HOVED = 1
    SIDE_ARKIV = 2

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Medarbejderafvikling")
        self.setWindowIcon(lav_app_ikon())
        self.resize(1320, 860)
        self.setMinimumSize(1020, 700)

        self.notifikationer = Notifikationer(lav_app_ikon(), self)
        self.notifikationer.vis_vindue.connect(self.vis_fra_baggrund)
        self.notifikationer.afslut.connect(self.afslut)
        self._afslutter = False
        self._baggrund_forklaret = False
        # Med ikon ved uret lukkes programmet kun via "Afslut".
        QApplication.instance().setQuitOnLastWindowClosed(
            not self.notifikationer.tilgaengelig
        )

        self.medarbejdere_liste = []
        self.medarbejdere_liste_arkiv = []
        self._signatur = None
        # Kan kaste DataFejl; main.py viser fejlen pænt.
        self._laes_data()

        self._opbyg_gui()

        self.opdaterings_timer = QTimer(self)
        self.opdaterings_timer.setInterval(self.OPDATERINGS_INTERVAL)
        self.opdaterings_timer.timeout.connect(self.opdater_alle_visninger)
        self.opdaterings_timer.start()

    ### ----- data -----------------------------------------------------------

    def _laes_data(self):
        self.medarbejdere_liste = data_manager.hent_medarbejdere()
        self.medarbejdere_liste_arkiv = data_manager.hent_arkiverede_medarbejdere()
        self._signatur = data_manager.fil_signatur()

    def synkroniser(self):
        """Genindlæser data, hvis filerne er ændret udefra (fx af en kollega)."""
        if data_manager.fil_signatur() == self._signatur:
            return False
        try:
            self._laes_data()
        except DataFejl:
            return False
        return True

    def _gem_aktive(self):
        data_manager.gem_medarbejdere(self.medarbejdere_liste)
        self._signatur = data_manager.fil_signatur()

    @staticmethod
    def _find(liste, loennr):
        for medarbejder in liste:
            if str(medarbejder.loennr) == str(loennr):
                return medarbejder
        return None

    def _alle_loennumre(self, undtagen=None):
        return {
            str(m.loennr)
            for m in self.medarbejdere_liste + self.medarbejdere_liste_arkiv
            if str(m.loennr) != str(undtagen)
        }

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_gui(self):
        central = QWidget()
        central.setObjectName("pageRoot")
        self.setCentralWidget(central)

        rod = QHBoxLayout(central)
        rod.setContentsMargins(0, 0, 0, 0)
        rod.setSpacing(0)

        self.dashboard = DashboardSide()
        self.dashboard.aabn_sag.connect(self.aabn_sag)
        self.hovedside = self._opbyg_hovedside()
        self.arkivside = self._opbyg_arkivside()

        self.sider = QStackedWidget()
        self.sider.addWidget(self.dashboard)    # SIDE_DASHBOARD
        self.sider.addWidget(self.hovedside)    # SIDE_HOVED
        self.sider.addWidget(self.arkivside)    # SIDE_ARKIV

        rod.addWidget(self._opbyg_sidebar())
        rod.addWidget(self.sider, 1)

        self.sider.currentChanged.connect(self._fane_skiftet)
        self.opdater_alle_visninger()
        self.sider.setCurrentIndex(self.SIDE_DASHBOARD)

    def _opbyg_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 26, 18, 18)
        layout.setSpacing(6)

        titel = QLabel("Medarbejder-\nafvikling")
        titel.setObjectName("appTitle")
        under = QLabel("Udstyr ved fratrædelse")
        under.setObjectName("appSub")
        layout.addWidget(titel)
        layout.addWidget(under)
        layout.addSpacing(26)

        self.nav_gruppe = QButtonGroup(self)
        self.nav_gruppe.setExclusive(True)
        self.nav_knapper = []

        for tekst, index in (
            ("Dashboard", self.SIDE_DASHBOARD),
            ("Hovedside", self.SIDE_HOVED),
            ("Arkiv", self.SIDE_ARKIV),
        ):
            knap = QPushButton(tekst)
            knap.setProperty("nav", True)
            knap.setCheckable(True)
            knap.setCursor(Qt.CursorShape.PointingHandCursor)
            knap.clicked.connect(lambda _=False, i=index: self.sider.setCurrentIndex(i))
            self.nav_gruppe.addButton(knap, index)
            self.nav_knapper.append(knap)
            layout.addWidget(knap)

        self.nav_knapper[self.SIDE_DASHBOARD].setChecked(True)

        layout.addStretch()

        self.sidst_opdateret_label = QLabel("")
        self.sidst_opdateret_label.setObjectName("sidebarFod")
        version_label = QLabel(f"{VERSION} · opdaterer hvert minut")
        version_label.setObjectName("sidebarFod")
        skaber_label = QLabel("© MASAN")
        skaber_label.setObjectName("sidebarFod")
        layout.addWidget(self.sidst_opdateret_label)
        layout.addWidget(version_label)
        layout.addWidget(skaber_label)

        return sidebar

    def _opbyg_hovedside(self):
        opret_knap = lav_knap("+ Opret medarbejder", "primary")
        sag_knap = lav_knap(
            "Åbn sag", tooltip="Opgaver, ansvarlige og frister (eller dobbeltklik)"
        )
        rediger_knap = lav_knap(
            "Rediger", tooltip="Navn, lønnr., sidste arbejdsdag og manuel status"
        )
        arkiver_knap = lav_knap("Arkiver", "danger")

        opret_knap.clicked.connect(self.opret_medarbejder)
        sag_knap.clicked.connect(self.aabn_valgt_sag)
        rediger_knap.clicked.connect(self.rediger_medarbejder)
        arkiver_knap.clicked.connect(self.arkiver_medarbejder)

        side = MedarbejderSide(
            "Medarbejdere",
            "Aktive afviklingssager. Status beregnes ud fra sagens opgaver.",
            [opret_knap, sag_knap, rediger_knap, arkiver_knap],
        )
        side.tabel.doubleClicked.connect(lambda _index: self.aabn_valgt_sag())
        return side

    def _opbyg_arkivside(self):
        goer_aktiv_knap = lav_knap("Gør medarbejder aktiv")
        slet_knap = lav_knap("Slet permanent", "danger")

        goer_aktiv_knap.clicked.connect(self.aktiver_medarbejder)
        slet_knap.clicked.connect(self.slet_medarbejder)

        side = MedarbejderSide(
            "Arkiv",
            "Afsluttede sager. Dobbeltklik for at se sagen. "
            "Kan gøres aktive igen eller slettes.",
            [goer_aktiv_knap, slet_knap],
        )
        side.tabel.doubleClicked.connect(lambda _index: self.vis_arkiveret_sag())
        return side

    ### ----- visning --------------------------------------------------------

    def _fane_skiftet(self, index):
        if 0 <= index < len(self.nav_knapper):
            self.nav_knapper[index].setChecked(True)
        if index == self.SIDE_DASHBOARD:
            self.dashboard.opdater(self.medarbejdere_liste, self.medarbejdere_liste_arkiv)

    def opdater_alle_visninger(self):
        self.synkroniser()
        self.hovedside.vis(self.medarbejdere_liste)
        self.arkivside.vis(self.medarbejdere_liste_arkiv)
        self.dashboard.opdater(self.medarbejdere_liste, self.medarbejdere_liste_arkiv)
        self.notifikationer.tjek(self.medarbejdere_liste)
        self.sidst_opdateret_label.setText(
            f"Sidst opdateret {QTime.currentTime().toString('HH:mm')}"
        )

    ### ----- fælles for handlinger ------------------------------------------

    def _hent_valgt(self, side, arkiv=False):
        """Finder den markerede medarbejder på siden, med friske data.

        Returnerer None (og har vist en besked), hvis intet kan bruges.
        """
        loennr = side.valgt_loennr()
        if loennr is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")
            return None

        self.synkroniser()
        # Listen slås først op nu, da synkroniseringen kan have udskiftet den.
        liste = self.medarbejdere_liste_arkiv if arkiv else self.medarbejdere_liste
        medarbejder = self._find(liste, loennr)
        if medarbejder is None:
            QMessageBox.warning(
                self,
                "Medarbejder ikke fundet",
                "Medarbejderen findes ikke længere (er den ændret af en anden?). "
                "Visningen er opdateret.",
            )
            self.opdater_alle_visninger()
        return medarbejder

    def _bekraeft(self, titel, tekst, advarsel=False):
        knapper = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        vis = QMessageBox.warning if advarsel else QMessageBox.question
        svar = vis(self, titel, tekst, knapper, QMessageBox.StandardButton.No)
        return svar == QMessageBox.StandardButton.Yes

    def _loennr_optaget(self, loennr, undtagen=None):
        if loennr not in self._alle_loennumre(undtagen=undtagen):
            return False
        QMessageBox.warning(
            self,
            "Lønnr. findes allerede",
            "Der findes allerede en medarbejder med dette lønnr.",
        )
        return True

    ### ----- handlinger: hovedside ------------------------------------------

    def _hent_skabeloner(self):
        try:
            return skabeloner.hent_skabeloner()
        except DataFejl as fejl:
            QMessageBox.warning(self, "Skabeloner", str(fejl))
            return None

    def _ansvarlige(self):
        try:
            alle_skabeloner = skabeloner.hent_skabeloner()
        except DataFejl:
            alle_skabeloner = []
        return skabeloner.kendte_ansvarlige(alle_skabeloner, self.medarbejdere_liste)

    def _gem_aendret(self, loennr, ny):
        """Erstatter medarbejderen med dette lønnr. med den ændrede kopi og gemmer.

        Data kan være ændret af en kollega, mens en dialog var åben, så der
        synkroniseres og tjekkes igen først.
        """
        self.synkroniser()
        gammel = self._find(self.medarbejdere_liste, loennr)
        if gammel is None:
            self.opdater_alle_visninger()
            QMessageBox.warning(
                self,
                "Medarbejder ikke fundet",
                "Medarbejderen findes ikke længere (er den ændret af en anden?).",
            )
            return False
        if self._loennr_optaget(ny.loennr, undtagen=loennr):
            return False

        index = self.medarbejdere_liste.index(gammel)
        self.medarbejdere_liste[index] = ny
        self._gem_aktive()
        self.opdater_alle_visninger()
        return True

    def opret_medarbejder(self):
        self.synkroniser()
        alle_skabeloner = self._hent_skabeloner()
        if alle_skabeloner is None:
            return
        dialog = MedarbejderDialog(
            self, optagede_loennumre=self._alle_loennumre(), skabeloner=alle_skabeloner
        )
        if not dialog.exec():
            return

        data = dialog.hent_data()

        # Tjek igen: en kollega kan have oprettet samme lønnr. imens.
        self.synkroniser()
        if self._loennr_optaget(data["loennr"]):
            return

        opgaver = (
            skabeloner.opret_opgaver(data["skabelon"], data["fratraedelsesdato"])
            if data["skabelon"] else []
        )
        medarbejder = Medarbejder(
            data["loennr"],
            data["navn"],
            data["fratraedelsesdato"],
            data["kommentar"],
            opgaver,
            data["status_manuel"],
            data["status_begrundelse"],
        )
        self.medarbejdere_liste.append(medarbejder)
        self._gem_aktive()
        self.opdater_alle_visninger()
        # Vis den nye sag med det samme, så opgaverne kan gennemgås.
        self.aabn_sag(medarbejder.loennr)

    def rediger_medarbejder(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        loennr = medarbejder.loennr

        dialog = MedarbejderDialog(
            self, medarbejder, optagede_loennumre=self._alle_loennumre(undtagen=loennr)
        )
        if not dialog.exec():
            return

        data = dialog.hent_data()
        ny = medarbejder.kopi()
        ny.loennr = data["loennr"]
        ny.navn = data["navn"]
        ny.flyt_fratraedelse(data["fratraedelsesdato"])
        ny.kommentar = data["kommentar"]
        ny.status_manuel = data["status_manuel"]
        ny.status_begrundelse = data["status_begrundelse"]
        self._gem_aendret(loennr, ny)

    def aabn_valgt_sag(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is not None:
            self.aabn_sag(medarbejder.loennr)

    def aabn_sag(self, loennr, opgave_id=""):
        """Åbner afviklingssagen; opgave_id fremhæver en bestemt opgave."""
        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self.opdater_alle_visninger()
            return
        dialog = SagDialog(
            self, medarbejder, self._ansvarlige(), fokus_opgave_id=opgave_id or None
        )
        if dialog.exec():
            self._gem_aendret(loennr, dialog.medarbejder)

    def vis_arkiveret_sag(self):
        medarbejder = self._hent_valgt(self.arkivside, arkiv=True)
        if medarbejder is not None:
            SagDialog(self, medarbejder, kun_laesning=True).exec()

    def arkiver_medarbejder(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        if not self._bekraeft(
            "Arkiver medarbejder", f"Vil du arkivere {medarbejder.navn}?"
        ):
            return

        data_manager.arkiver_medarbejder(medarbejder)
        self._laes_data()
        self.opdater_alle_visninger()

    ### ----- handlinger: arkiv ----------------------------------------------

    def aktiver_medarbejder(self):
        medarbejder = self._hent_valgt(self.arkivside, arkiv=True)
        if medarbejder is None:
            return
        if not self._bekraeft(
            "Aktivér medarbejder", f"Vil du gøre {medarbejder.navn} aktiv igen?"
        ):
            return

        data_manager.aktiver_medarbejder(medarbejder)
        self._laes_data()
        self.opdater_alle_visninger()

    def slet_medarbejder(self):
        medarbejder = self._hent_valgt(self.arkivside, arkiv=True)
        if medarbejder is None:
            return
        if not self._bekraeft(
            "Slet medarbejder permanent",
            f"Vil du slette {medarbejder.navn} (lønnr. {medarbejder.loennr}) "
            "permanent fra arkivet?\n\nHandlingen kan ikke fortrydes.",
            advarsel=True,
        ):
            return

        data_manager.slet_fra_arkiv(medarbejder)
        self._laes_data()
        self.opdater_alle_visninger()

    ### ----- baggrund og lukning --------------------------------------------

    def closeEvent(self, event):
        """Luk-knappen skjuler vinduet; programmet kører videre ved uret."""
        if self._afslutter or not self.notifikationer.tilgaengelig:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._baggrund_forklaret:
            self._baggrund_forklaret = True
            self.notifikationer.vis_besked(
                "Medarbejderafvikling kører i baggrunden",
                "Du får besked om forsinkede opgaver. Højreklik på ikonet ved "
                "uret og vælg Afslut for at lukke helt.",
            )

    def vis_fra_baggrund(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.sider.setCurrentIndex(self.SIDE_DASHBOARD)

    def afslut(self):
        self._afslutter = True
        self.notifikationer.tray.hide()
        QApplication.quit()
