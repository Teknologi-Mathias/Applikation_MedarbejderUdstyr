"""Log på-skærmen, der skal passeres før programmet åbner."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app import APP_BESKRIVELSE, APP_NAVN, APP_SLOGAN, VERSION, brugere
from app.ui.hjaelpere import lav_app_ikon, lav_kort


class LoginDialog(QDialog):
    """Efter exec(): self.bruger er den bruger, der loggede på."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bruger = None
        self.setWindowTitle(f"{APP_NAVN} – Log på")
        self.setWindowIcon(lav_app_ikon())
        self.setMinimumSize(500, 700)

        kort = lav_kort()
        kort.setObjectName("loginKort")
        # Fast bredde, så ombrudte tekster får den rigtige højde.
        kort.setFixedWidth(420)
        indhold = QVBoxLayout(kort)
        indhold.setContentsMargins(32, 30, 32, 28)
        indhold.setSpacing(10)

        titel = QLabel(APP_NAVN)
        titel.setObjectName("appTitle")
        titel.setStyleSheet("font-size: 30px;")
        slogan = QLabel(APP_SLOGAN)
        slogan.setObjectName("appSlogan")
        beskrivelse = QLabel(APP_BESKRIVELSE)
        beskrivelse.setObjectName("hjaelpTekst")
        beskrivelse.setWordWrap(True)

        self.brugernavn_input = QLineEdit()
        self.brugernavn_input.setPlaceholderText("Brugernavn")
        self.kode_input = QLineEdit()
        self.kode_input.setPlaceholderText("Adgangskode")
        self.kode_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        log_paa = QPushButton("Log på")
        log_paa.setProperty("variant", "primary")
        log_paa.setDefault(True)
        log_paa.setCursor(Qt.CursorShape.PointingHandCursor)
        log_paa.clicked.connect(self._log_paa)

        beta = QLabel(
            "BETA: Adgangskoder er ikke sikkert beskyttet. "
            "Brug ikke private adgangskoder."
        )
        beta.setObjectName("beta")
        beta.setWordWrap(True)

        indhold.addWidget(titel)
        indhold.addWidget(slogan)
        indhold.addWidget(beskrivelse)
        indhold.addSpacing(14)
        indhold.addWidget(QLabel("Brugernavn"))
        indhold.addWidget(self.brugernavn_input)
        indhold.addWidget(QLabel("Adgangskode"))
        indhold.addWidget(self.kode_input)
        indhold.addWidget(self.fejl_label)
        indhold.addWidget(log_paa)
        indhold.addSpacing(6)
        if brugere.bruger_standardkode():
            foerste = QLabel(
                "Første gang: log på med admin / admin, og skift derefter koden "
                "under Brugerkartotek."
            )
            foerste.setObjectName("info")
            foerste.setWordWrap(True)
            indhold.addWidget(foerste)
        indhold.addWidget(beta)

        version = QLabel(VERSION)
        version.setObjectName("sidebarFod")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centreres med stræk (ikke alignment), så kortet får den højde,
        # som de ombrudte tekster kræver.
        midte = QHBoxLayout()
        midte.addStretch()
        midte.addWidget(kort)
        midte.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.addStretch()
        layout.addLayout(midte)
        layout.addStretch()
        layout.addWidget(version)

        self.brugernavn_input.setFocus()

    def _log_paa(self):
        bruger = brugere.log_ind(self.brugernavn_input.text(), self.kode_input.text())
        if bruger is None:
            self.fejl_label.setText("Forkert brugernavn eller adgangskode.")
            self.kode_input.clear()
            self.kode_input.setFocus()
            return
        self.bruger = bruger
        self.accept()
