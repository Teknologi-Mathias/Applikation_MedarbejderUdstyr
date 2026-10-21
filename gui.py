from PySide6.QtCore import QDate, QTime, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import data_manager
from data_manager import DataFejl
from medarbejder import Medarbejder
from theme import FARVER, STATUS_STIL
from widgets import (
    LOENNR_ROLE,
    SORT_ROLE,
    BarChart,
    DonutChart,
    SortItem,
    StatusDelegate,
)

VERSION = "V0.5"

UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
UGEDAGE_KORT = ["ma", "ti", "on", "to", "fr", "lø", "sø"]
MAANEDER = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def dansk_dato(dato):
    return (
        f"{UGEDAGE[dato.dayOfWeek() - 1]} den {dato.day()}. "
        f"{MAANEDER[dato.month() - 1]} {dato.year()}"
    )


def laes_dato(tekst):
    return QDate.fromString(str(tekst), "yyyy-MM-dd")


def lav_knap(tekst, variant=None, tooltip=None):
    knap = QPushButton(tekst)
    if variant:
        knap.setProperty("variant", variant)
    knap.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        knap.setToolTip(tooltip)
    return knap


def lav_kort(skygge=True):
    kort = QFrame()
    kort.setObjectName("card")
    if skygge:
        effekt = QGraphicsDropShadowEffect(kort)
        effekt.setBlurRadius(24)
        effekt.setOffset(0, 4)
        effekt.setColor(QColor(15, 23, 42, 22))
        kort.setGraphicsEffect(effekt)
    return kort


def lav_sidehoved(titel, undertitel):
    boks = QVBoxLayout()
    boks.setSpacing(2)
    titel_label = QLabel(titel)
    titel_label.setObjectName("pageTitle")
    under_label = QLabel(undertitel)
    under_label.setObjectName("pageSub")
    boks.addWidget(titel_label)
    boks.addWidget(under_label)
    return boks, under_label


def lav_raekke(titel, undertitel, badge, badge_bg, badge_tekst):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 9, 4, 9)
    layout.setSpacing(12)

    badge_label = QLabel(badge)
    badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge_label.setFixedWidth(78)
    badge_label.setStyleSheet(
        f"background: {badge_bg}; color: {badge_tekst}; border-radius: 10px;"
        "font-weight: 700; font-size: 12px; padding: 6px 0;"
    )

    tekst_layout = QVBoxLayout()
    tekst_layout.setSpacing(1)
    titel_label = QLabel(titel)
    titel_label.setStyleSheet("font-weight: 600; background: transparent;")
    under_label = QLabel(undertitel)
    under_label.setStyleSheet(
        f"color: {FARVER['muted']}; font-size: 12px; background: transparent;"
    )
    tekst_layout.addWidget(titel_label)
    tekst_layout.addWidget(under_label)

    layout.addWidget(badge_label)
    layout.addLayout(tekst_layout, 1)
    return widget


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class MedarbejderDialog(QDialog):
    def __init__(self, parent=None, medarbejder=None, optagede_loennumre=()):
        super().__init__(parent)

        self.optagede_loennumre = {str(x) for x in optagede_loennumre}

        self.setWindowTitle(
            "Opret medarbejder" if medarbejder is None else "Rediger medarbejder"
        )
        self.setMinimumWidth(460)

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
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("Lønnr.", self.loennr_input)
        form.addRow("Medarbejdernavn", self.navn_input)
        form.addRow("Fratrædelsesdato", self.dato_input)
        form.addRow("Status", self.status_input)
        form.addRow("Kommentar", self.kommentar_input)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        gem_knap = buttons.button(QDialogButtonBox.StandardButton.Save)
        gem_knap.setText("Gem")
        gem_knap.setProperty("variant", "primary")
        gem_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        annuller_knap = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        annuller_knap.setText("Annuller")
        annuller_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(self.fejl_label)
        layout.addWidget(buttons)

        if medarbejder is not None:
            self.loennr_input.setText(str(medarbejder.loennr))
            self.navn_input.setText(medarbejder.navn)
            self.kommentar_input.setText(str(medarbejder.kommentar))

            dato = laes_dato(medarbejder.fratraedelsesdato)
            if dato.isValid():
                self.dato_input.setDate(dato)

            status_index = self.status_input.findText(medarbejder.status)
            if status_index >= 0:
                self.status_input.setCurrentIndex(status_index)

    def accept(self):
        data = self.hent_data()
        if not data["loennr"] or not data["navn"]:
            self.fejl_label.setText("Lønnr. og medarbejdernavn skal udfyldes.")
            return
        if data["loennr"] in self.optagede_loennumre:
            self.fejl_label.setText(
                "Der findes allerede en medarbejder med dette lønnr. "
                "(aktiv eller arkiveret)."
            )
            return
        super().accept()

    def hent_data(self):
        return {
            "loennr": self.loennr_input.text().strip(),
            "navn": self.navn_input.text().strip(),
            "fratraedelsesdato": self.dato_input.date().toString("yyyy-MM-dd"),
            "status": self.status_input.currentText(),
            "kommentar": self.kommentar_input.text().strip(),
        }


# ---------------------------------------------------------------------------
# Hovedvindue
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder
    NOTIFIKATIONSDAGE = 14
    KOMMENDE_FRATRAEDELSESDAGE = 7
    DIAGRAM_DAGE = 14

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

        self.opbyg_gui()

        self.opdaterings_timer = QTimer(self)
        self.opdaterings_timer.setInterval(self.OPDATERINGS_INTERVAL)
        self.opdaterings_timer.timeout.connect(self.opdater_alle_visninger)
        self.opdaterings_timer.start()

    ### ----- data -----------------------------------------------------------

    def _laes_data(self):
        aktive = data_manager.hent_medarbejdere()
        arkiv = data_manager.hent_arkiverede_medarbejdere()
        self.medarbejdere_liste = aktive
        self.medarbejdere_liste_arkiv = arkiv
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

    def opbyg_gui(self):
        central = QWidget()
        central.setObjectName("pageRoot")
        self.setCentralWidget(central)

        rod = QHBoxLayout(central)
        rod.setContentsMargins(0, 0, 0, 0)
        rod.setSpacing(0)

        self.dashboard_side = QWidget()
        self.hovedside = QWidget()
        self.arkivside = QWidget()

        self.sider = QStackedWidget()
        self.sider.addWidget(self.dashboard_side)   # index 0
        self.sider.addWidget(self.hovedside)        # index 1
        self.sider.addWidget(self.arkivside)        # index 2

        rod.addWidget(self.opbyg_sidebar())
        rod.addWidget(self.sider, 1)

        self.opbyg_dashboard()
        self.opbyg_hovedside()
        self.opbyg_arkivside()

        self.sider.currentChanged.connect(self.fane_skiftet)
        self.opdater_alle_visninger()
        self.sider.setCurrentIndex(self.SIDE_DASHBOARD)

    def opbyg_sidebar(self):
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

        self.skaber_label = QLabel("")
        self.skaber_label.setObjectName("sidebarFod")
        layout.addWidget(self.sidst_opdateret_label)
        layout.addWidget(version_label)
        layout.addWidget(self.skaber_label)

        return sidebar

    def opbyg_medarbejderside(self, side, titel, undertitel, soeg_navn, knapper):
        """Fælles layout for Hovedside og Arkiv. Returnerer (tabel, soegefelt)."""
        layout = QVBoxLayout(side)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        hoved, _ = lav_sidehoved(titel, undertitel)
        layout.addLayout(hoved)

        vaerktoej = QHBoxLayout()
        vaerktoej.setSpacing(10)

        soegefelt = QLineEdit()
        soegefelt.setPlaceholderText("Søg på navn, lønnr., status eller kommentar…")
        soegefelt.setClearButtonEnabled(True)
        soegefelt.setMinimumWidth(340)
        soegefelt.textChanged.connect(
            lambda _tekst, navn=soeg_navn: self.anvend_filter(navn)
        )
        vaerktoej.addWidget(soegefelt)
        vaerktoej.addStretch()
        for knap in knapper:
            vaerktoej.addWidget(knap)
        layout.addLayout(vaerktoej)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        tabel = self.opret_medarbejder_tabel()
        kort_layout.addWidget(tabel)
        layout.addWidget(kort, 1)

        return tabel, soegefelt

    def opbyg_hovedside(self):
        self.opret_knap = lav_knap("+ Opret medarbejder", "primary")
        self.rediger_knap = lav_knap("Rediger")
        self.status_knap = lav_knap(
            "Skift status", tooltip="Går til næste status i rækken"
        )
        self.arkiver_knap = lav_knap("Arkiver", "danger")

        self.opret_knap.clicked.connect(self.opret_medarbejder)
        self.rediger_knap.clicked.connect(self.rediger_medarbejder)
        self.status_knap.clicked.connect(self.skift_status)
        self.arkiver_knap.clicked.connect(self.arkiver_medarbejder)

        self.tabel, self.soeg_aktive = self.opbyg_medarbejderside(
            self.hovedside,
            "Medarbejdere",
            "Aktive medarbejdere og status på udstyrsafleveringen.",
            "tabel",
            [self.opret_knap, self.rediger_knap, self.status_knap, self.arkiver_knap],
        )

    def opbyg_arkivside(self):
        self.goer_aktiv_knap = lav_knap("Gør medarbejder aktiv")
        self.slet_knap = lav_knap("Slet permanent", "danger")

        self.goer_aktiv_knap.clicked.connect(self.aktiver_medarbejder)
        self.slet_knap.clicked.connect(self.slet_medarbejder)

        self.tabel_arkiv, self.soeg_arkiv = self.opbyg_medarbejderside(
            self.arkivside,
            "Arkiv",
            "Afsluttede medarbejdere. Kan gøres aktive igen eller slettes.",
            "tabel_arkiv",
            [self.goer_aktiv_knap, self.slet_knap],
        )

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
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.setShowGrid(False)
        tabel.setAlternatingRowColors(True)
        tabel.setWordWrap(False)
        tabel.setTextElideMode(Qt.TextElideMode.ElideRight)
        tabel.verticalHeader().setVisible(False)
        tabel.verticalHeader().setDefaultSectionSize(46)

        header = tabel.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        tabel.setColumnWidth(0, 130)
        tabel.setColumnWidth(1, 280)
        tabel.setColumnWidth(2, 160)
        tabel.setColumnWidth(3, 210)

        tabel.setItemDelegateForColumn(3, StatusDelegate(tabel))

        tabel.setSortingEnabled(True)
        header.setSortIndicator(2, Qt.SortOrder.AscendingOrder)
        return tabel

    def opbyg_dashboard(self):
        ydre = QVBoxLayout(self.dashboard_side)
        ydre.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ydre.addWidget(scroll)

        indre = QWidget()
        indre.setObjectName("scrollInner")
        scroll.setWidget(indre)

        layout = QVBoxLayout(indre)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        hoved, self.dashboard_dato_label = lav_sidehoved(
            "Dashboard", "Overblik over udstyr, fratrædelser og opgaver."
        )
        layout.addLayout(hoved)

        ### --- statistikkort ---
        kort_raekke = QHBoxLayout()
        kort_raekke.setSpacing(14)
        self.kort = {}
        for noegle, titel, farve in (
            ("aktive", "Aktive medarbejdere", FARVER["primary"]),
            ("afventer", Medarbejder.STATUS_AFVENTER, STATUS_STIL[Medarbejder.STATUS_AFVENTER]["farve"]),
            ("delvist", Medarbejder.STATUS_DELVIST, STATUS_STIL[Medarbejder.STATUS_DELVIST]["farve"]),
            ("afviklet", Medarbejder.STATUS_AFVIKLET, STATUS_STIL[Medarbejder.STATUS_AFVIKLET]["farve"]),
            ("arkiverede", "Arkiverede", "#94A3B8"),
        ):
            kort, vaerdi, sub = self.opret_statistik_kort(titel, farve)
            self.kort[noegle] = (vaerdi, sub)
            kort_raekke.addWidget(kort, 1)
        layout.addLayout(kort_raekke)

        ### --- diagrammer ---
        diagram_raekke = QHBoxLayout()
        diagram_raekke.setSpacing(14)

        donut_kort = lav_kort()
        donut_layout = QVBoxLayout(donut_kort)
        donut_layout.setContentsMargins(20, 18, 20, 18)
        donut_layout.setSpacing(8)
        donut_titel = QLabel("Statusfordeling")
        donut_titel.setObjectName("cardTitle")
        donut_under = QLabel("Aktive medarbejdere")
        donut_under.setObjectName("cardSub")
        self.donut = DonutChart()
        donut_layout.addWidget(donut_titel)
        donut_layout.addWidget(donut_under)
        donut_layout.addWidget(self.donut, 1)
        self.legend_labels = {}
        for status in Medarbejder.STATUSER:
            label = QLabel("")
            label.setTextFormat(Qt.TextFormat.RichText)
            self.legend_labels[status] = label
            donut_layout.addWidget(label)

        soejle_kort = lav_kort()
        soejle_layout = QVBoxLayout(soejle_kort)
        soejle_layout.setContentsMargins(20, 18, 20, 18)
        soejle_layout.setSpacing(8)
        soejle_titel = QLabel(f"Fratrædelser de næste {self.DIAGRAM_DAGE} dage")
        soejle_titel.setObjectName("cardTitle")
        soejle_under = QLabel("Antal aktive medarbejdere, der fratræder pr. dag")
        soejle_under.setObjectName("cardSub")
        self.soejlediagram = BarChart()
        soejle_layout.addWidget(soejle_titel)
        soejle_layout.addWidget(soejle_under)
        soejle_layout.addWidget(self.soejlediagram, 1)

        diagram_raekke.addWidget(donut_kort, 4)
        diagram_raekke.addWidget(soejle_kort, 7)
        layout.addLayout(diagram_raekke)

        ### --- lister ---
        lister = QHBoxLayout()
        lister.setSpacing(14)

        notif_kort, self.notifikations_liste, self.notif_antal = self.opret_liste_kort(
            "Kræver opmærksomhed",
            f"Afventer udstyr og fratrådt for mindst {self.NOTIFIKATIONSDAGE} dage siden",
        )
        kommende_kort, self.kommende_liste, self.kommende_antal = self.opret_liste_kort(
            f"Fratræder inden for {self.KOMMENDE_FRATRAEDELSESDAGE} dage",
            "Aktive medarbejdere, der snart forlader virksomheden",
        )
        lister.addWidget(notif_kort, 1)
        lister.addWidget(kommende_kort, 1)
        layout.addLayout(lister)

    def opret_statistik_kort(self, titel, farve):
        kort = lav_kort()
        kort.setMinimumHeight(112)

        layout = QVBoxLayout(kort)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(7)
        prik = QLabel("●")
        prik.setStyleSheet(f"color: {farve}; font-size: 11px; background: transparent;")
        titel_label = QLabel(titel)
        titel_label.setObjectName("statTitle")
        top.addWidget(prik)
        top.addWidget(titel_label)
        top.addStretch()

        vaerdi_label = QLabel("0")
        vaerdi_label.setObjectName("statValue")
        sub_label = QLabel("")
        sub_label.setObjectName("statSub")

        layout.addLayout(top)
        layout.addWidget(vaerdi_label)
        layout.addWidget(sub_label)
        return kort, vaerdi_label, sub_label

    def opret_liste_kort(self, titel, undertitel):
        kort = lav_kort()
        layout = QVBoxLayout(kort)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        titel_label = QLabel(titel)
        titel_label.setObjectName("cardTitle")
        antal_label = QLabel("0")
        antal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        antal_label.setMinimumWidth(28)
        antal_label.setStyleSheet(
            f"background: {FARVER['primary_soft']}; color: {FARVER['primary']};"
            "border-radius: 10px; font-weight: 700; font-size: 12px; padding: 3px 8px;"
        )
        top.addWidget(titel_label)
        top.addStretch()
        top.addWidget(antal_label)

        under_label = QLabel(undertitel)
        under_label.setObjectName("cardSub")

        liste = QListWidget()
        liste.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        liste.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        liste.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        liste.setMinimumHeight(260)

        layout.addLayout(top)
        layout.addWidget(under_label)
        layout.addWidget(liste, 1)
        return kort, liste, antal_label

    ### ----- tabeller -------------------------------------------------------

    def _tabel_for(self, visning):
        if visning == "tabel":
            return self.tabel
        if visning == "tabel_arkiv":
            return self.tabel_arkiv
        raise ValueError(f"Ukendt tabelvisning: {visning}")

    @staticmethod
    def _loennr_noegle(loennr):
        tekst = str(loennr)
        if tekst.isdigit():
            return (0, int(tekst), "")
        return (1, 0, tekst.lower())

    @staticmethod
    def _celle(tekst, noegle, loennr):
        item = SortItem(tekst)
        item.setData(SORT_ROLE, noegle)
        item.setData(LOENNR_ROLE, str(loennr))
        return item

    def opdater_tabel(self, visning, indholdliste):
        tabel = self._tabel_for(visning)

        # Bevar markering og scrollposition ved automatisk opdatering.
        valgt_loennr = self.valgt_loennr(tabel)
        scroll_position = tabel.verticalScrollBar().value()

        tabel.setUpdatesEnabled(False)
        tabel.setSortingEnabled(False)
        try:
            tabel.setRowCount(len(indholdliste))

            for row, m in enumerate(indholdliste):
                dato = laes_dato(m.fratraedelsesdato)
                vis_dato = (
                    dato.toString("dd-MM-yyyy")
                    if dato.isValid()
                    else str(m.fratraedelsesdato)
                )
                status_nr = (
                    Medarbejder.STATUSER.index(m.status)
                    if m.status in Medarbejder.STATUSER
                    else 99
                )

                tabel.setItem(row, 0, self._celle(
                    str(m.loennr), self._loennr_noegle(m.loennr), m.loennr))
                tabel.setItem(row, 1, self._celle(
                    str(m.navn), str(m.navn).lower(), m.loennr))
                tabel.setItem(row, 2, self._celle(
                    vis_dato, str(m.fratraedelsesdato), m.loennr))
                tabel.setItem(row, 3, self._celle(
                    str(m.status), status_nr, m.loennr))
                tabel.setItem(row, 4, self._celle(
                    str(m.kommentar), str(m.kommentar).lower(), m.loennr))
        finally:
            # Aktiverer sorteringen igen, hvilket også sorterer rækkerne.
            tabel.setSortingEnabled(True)
            tabel.setUpdatesEnabled(True)

        # Gendan markering ved at matche lønnr. igen.
        if valgt_loennr is not None:
            for row in range(tabel.rowCount()):
                item = tabel.item(row, 0)
                if item is not None and item.data(LOENNR_ROLE) == valgt_loennr:
                    tabel.selectRow(row)
                    tabel.setCurrentCell(row, 0)
                    break

        self.anvend_filter(visning)
        tabel.verticalScrollBar().setValue(scroll_position)

    def anvend_filter(self, visning):
        tabel = self._tabel_for(visning)
        felt = self.soeg_aktive if visning == "tabel" else self.soeg_arkiv
        soegetekst = felt.text().strip().lower()

        for row in range(tabel.rowCount()):
            if not soegetekst:
                tabel.setRowHidden(row, False)
                continue
            tekster = (
                (tabel.item(row, kolonne).text().lower() if tabel.item(row, kolonne) else "")
                for kolonne in range(tabel.columnCount())
            )
            tabel.setRowHidden(row, not any(soegetekst in t for t in tekster))

    def valgt_loennr(self, tabel):
        rows = tabel.selectionModel().selectedRows()
        if not rows:
            return None
        item = tabel.item(rows[0].row(), 0)
        return item.data(LOENNR_ROLE) if item is not None else None

    def valgt_medarbejder(self, visning):
        if visning == "tabel":
            liste = self.medarbejdere_liste
        elif visning == "tabel_arkiv":
            liste = self.medarbejdere_liste_arkiv
        else:
            return None
        loennr = self.valgt_loennr(self._tabel_for(visning))
        return None if loennr is None else self._find(liste, loennr)

    ### ----- handlinger -----------------------------------------------------

    def _vaelg_foerst(self):
        QMessageBox.information(self, "Ingen valgt", "Vælg en medarbejder først.")

    def _findes_ikke_laengere(self):
        QMessageBox.warning(
            self,
            "Medarbejder ikke fundet",
            "Medarbejderen findes ikke længere (er den ændret af en anden?). "
            "Visningen er opdateret.",
        )
        self.opdater_alle_visninger()

    def opret_medarbejder(self):
        self.synkroniser()
        dialog = MedarbejderDialog(
            self, optagede_loennumre=self._alle_loennumre()
        )
        if not dialog.exec():
            return

        data = dialog.hent_data()

        # Tjek igen: en kollega kan have oprettet samme lønnr. imens.
        self.synkroniser()
        if data["loennr"] in self._alle_loennumre():
            QMessageBox.warning(
                self,
                "Lønnr. findes allerede",
                "Der findes allerede en medarbejder med dette lønnr.",
            )
            return

        self.medarbejdere_liste.append(Medarbejder(
            data["loennr"],
            data["navn"],
            data["fratraedelsesdato"],
            data["status"],
            data["kommentar"],
        ))
        self._gem_aktive()
        self.opdater_alle_visninger()

    def rediger_medarbejder(self):
        loennr = self.valgt_loennr(self.tabel)
        if loennr is None:
            self._vaelg_foerst()
            return

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
            return

        dialog = MedarbejderDialog(
            self, medarbejder, optagede_loennumre=self._alle_loennumre(undtagen=loennr)
        )
        if not dialog.exec():
            return

        data = dialog.hent_data()

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
            return
        if data["loennr"] in self._alle_loennumre(undtagen=loennr):
            QMessageBox.warning(
                self,
                "Lønnr. findes allerede",
                "En anden medarbejder bruger allerede dette lønnr.",
            )
            return

        medarbejder.loennr = data["loennr"]
        medarbejder.navn = data["navn"]
        medarbejder.fratraedelsesdato = data["fratraedelsesdato"]
        medarbejder.status = Medarbejder.normaliser_status(data["status"])
        medarbejder.kommentar = data["kommentar"]

        self._gem_aktive()
        self.opdater_alle_visninger()

    def skift_status(self):
        loennr = self.valgt_loennr(self.tabel)
        if loennr is None:
            self._vaelg_foerst()
            return

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
            return

        statuser = list(Medarbejder.STATUSER)
        nuvaerende = statuser.index(medarbejder.status)
        medarbejder.status = statuser[(nuvaerende + 1) % len(statuser)]

        self._gem_aktive()
        self.opdater_alle_visninger()

    def arkiver_medarbejder(self):
        loennr = self.valgt_loennr(self.tabel)
        if loennr is None:
            self._vaelg_foerst()
            return

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
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
        self._laes_data()
        self.opdater_alle_visninger()

    def aktiver_medarbejder(self):
        loennr = self.valgt_loennr(self.tabel_arkiv)
        if loennr is None:
            self._vaelg_foerst()
            return

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste_arkiv, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
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
        self._laes_data()
        self.opdater_alle_visninger()

    def slet_medarbejder(self):
        loennr = self.valgt_loennr(self.tabel_arkiv)
        if loennr is None:
            self._vaelg_foerst()
            return

        self.synkroniser()
        medarbejder = self._find(self.medarbejdere_liste_arkiv, loennr)
        if medarbejder is None:
            self._findes_ikke_laengere()
            return

        svar = QMessageBox.warning(
            self,
            "Slet medarbejder permanent",
            f"Vil du slette {medarbejder.navn} (lønnr. {medarbejder.loennr}) "
            "permanent fra arkivet?\n\nHandlingen kan ikke fortrydes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return

        data_manager.slet_fra_arkiv(medarbejder)
        self._laes_data()
        self.opdater_alle_visninger()

    ### ----- dashboard ------------------------------------------------------

    def opdater_dashboard(self):
        aktive = self.medarbejdere_liste
        antal_aktive = len(aktive)
        antal_arkiverede = len(self.medarbejdere_liste_arkiv)
        tael = {
            status: sum(1 for m in aktive if m.status == status)
            for status in Medarbejder.STATUSER
        }
        antal_notifikationer = len(self._notifikationer())

        def procent(antal):
            return round(antal / antal_aktive * 100) if antal_aktive else 0

        vaerdi, sub = self.kort["aktive"]
        vaerdi.setText(str(antal_aktive))
        if antal_notifikationer:
            sub.setText(f"{antal_notifikationer} kræver opmærksomhed")
            sub.setStyleSheet(f"color: {STATUS_STIL[Medarbejder.STATUS_AFVENTER]['tekst']};")
        else:
            sub.setText("Intet kræver opmærksomhed")
            sub.setStyleSheet("")

        for noegle, status in (
            ("afventer", Medarbejder.STATUS_AFVENTER),
            ("delvist", Medarbejder.STATUS_DELVIST),
            ("afviklet", Medarbejder.STATUS_AFVIKLET),
        ):
            vaerdi, sub = self.kort[noegle]
            vaerdi.setText(str(tael[status]))
            sub.setText(f"{procent(tael[status])}% af aktive")

        vaerdi, sub = self.kort["arkiverede"]
        vaerdi.setText(str(antal_arkiverede))
        sub.setText("Afsluttede forløb")

        # Donut + forklaring
        self.donut.saet_data(
            [(s, tael[s], STATUS_STIL[s]["farve"]) for s in Medarbejder.STATUSER],
            antal_aktive,
            "aktive",
        )
        for status in Medarbejder.STATUSER:
            farve = STATUS_STIL[status]["farve"]
            self.legend_labels[status].setText(
                f'<span style="color:{farve}; font-size:14px;">●</span>&nbsp;&nbsp;'
                f"{status} &nbsp;<b>{tael[status]}</b> "
                f'<span style="color:{FARVER["muted"]};">({procent(tael[status])}%)</span>'
            )

        self.dashboard_dato_label.setText(
            f"Overblik over udstyr, fratrædelser og opgaver · "
            f"{dansk_dato(QDate.currentDate())}"
        )

    def opdater_diagram(self):
        i_dag = QDate.currentDate()
        antal_pr_dag = {}
        for m in self.medarbejdere_liste:
            dato = laes_dato(m.fratraedelsesdato)
            if dato.isValid():
                antal_pr_dag[dato] = antal_pr_dag.get(dato, 0) + 1

        data = []
        for i in range(self.DIAGRAM_DAGE):
            dato = i_dag.addDays(i)
            data.append((
                dato.day(),
                UGEDAGE_KORT[dato.dayOfWeek() - 1],
                antal_pr_dag.get(dato, 0),
                i == 0,
                dato.dayOfWeek() >= 6,
            ))
        self.soejlediagram.saet_data(data)

    def _notifikationer(self):
        """Aktive med status 'Afventer Udstyr', fratrådt for >= 14 dage siden."""
        i_dag = QDate.currentDate()
        resultat = []
        for m in self.medarbejdere_liste:
            if m.status != Medarbejder.STATUS_AFVENTER:
                continue
            dato = laes_dato(m.fratraedelsesdato)
            if not dato.isValid():
                continue
            dage_siden = dato.daysTo(i_dag)
            if dage_siden >= self.NOTIFIKATIONSDAGE:
                resultat.append((dage_siden, dato, m))
        # Mest overskredne fratrædelser øverst.
        resultat.sort(key=lambda element: element[0], reverse=True)
        return resultat

    def _fyld_liste(self, liste, raekker, tom_tekst):
        liste.clear()
        if not raekker:
            item = QListWidgetItem()
            label = QLabel(tom_tekst)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                f"color: {FARVER['muted']}; padding: 44px 0; background: transparent;"
            )
            item.setSizeHint(label.sizeHint())
            liste.addItem(item)
            liste.setItemWidget(item, label)
            return
        for widget in raekker:
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            liste.addItem(item)
            liste.setItemWidget(item, widget)

    def opdater_notifikationer(self):
        raekker = []
        notifikationer = self._notifikationer()
        for dage_siden, dato, m in notifikationer:
            kritisk = dage_siden >= 30
            raekker.append(lav_raekke(
                f"{m.navn}  ·  lønnr. {m.loennr}",
                f"Fratrådt {dato.toString('dd-MM-yyyy')} – udstyr mangler",
                f"{dage_siden} dage",
                "#FEE2E2" if kritisk else "#FEF3C7",
                "#B91C1C" if kritisk else "#B45309",
            ))
        self._fyld_liste(
            self.notifikations_liste, raekker, "Ingen medarbejdere kræver opmærksomhed."
        )
        self.notif_antal.setText(str(len(notifikationer)))

    def opdater_kommende_fratraedelser(self):
        i_dag = QDate.currentDate()
        kommende = []
        for m in self.medarbejdere_liste:
            dato = laes_dato(m.fratraedelsesdato)
            if not dato.isValid():
                continue
            dage_til = i_dag.daysTo(dato)
            if 0 <= dage_til <= self.KOMMENDE_FRATRAEDELSESDAGE:
                kommende.append((dato, dage_til, m))
        kommende.sort(key=lambda element: (element[0].toJulianDay(), element[2].navn))

        raekker = []
        for dato, dage_til, m in kommende:
            if dage_til == 0:
                badge, bg, tekst = "I dag", "#FEE2E2", "#B91C1C"
            elif dage_til == 1:
                badge, bg, tekst = "I morgen", "#FEF3C7", "#B45309"
            else:
                badge, bg, tekst = f"{dage_til} dage", "#E0E7FF", "#4338CA"
            raekker.append(lav_raekke(
                f"{m.navn}  ·  lønnr. {m.loennr}",
                f"{dato.toString('dd-MM-yyyy')} – {m.status}",
                badge, bg, tekst,
            ))
        self._fyld_liste(
            self.kommende_liste,
            raekker,
            f"Ingen fratrædelser inden for {self.KOMMENDE_FRATRAEDELSESDAGE} dage.",
        )
        self.kommende_antal.setText(str(len(kommende)))

    def fane_skiftet(self, index):
        if 0 <= index < len(self.nav_knapper):
            self.nav_knapper[index].setChecked(True)
        if self.sider.widget(index) == self.dashboard_side:
            self.opdater_dashboard_visning()

    def opdater_dashboard_visning(self):
        self.opdater_dashboard()
        self.opdater_diagram()
        self.opdater_notifikationer()
        self.opdater_kommende_fratraedelser()

    def opdater_alle_visninger(self):
        self.synkroniser()
        self.opdater_tabel("tabel", self.medarbejdere_liste)
        self.opdater_tabel("tabel_arkiv", self.medarbejdere_liste_arkiv)
        self.opdater_dashboard_visning()
        self.sidst_opdateret_label.setText(f"Sidst opdateret {QTime.currentTime().toString('HH:mm')}")
        self.skaber_label.setText("© MASAN")
