"""Hovedvinduet: sidebar, sider og alle handlinger på medarbejdere."""
from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
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

from app import VERSION, data_manager
from app.data_manager import DataFejl
from app.medarbejder import Medarbejder
from app.ui.dashboard_side import DashboardSide
from app.ui.hjaelpere import lav_knap
from app.ui.medarbejder_dialog import MedarbejderDialog
from app.ui.medarbejder_side import MedarbejderSide


class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder

    SIDE_DASHBOARD = 0
    SIDE_HOVED = 1
    SIDE_ARKIV = 2

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Medarbejderafvikling")
        self.resize(1320, 860)
        self.setMinimumSize(1020, 700)

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
        rediger_knap = lav_knap(
            "Rediger", tooltip="Rediger oplysninger og udstyr (eller dobbeltklik)"
        )
        status_knap = lav_knap("Skift status", tooltip="Går til næste status i rækken")
        arkiver_knap = lav_knap("Arkiver", "danger")

        opret_knap.clicked.connect(self.opret_medarbejder)
        rediger_knap.clicked.connect(self.rediger_medarbejder)
        status_knap.clicked.connect(self.skift_status)
        arkiver_knap.clicked.connect(self.arkiver_medarbejder)

        side = MedarbejderSide(
            "Medarbejdere",
            "Aktive medarbejdere og status på udstyrsafleveringen.",
            [opret_knap, rediger_knap, status_knap, arkiver_knap],
        )
        side.tabel.doubleClicked.connect(lambda _index: self.rediger_medarbejder())
        return side

    def _opbyg_arkivside(self):
        goer_aktiv_knap = lav_knap("Gør medarbejder aktiv")
        slet_knap = lav_knap("Slet permanent", "danger")

        goer_aktiv_knap.clicked.connect(self.aktiver_medarbejder)
        slet_knap.clicked.connect(self.slet_medarbejder)

        return MedarbejderSide(
            "Arkiv",
            "Afsluttede medarbejdere. Kan gøres aktive igen eller slettes.",
            [goer_aktiv_knap, slet_knap],
        )

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

    def opret_medarbejder(self):
        self.synkroniser()
        dialog = MedarbejderDialog(self, optagede_loennumre=self._alle_loennumre())
        if not dialog.exec():
            return

        data = dialog.hent_data()

        # Tjek igen: en kollega kan have oprettet samme lønnr. imens.
        self.synkroniser()
        if self._loennr_optaget(data["loennr"]):
            return

        self.medarbejdere_liste.append(Medarbejder.fra_dict(data))
        self._gem_aktive()
        self.opdater_alle_visninger()

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

        # Data kan være ændret af en kollega, mens dialogen var åben.
        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self.opdater_alle_visninger()
            QMessageBox.warning(
                self,
                "Medarbejder ikke fundet",
                "Medarbejderen findes ikke længere (er den ændret af en anden?).",
            )
            return
        if self._loennr_optaget(data["loennr"], undtagen=loennr):
            return

        index = self.medarbejdere_liste.index(medarbejder)
        self.medarbejdere_liste[index] = Medarbejder.fra_dict(data)
        self._gem_aktive()
        self.opdater_alle_visninger()

    def skift_status(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return

        statuser = list(Medarbejder.STATUSER)
        nuvaerende = statuser.index(medarbejder.status)
        medarbejder.status = statuser[(nuvaerende + 1) % len(statuser)]

        self._gem_aktive()
        self.opdater_alle_visninger()

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
