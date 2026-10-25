"""Log på-skærmen, der skal passeres før programmet åbner.

Har en ny bruger fået en midlertidig adgangskode af administratoren, skal
vedkommende vælge sin egen, før programmet åbner (NyKodeDialog).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app import APP_BESKRIVELSE, APP_NAVN, APP_SLOGAN, VERSION
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.ui.hjaelpere import lav_app_ikon, lav_kort, lav_logo


class NyKodeDialog(QDialog):
    """Første log på: erstat den midlertidige adgangskode med en ny."""

    def __init__(self, parent, auth):
        super().__init__(parent)
        self.auth = auth
        self.setWindowTitle("Vælg din egen adgangskode")
        self.setMinimumWidth(440)
        forklaring = QLabel(
            "Du er logget på med en midlertidig adgangskode fra din administrator. "
            f"Vælg nu din egen (mindst {auth.MIN_KODE} tegn)."
        )
        forklaring.setWordWrap(True)
        self.kode_input = QLineEdit()
        self.gentag_input = QLineEdit()
        for felt in (self.kode_input, self.gentag_input):
            felt.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout()
        form.addRow("Ny adgangskode", self.kode_input)
        form.addRow("Gentag", self.gentag_input)
        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        knapper.button(QDialogButtonBox.StandardButton.Ok).setText("Gem og fortsæt")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(forklaring)
        layout.addLayout(form)
        layout.addWidget(self.fejl_label)
        layout.addWidget(knapper)

    def accept(self):
        try:
            self.auth.skift_midlertidig_kode(self.kode_input.text(), self.gentag_input.text())
        except (ValideringsFejl, DataFejl) as fejl:
            self.fejl_label.setText(str(fejl))
            return
        super().accept()


class LoginDialog(QDialog):
    """Efter exec(): self.bruger er den bruger, der loggede på."""

    def __init__(self, auth, parent=None, offline_tekst=""):
        super().__init__(parent)
        self.auth = auth
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
        titel.setObjectName("loginTitel")
        slogan = QLabel(APP_SLOGAN)
        slogan.setObjectName("appSlogan")
        beskrivelse = QLabel(APP_BESKRIVELSE)
        beskrivelse.setObjectName("hjaelpTekst")
        beskrivelse.setWordWrap(True)

        self.brugernavn_input = QLineEdit()
        self.brugernavn_input.setPlaceholderText(f"{auth.LOGIN_FELT}, fx HAFRA")
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

        indhold.addWidget(lav_logo(64))
        indhold.addSpacing(6)
        indhold.addWidget(titel)
        indhold.addWidget(slogan)
        indhold.addWidget(beskrivelse)
        indhold.addSpacing(14)
        indhold.addWidget(QLabel(auth.LOGIN_FELT))
        indhold.addWidget(self.brugernavn_input)
        indhold.addWidget(QLabel("Adgangskode"))
        indhold.addWidget(self.kode_input)
        indhold.addWidget(self.fejl_label)
        indhold.addWidget(log_paa)
        indhold.addSpacing(6)
        if offline_tekst:
            offline = QLabel(offline_tekst)
            offline.setObjectName("advarsel")
            offline.setWordWrap(True)
            indhold.addWidget(offline)
        if auth.BETA:
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
        try:
            bruger = self.auth.log_ind(self.brugernavn_input.text(), self.kode_input.text())
        except DataFejl as fejl:     # ingen forbindelse, deaktiveret, ingen profil o.l.
            self.fejl_label.setText(str(fejl))
            self.kode_input.clear()
            return
        if bruger is None:
            self.fejl_label.setText(self.auth.LOGIN_FEJL)
            self.kode_input.clear()
            self.kode_input.setFocus()
            return
        if bruger.get("skal_skifte_kode") and not NyKodeDialog(self, self.auth).exec():
            self.auth.log_ud()
            self.fejl_label.setText("Du skal vælge en ny adgangskode for at fortsætte.")
            self.kode_input.clear()
            return
        self.bruger = bruger
        self.accept()
