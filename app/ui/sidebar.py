"""Venstremenuen: Dashboard, Onboarding, Offboarding, Ønsker & Udvikling og Indstillinger.

Onboarding og Offboarding er to separate hovedpunkter med hver deres
undersider; Ønsker & Udvikling er et selvstændigt punkt. Et hovedpunkt kan foldes sammen; det, der indeholder den aktive
side, foldes altid ud.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import APP_BESKRIVELSE, APP_NAVN, APP_SLOGAN, VERSION
from app.ui.hjaelpere import lav_knap, lav_logo


# Forbindelsens tilstand (vises nederst i menuen).
ONLINE = "online"
FORBINDER = "forbinder"
MISTET = "mistet"


class Sidebar(QFrame):
    side_valgt = Signal(str)
    log_ud = Signal()

    def __init__(self, struktur):
        """struktur: [(sektion eller None, [(nøgle, tekst), ...]), ...]"""
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
        menu_layout.setSpacing(3)
        layout.addWidget(rul, 1)

        self.gruppe = QButtonGroup(self)
        self.gruppe.setExclusive(True)
        self.knapper = {}
        self.sektioner = {}          # sektion -> (hovedknap, [underknapper])
        for sektion, punkter in struktur:
            underknapper = []
            if sektion:
                hoved = QPushButton(f"▾  {sektion.upper()}")
                hoved.setProperty("navSektion", True)
                hoved.setCursor(Qt.CursorShape.PointingHandCursor)
                hoved.clicked.connect(lambda _=False, s=sektion: self._fold(s))
                menu_layout.addWidget(hoved)
            for noegle, tekst in punkter:
                knap = QPushButton(tekst.replace("&", "&&"))   # "&" er ellers genvejstast i Qt
                knap.setProperty("navUnder" if sektion else "nav", True)
                knap.setCheckable(True)
                knap.setCursor(Qt.CursorShape.PointingHandCursor)
                knap.clicked.connect(lambda _=False, n=noegle: self.side_valgt.emit(n))
                self.gruppe.addButton(knap)
                self.knapper[noegle] = knap
                underknapper.append(knap)
                menu_layout.addWidget(knap)
            if sektion:
                self.sektioner[sektion] = (hoved, underknapper)
            menu_layout.addSpacing(6)

        menu_layout.addStretch()
        self.lagring_label = QLabel("")
        self.lagring_label.setWordWrap(True)
        layout.addWidget(self.lagring_label)
        layout.addSpacing(6)
        bruger_raekke = QHBoxLayout()
        self.bruger_label = QLabel("")
        self.bruger_label.setObjectName("sidebarBruger")
        self.bruger_label.setWordWrap(True)
        log_ud = lav_knap("Log ud")
        log_ud.setStyleSheet("padding: 5px 12px; font-size: 12px;")
        log_ud.clicked.connect(self.log_ud.emit)
        bruger_raekke.addWidget(self.bruger_label, 1)
        bruger_raekke.addWidget(log_ud)
        layout.addLayout(bruger_raekke)
        layout.addSpacing(6)
        self.opdateret_label = QLabel("")
        self.opdateret_label.setObjectName("sidebarFod")
        fod = QLabel(f"{VERSION} · © MASAN")
        fod.setObjectName("sidebarFod")
        layout.addWidget(self.opdateret_label)
        layout.addWidget(fod)

    def _fold(self, sektion, aaben=None):
        hoved, knapper = self.sektioner[sektion]
        aaben = not knapper[0].isVisible() if aaben is None else aaben
        if not aaben and any(k.isChecked() for k in knapper):
            return   # den aktive side må ikke skjules
        for knap in knapper:
            knap.setVisible(aaben)
        hoved.setText(f"{'▾' if aaben else '▸'}  {sektion.upper()}")

    def marker(self, noegle):
        knap = self.knapper.get(noegle)
        if knap:
            knap.setChecked(True)
            for sektion, (_, knapper) in self.sektioner.items():
                if knap in knapper:
                    self._fold(sektion, True)

    def vis_punkt(self, noegle, synlig):
        self.knapper[noegle].setVisible(synlig)

    def saet_bruger(self, bruger: dict):
        """Brugernavnet er identiteten i IN-BASE; visningsnavnet står i tooltip."""
        self.bruger_label.setText(f"{bruger.get('brugernavn', '')}\n{bruger.get('rolle', '')}")
        self.bruger_label.setToolTip(bruger.get("navn", ""))

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
