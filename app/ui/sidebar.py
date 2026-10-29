"""Venstremenuen: hovedområderne (Arbejdsoverblik, Onboarding,
Offboarding, Telefoner, Ønsker & Udvikling) med ikon og tekst.

Et områdes undersider vises som faner øverst i arbejdsområdet (hovedvinduet),
ikke her. Indstillinger er tandhjulet ved det indloggede brugerområde nederst.
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_BESKRIVELSE, APP_NAVN, APP_SLOGAN, VERSION
from app.ui import ikoner
from app.ui.hjaelpere import lav_knap, lav_logo
from app.ui.theme import FARVER


# Forbindelsens tilstand (vises nederst i menuen).
ONLINE = "online"
FORBINDER = "forbinder"
MISTET = "mistet"

INDSTILLINGER = "indstillinger"


class Sidebar(QFrame):
    omraade_valgt = Signal(str)
    log_ud = Signal()
    opdatering_valgt = Signal()

    def __init__(self, omraader):
        """omraader: [(nøgle, tekst, ikon, [(side, fanetekst), ...]), ...]"""
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(3)

        titel = QLabel(APP_NAVN)
        titel.setObjectName("appTitle")
        titel.setToolTip(APP_BESKRIVELSE)
        logo = lav_logo(40)
        logo.setToolTip(APP_BESKRIVELSE)
        titel_raekke = QHBoxLayout()
        titel_raekke.setSpacing(10)
        titel_raekke.addWidget(logo)
        titel_raekke.addWidget(titel, 1)
        slogan = QLabel(APP_SLOGAN)
        slogan.setObjectName("appSlogan")
        slogan.setWordWrap(True)
        layout.addLayout(titel_raekke)
        layout.addSpacing(4)
        layout.addWidget(slogan)
        layout.addSpacing(14)

        # Menupunkterne kan rulles, så de ikke trykkes sammen på lave skærme.
        rul = QScrollArea()
        rul.setWidgetResizable(True)
        rul.setFrameShape(QFrame.Shape.NoFrame)
        rul.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rul.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        menu = QWidget()
        rul.setWidget(menu)
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(4)
        layout.addWidget(rul, 1)

        self.gruppe = QButtonGroup(self)
        self.gruppe.setExclusive(True)
        self.knapper = {}               # områdenøgle -> knap
        self._ikoner = {}               # knap -> ikonnavn
        for noegle, tekst, ikon, _ in omraader:
            knap = QPushButton(tekst.replace("&", "&&"))   # "&" er ellers genvejstast i Qt
            knap.setProperty("nav", True)
            knap.setCheckable(True)
            knap.setIconSize(QSize(18, 18))
            knap.setCursor(Qt.CursorShape.PointingHandCursor)
            knap.clicked.connect(lambda _=False, n=noegle: self.omraade_valgt.emit(n))
            self.gruppe.addButton(knap)
            self.knapper[noegle] = knap
            self._ikoner[knap] = ikon
            menu_layout.addWidget(knap)

        menu_layout.addStretch()
        # Central opdatering: vises, når en ny version er klar (hovedvinduet).
        self.opdatering_knap = lav_knap("", "primary")
        self.opdatering_knap.setVisible(False)
        self.opdatering_knap.clicked.connect(self.opdatering_valgt.emit)
        layout.addWidget(self.opdatering_knap)
        layout.addSpacing(6)
        self.lagring_label = QLabel("")
        self.lagring_label.setWordWrap(True)
        layout.addWidget(self.lagring_label)
        layout.addSpacing(8)

        # Brugerområdet: hvem er logget ind, indstillinger (tandhjul) og log ud.
        bruger = QFrame()
        bruger.setObjectName("brugerOmraade")
        bruger_raekke = QHBoxLayout(bruger)
        bruger_raekke.setContentsMargins(10, 8, 6, 8)
        bruger_raekke.setSpacing(4)
        self.bruger_label = QLabel("")
        self.bruger_label.setObjectName("sidebarBruger")
        self.bruger_label.setWordWrap(True)
        self.indstillinger_knap = QToolButton()
        self.indstillinger_knap.setObjectName("sidebarIkon")
        self.indstillinger_knap.setCheckable(True)
        self.indstillinger_knap.setToolTip("Indstillinger")
        self.indstillinger_knap.setAccessibleName("Indstillinger")
        self.indstillinger_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.indstillinger_knap.clicked.connect(lambda: self.omraade_valgt.emit(INDSTILLINGER))
        self.gruppe.addButton(self.indstillinger_knap)
        self._ikoner[self.indstillinger_knap] = "indstillinger"
        self.knapper[INDSTILLINGER] = self.indstillinger_knap
        self.log_ud_knap = QToolButton()
        self.log_ud_knap.setObjectName("sidebarIkon")
        self.log_ud_knap.setText("Log ud")
        self.log_ud_knap.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.log_ud_knap.setToolTip("Log ud af IN-BASE")
        self.log_ud_knap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_ud_knap.clicked.connect(self.log_ud.emit)
        self._ikoner[self.log_ud_knap] = "log_ud"
        for knap in (self.indstillinger_knap, self.log_ud_knap):
            knap.setIconSize(QSize(20, 20))
        bruger_raekke.addWidget(self.bruger_label, 1)
        bruger_raekke.addWidget(self.indstillinger_knap)
        bruger_raekke.addWidget(self.log_ud_knap)
        layout.addWidget(bruger)
        layout.addSpacing(6)
        self.opdateret_label = QLabel("")
        self.opdateret_label.setObjectName("sidebarFod")
        fod = QLabel(f"{VERSION} · © MASAN")
        fod.setObjectName("sidebarFod")
        layout.addWidget(self.opdateret_label)
        layout.addWidget(fod)
        self.opdater_ikoner()

    def opdater_ikoner(self):
        """Ikonerne farves efter temaet – kaldes igen ved temaskift."""
        for knap, navn in self._ikoner.items():
            knap.setIcon(ikoner.ikon(navn, FARVER["sidebar_tekst"], "#FFFFFF"))

    def marker(self, noegle):
        """Markér området (eller INDSTILLINGER), der indeholder den aktive side."""
        knap = self.knapper.get(noegle)
        if knap:
            knap.setChecked(True)

    def saet_bruger(self, bruger: dict):
        """Brugernavnet er identiteten i IN-BASE; visningsnavnet står i tooltip."""
        self.bruger_label.setText(f"{bruger.get('brugernavn', '')}\n{bruger.get('rolle', '')}")
        self.bruger_label.setToolTip(f"Logget ind som {bruger.get('navn', '')}")

    def saet_opdatering(self, version: str | None) -> None:
        """Knappen "Ny version" – skjult, når der ingen opdatering er."""
        self.opdatering_knap.setVisible(bool(version))
        if version:
            self.opdatering_knap.setText(f"⬆  Version {version} er klar")
            self.opdatering_knap.setToolTip("Klik for at se, hvad der er nyt, og opdatere")

    def saet_lagring(self, offline: bool, ventende: int, kilde: str = "central datamappe"):
        if offline:
            self.lagring_label.setObjectName("lagringOffline")
            self.lagring_label.setText(f"● OFFLINE · {ventende} ikke synkroniseret")
            self.lagring_label.setToolTip("Ændringer gemmes lokalt. Gå online under Indstillinger.")
        else:
            self.lagring_label.setObjectName("lagringOnline")
            self.lagring_label.setText(f"● ONLINE · {kilde.split(' (')[0]}")
            self.lagring_label.setToolTip(f"Data gemmes direkte i {kilde}.")
        self._polish()

    def saet_forbindelse(self, tilstand: str, sidst_opdateret: str = "") -> None:
        """Online / Forbinder / Forbindelse mistet + seneste vellykkede opdatering.

        IN-BASE kan ikke arbejde offline mod Supabase: uden forbindelse kan
        intet gemmes, og det står i værktøjstippet."""
        sidst = f" · {sidst_opdateret}" if sidst_opdateret else ""
        tekst, navn, tip = {
            ONLINE: (f"● Online{sidst}", "lagringOnline",
                     "Forbundet til den fælles database. Data opdateres hvert minut."),
            FORBINDER: ("● Forbinder…", "lagringForbinder", "Opretter forbindelse til databasen."),
            MISTET: (f"● Forbindelse mistet{sidst}", "lagringOffline",
                     "Ingen forbindelse til databasen – ændringer kan ikke gemmes. "
                     "Der prøves igen hvert minut. Tidspunktet er seneste vellykkede opdatering."),
        }[tilstand]
        self.lagring_label.setObjectName(navn)
        self.lagring_label.setText(tekst)
        self.lagring_label.setToolTip(tip)
        self._polish()

    def _polish(self):
        self.lagring_label.style().unpolish(self.lagring_label)
        self.lagring_label.style().polish(self.lagring_label)
