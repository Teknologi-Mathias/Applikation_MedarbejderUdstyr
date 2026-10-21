"""Hovedvinduet: sidebar, sider og alle handlinger på medarbejdere."""
from datetime import date

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import (
    APP_BESKRIVELSE,
    APP_NAVN,
    APP_SLOGAN,
    VERSION,
    data_manager,
    session,
    datasikkerhed,
    indstillinger,
    skabeloner as sk,
)
from app.data_manager import DataFejl
from app.historik import registrer_aendringer
from app.medarbejder import Medarbejder
from app.ui.bruger_side import BrugerSide
from app.ui.dashboard_side import DashboardSide
from app.ui.data_side import DataSide
from app.ui.hjaelpere import lav_app_ikon, lav_knap, vis_dato
from app.ui.login_dialog import LoginDialog
from app.ui.medarbejder_dialog import MedarbejderDialog
from app.ui.medarbejder_side import MedarbejderSide
from app.ui.notifikationer import Notifikationer
from app.ui.rykker_dialog import RykkerDialog
from app.ui.sag_dialog import SagDialog
from app.ui.skabelon_side import SkabelonSide


class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder

    SIDE_DASHBOARD = 0
    SIDE_HOVED = 1
    SIDE_ARKIV = 2
    SIDE_SKABELONER = 3
    SIDE_DATA = 4
    SIDE_BRUGERE = 5

    # Sider kun administratorer kan se.
    ADMIN_SIDER = (SIDE_DATA, SIDE_BRUGERE)

    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAVN)
        self.setWindowIcon(lav_app_ikon())
        self.resize(1320, 860)
        self.setMinimumSize(1020, 700)

        self.notifikationer = Notifikationer(lav_app_ikon(), self)
        self.notifikationer.vis_vindue.connect(self.vis_fra_baggrund)
        self.notifikationer.afslut.connect(self.afslut)
        self._afslutter = False
        self._baggrund_forklaret = False
        self._backup_fejl_vist = False
        # Med ikon ved uret lukkes programmet kun via "Afslut".
        QApplication.instance().setQuitOnLastWindowClosed(
            not self.notifikationer.tilgaengelig
        )

        self.medarbejdere_liste = []
        self.medarbejdere_liste_arkiv = []
        self._signatur = None
        # Kan kaste DataFejl; main.py viser fejlen pænt.
        self._laes_data()
        self._daglig_backup()

        self._opbyg_gui()

        self.opdaterings_timer = QTimer(self)
        self.opdaterings_timer.setInterval(self.OPDATERINGS_INTERVAL)
        self.opdaterings_timer.timeout.connect(self._minut_tik)
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

    def _hent_skabeloner(self, vis_fejl=True):
        try:
            return sk.hent_alle()
        except DataFejl as fejl:
            if vis_fejl:
                QMessageBox.warning(self, "Skabeloner", str(fejl))
            return None

    def _ansvarlige(self):
        alle = self._hent_skabeloner(vis_fejl=False) or {}
        return sk.kendte_ansvarlige(alle, self.medarbejdere_liste)

    def _daglig_backup(self):
        """Tager dagens backup (én gang pr. dag). Fejl vises én gang pr. kørsel."""
        try:
            datasikkerhed.daglig_backup(indstillinger.hent())
        except (DataFejl, OSError) as fejl:
            if not self._backup_fejl_vist:
                self._backup_fejl_vist = True
                QMessageBox.warning(
                    self, "Sikkerhedskopi",
                    f"Dagens automatiske backup kunne ikke tages:\n{fejl}\n\n"
                    "Se Data & sikkerhed.",
                )

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
        self.skabelon_side = SkabelonSide(
            lambda: self.medarbejdere_liste, self.notifikationer.vis_besked
        )
        self.data_side = DataSide(lambda: self.medarbejdere_liste_arkiv)
        self.data_side.data_aendret.connect(self._data_gendannet)
        self.bruger_side = BrugerSide()

        self.sider = QStackedWidget()
        self.sider.addWidget(self.dashboard)        # SIDE_DASHBOARD
        self.sider.addWidget(self.hovedside)        # SIDE_HOVED
        self.sider.addWidget(self.arkivside)        # SIDE_ARKIV
        self.sider.addWidget(self.skabelon_side)    # SIDE_SKABELONER
        self.sider.addWidget(self.data_side)        # SIDE_DATA
        self.sider.addWidget(self.bruger_side)      # SIDE_BRUGERE

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

        titel = QLabel(APP_NAVN)
        titel.setObjectName("appTitle")
        titel.setToolTip(APP_BESKRIVELSE)
        slogan = QLabel(APP_SLOGAN)
        slogan.setObjectName("appSlogan")
        slogan.setWordWrap(True)
        slogan.setToolTip(APP_BESKRIVELSE)
        layout.addWidget(titel)
        layout.addWidget(slogan)
        layout.addSpacing(12)

        self.nav_gruppe = QButtonGroup(self)
        self.nav_gruppe.setExclusive(True)
        self.nav_knapper = {}

        for sektion, punkter in (
            ("MEDARBEJDERAFVIKLING", (
                ("Dashboard", self.SIDE_DASHBOARD),
                ("Hovedside", self.SIDE_HOVED),
                ("Arkiv", self.SIDE_ARKIV),
            )),
            ("SYSTEM", (
                ("Skabeloner", self.SIDE_SKABELONER),
                ("Data & sikkerhed", self.SIDE_DATA),
                ("Brugerkartotek", self.SIDE_BRUGERE),
            )),
        ):
            sektion_label = QLabel(sektion)
            sektion_label.setObjectName("navSektion")
            layout.addWidget(sektion_label)
            for tekst, index in punkter:
                knap = QPushButton(tekst)
                knap.setProperty("nav", True)
                knap.setCheckable(True)
                knap.setCursor(Qt.CursorShape.PointingHandCursor)
                knap.clicked.connect(lambda _=False, i=index: self.sider.setCurrentIndex(i))
                self.nav_gruppe.addButton(knap, index)
                self.nav_knapper[index] = knap
                layout.addWidget(knap)

        self.nav_knapper[self.SIDE_DASHBOARD].setChecked(True)

        layout.addStretch()

        self.sidst_opdateret_label = QLabel("")
        self.sidst_opdateret_label.setObjectName("sidebarFod")
        version_label = QLabel(f"{VERSION} · opdaterer hvert minut")
        version_label.setObjectName("sidebarFod")
        skaber_label = QLabel("© MASAN")
        skaber_label.setObjectName("sidebarFod")

        bruger_raekke = QHBoxLayout()
        self.bruger_label = QLabel("")
        self.bruger_label.setObjectName("sidebarBruger")
        self.bruger_label.setWordWrap(True)
        log_ud = lav_knap("Log ud")
        log_ud.setStyleSheet("padding: 5px 12px; font-size: 12px;")
        log_ud.clicked.connect(self.log_ud)
        bruger_raekke.addWidget(self.bruger_label, 1)
        bruger_raekke.addWidget(log_ud)
        layout.addLayout(bruger_raekke)
        layout.addSpacing(8)
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
            "Rediger", tooltip="Navn, e-mail, sidste arbejdsdag og manuel status"
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
            [self._opbyg_handling_knap()],
        )
        side.tabel.doubleClicked.connect(lambda _index: self.aabn_valgt_sag())
        return side

    def _opbyg_handling_knap(self):
        """Dropdown "Handling" med handlinger på den valgte medarbejder."""
        menu = QMenu(self)
        self.handling_opret_rykker = menu.addAction("Opret rykker…", self.opret_rykker)
        self.handling_marker_sendt = menu.addAction(
            "Marker rykker som sendt…", self.marker_rykker_sendt
        )
        self.handling_returlabel = menu.addAction(
            "Registrér returlabel som sendt…", self.registrer_returlabel
        )
        self.handling_notat = menu.addAction(
            "Tilføj notat til tidslinjen…", self.tilfoej_notat
        )
        menu.addSeparator()
        self.handling_tidslinje = menu.addAction("Vis tidslinje", self.vis_tidslinje)
        menu.aboutToShow.connect(self._opdater_handlingsmenu)

        knap = QToolButton()
        knap.setText("Handling")
        knap.setProperty("variant", "menu")
        knap.setCursor(Qt.CursorShape.PointingHandCursor)
        knap.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        knap.setMenu(menu)
        knap.setToolTip("Handlinger på den valgte medarbejder")
        return knap

    def _opbyg_arkivside(self):
        goer_aktiv_knap = lav_knap("Gør medarbejder aktiv")
        self.slet_knap = slet_knap = lav_knap("Slet permanent", "danger")

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
        if index in self.nav_knapper:
            self.nav_knapper[index].setChecked(True)
        if index == self.SIDE_DASHBOARD:
            self.dashboard.opdater(self.medarbejdere_liste, self.medarbejdere_liste_arkiv)
        elif index == self.SIDE_SKABELONER:
            self.skabelon_side.opdater()
        elif index == self.SIDE_BRUGERE:
            self.bruger_side.opdater()
        elif index == self.SIDE_DATA:
            self.data_side.opdater()

    def opdater_alle_visninger(self):
        self.synkroniser()
        self.hovedside.vis(self.medarbejdere_liste)
        self.arkivside.vis(self.medarbejdere_liste_arkiv)
        self.dashboard.opdater(self.medarbejdere_liste, self.medarbejdere_liste_arkiv)
        alle = self._hent_skabeloner(vis_fejl=False)
        if alle:
            self.notifikationer.tjek(
                self.medarbejdere_liste, sk.aktive(alle, sk.PAAMINDELSE)
            )
        self.sidst_opdateret_label.setText(
            f"Sidst opdateret {QTime.currentTime().toString('HH:mm')}"
        )

    def _minut_tik(self):
        self._daglig_backup()   # programmet kan køre i flere døgn i baggrunden
        self.opdater_alle_visninger()

    def _data_gendannet(self):
        try:
            self._laes_data()
        except DataFejl as fejl:
            QMessageBox.critical(self, "Datafejl", str(fejl))
            return
        self.opdater_alle_visninger()

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

    def _gem_aendret(self, loennr, ny, registrer=True):
        """Erstatter medarbejderen med dette lønnr. med den ændrede kopi og gemmer.

        registrer=True skriver forskellene (opgaver, stamdata, status) i
        tidslinjen. Data kan være ændret af en kollega, mens en dialog var
        åben, så der synkroniseres og tjekkes igen først.
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

        if registrer:
            registrer_aendringer(gammel, ny)
        index = self.medarbejdere_liste.index(gammel)
        self.medarbejdere_liste[index] = ny
        self._gem_aktive()
        self.opdater_alle_visninger()
        return True

    ### ----- handlinger: hovedside ------------------------------------------

    def opret_medarbejder(self):
        self.synkroniser()
        alle = self._hent_skabeloner()
        if alle is None:
            return
        dialog = MedarbejderDialog(
            self,
            optagede_loennumre=self._alle_loennumre(),
            skabeloner=sk.aktive(alle, sk.SAG),
        )
        if not dialog.exec():
            return

        data = dialog.hent_data()

        # Tjek igen: en kollega kan have oprettet samme lønnr. imens.
        self.synkroniser()
        if self._loennr_optaget(data["loennr"]):
            return

        skabelon = data["skabelon"]
        medarbejder = Medarbejder(
            data["loennr"],
            data["navn"],
            data["fratraedelsesdato"],
            data["kommentar"],
            sk.opret_opgaver(skabelon, data["fratraedelsesdato"]) if skabelon else [],
            data["status_manuel"],
            data["status_begrundelse"],
            data["email"],
            data["tracking_link"],
        )
        medarbejder.historik.tilfoej(
            "Afviklingssag oprettet",
            f"Skabelon: {skabelon['navn']}" if skabelon else "Uden skabelon",
        )
        if medarbejder.status_manuel:
            medarbejder.historik.tilfoej(
                f"Status låst manuelt: {medarbejder.status_manuel}",
                medarbejder.status_begrundelse,
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
        ny.email = data["email"]
        ny.tracking_link = data["tracking_link"]
        ny.status_manuel = data["status_manuel"]
        ny.status_begrundelse = data["status_begrundelse"]
        self._gem_aendret(loennr, ny)

    def aabn_valgt_sag(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is not None:
            self.aabn_sag(medarbejder.loennr)

    def aabn_sag(self, loennr, opgave_id="", start_fane=SagDialog.FANE_OPGAVER):
        """Åbner afviklingssagen; opgave_id fremhæver en bestemt opgave."""
        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self.opdater_alle_visninger()
            return
        dialog = SagDialog(
            self, medarbejder, self._ansvarlige(),
            fokus_opgave_id=opgave_id or None, start_fane=start_fane,
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

        ny = medarbejder.kopi()
        ny.arkiveret = date.today().isoformat()
        ny.historik.tilfoej("Sag arkiveret", f"Status ved arkivering: {ny.status}")
        data_manager.arkiver_medarbejder(ny)
        self._laes_data()
        self.opdater_alle_visninger()

    ### ----- handlinger: Handling-menuen ------------------------------------

    def _opdater_handlingsmenu(self):
        """Slår menupunkter til/fra efter den valgte medarbejder."""
        loennr = self.hovedside.valgt_loennr()
        m = self._find(self.medarbejdere_liste, loennr) if loennr else None
        for handling in (
            self.handling_opret_rykker, self.handling_returlabel,
            self.handling_notat, self.handling_tidslinje,
        ):
            handling.setEnabled(m is not None)
        self.handling_marker_sendt.setEnabled(bool(m and m.usendte_rykkere()))

    def opret_rykker(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        alle = self._hent_skabeloner()
        if alle is None:
            return
        dialog = RykkerDialog(
            self, medarbejder, sk.aktive(alle, sk.MAIL),
            sk.relevant_mailskabelon(alle, medarbejder),
        )
        if not dialog.exec():
            return

        rykker = dialog.rykker
        ny = medarbejder.kopi()
        ny.rykkere.append(rykker)
        ny.historik.tilfoej(
            f"{rykker.kategori} oprettet som kladde",
            f"Skabelon: {rykker.skabelon_navn} · Frist: {vis_dato(rykker.frist)} "
            f"· Til: {ny.email}",
            rykker.id,
        )
        self._gem_aendret(medarbejder.loennr, ny, registrer=False)

    def marker_rykker_sendt(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        usendte = medarbejder.usendte_rykkere()
        if not usendte:
            QMessageBox.information(
                self, "Ingen kladder", "Der er ingen rykkere, som venter på at blive sendt."
            )
            return

        valg = [
            f"{r.kategori} – oprettet {vis_dato(r.oprettet[:10])} – {r.emne}"
            for r in usendte
        ]
        tekst, ok = QInputDialog.getItem(
            self, "Marker rykker som sendt",
            "Hvilken rykker er sendt?\nMarker den først, når mailen faktisk er afsendt.",
            valg, 0, False,
        )
        if not ok:
            return
        rykker_id = usendte[valg.index(tekst)].id

        ny = medarbejder.kopi()
        rykker = ny.find_rykker(rykker_id)
        rykker.marker_sendt()
        ny.historik.tilfoej(
            f"{rykker.kategori} markeret som sendt", f"Emne: {rykker.emne}", rykker.id
        )
        self._gem_aendret(medarbejder.loennr, ny, registrer=False)

    def registrer_returlabel(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        link, ok = QInputDialog.getText(
            self, "Returlabel sendt",
            "Tracking-link til returpakken (valgfrit):",
            QLineEdit.EchoMode.Normal, medarbejder.tracking_link,
        )
        if not ok:
            return
        ny = medarbejder.kopi()
        ny.tracking_link = link.strip()
        ny.historik.tilfoej("Returlabel registreret som sendt", ny.tracking_link)
        self._gem_aendret(medarbejder.loennr, ny, registrer=False)

    def tilfoej_notat(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is None:
            return
        tekst, ok = QInputDialog.getMultiLineText(
            self, "Tilføj notat",
            f"Notat til {medarbejder.navn}s tidslinje.\n"
            "Notatet kan ikke ændres, når det er gemt.",
        )
        if not ok or not tekst.strip():
            return
        ny = medarbejder.kopi()
        ny.historik.tilfoej("Notat", tekst.strip())
        self._gem_aendret(medarbejder.loennr, ny, registrer=False)

    def vis_tidslinje(self):
        medarbejder = self._hent_valgt(self.hovedside)
        if medarbejder is not None:
            self.aabn_sag(medarbejder.loennr, start_fane=SagDialog.FANE_TIDSLINJE)

    ### ----- handlinger: arkiv ----------------------------------------------

    def aktiver_medarbejder(self):
        medarbejder = self._hent_valgt(self.arkivside, arkiv=True)
        if medarbejder is None:
            return
        if not self._bekraeft(
            "Aktivér medarbejder", f"Vil du gøre {medarbejder.navn} aktiv igen?"
        ):
            return

        ny = medarbejder.kopi()
        ny.arkiveret = ""
        ny.historik.tilfoej("Sag gjort aktiv igen")
        data_manager.aktiver_medarbejder(ny)
        self._laes_data()
        self.opdater_alle_visninger()

    def slet_medarbejder(self):
        if not session.er_admin():
            return
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

    ### ----- log på og roller ---------------------------------------------

    def anvend_rolle(self):
        """Viser/skjuler det, der kræver administratorrettigheder."""
        bruger = session.bruger() or {}
        admin = session.er_admin()
        self.bruger_label.setText(
            f"{bruger.get('navn') or bruger.get('brugernavn', '')}\n{bruger.get('rolle', '')}"
        )
        for index in self.ADMIN_SIDER:
            self.nav_knapper[index].setVisible(admin)
        self.slet_knap.setVisible(admin)
        self.skabelon_side.saet_redigerbar(admin)
        if not admin and self.sider.currentIndex() in self.ADMIN_SIDER:
            self.sider.setCurrentIndex(self.SIDE_DASHBOARD)

    def log_ud(self):
        session.log_ud()
        self.hide()
        self.log_paa()

    def log_paa(self):
        """Viser log på-skærmen. Annulleres den, afsluttes programmet."""
        dialog = LoginDialog()
        if not dialog.exec():
            self.afslut()
            return
        session.log_ind(dialog.bruger)
        self.anvend_rolle()
        self.sider.setCurrentIndex(self.SIDE_DASHBOARD)
        self.showNormal()
        self.raise_()
        self.activateWindow()

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
                f"{APP_NAVN} kører i baggrunden",
                "Du får påmindelser som Windows-notifikationer. Højreklik på "
                "ikonet ved uret og vælg Afslut for at lukke helt.",
            )

    def vis_fra_baggrund(self):
        if session.bruger() is None:
            return   # log på-skærmen er åben
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.sider.setCurrentIndex(self.SIDE_DASHBOARD)

    def afslut(self):
        self._afslutter = True
        self.notifikationer.tray.hide()
        QApplication.quit()
