"""Dialoger til Telefoner (MDM): oplysninger om en telefon og klargøring med QR-kode.

Regler ligger i MdmService – dialogerne viser og indsamler. Klargøringsdialogen
starter den midlertidige server (app/infrastructure/mdm/lokal_server.py), mens
den er åben, og stopper den igen, når den lukkes.
"""
import secrets
from pathlib import Path

from PySide6.QtCore import QObject, QRegularExpression, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.domain import mdm_enhed as md
from app.infrastructure.mdm.lokal_server import KlargoeringsServer, netvaerk
from app.infrastructure.mdm.qr import qr_matrix
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap

QR_STOERRELSE = 460
WIFI_TYPER = ("WPA", "WEP", "NONE")


def qr_pixmap(tekst: str, stoerrelse: int = QR_STOERRELSE, dpr: float = 1.0) -> QPixmap:
    """Tegner QR-koden sort på hvidt (skarpe kanter, uanset tema).

    dpr: skærmens skalering (fx 1.5 ved 150 %). Billedet tegnes i skærmens egne pixels,
    så hvert modul får et helt antal pixels – ellers strækkes og sløres koden på bærbare
    med skalering, og telefonens QR-læser kan ikke læse den."""
    matrix = qr_matrix(tekst)
    n = len(matrix)
    billede = QImage(n, n, QImage.Format.Format_RGB32)
    billede.fill(QColor("white"))
    maler = QPainter(billede)
    for y, raekke in enumerate(matrix):
        for x, sort in enumerate(raekke):
            if sort:
                maler.fillRect(x, y, 1, 1, QColor("black"))
    maler.end()
    pixels = int(stoerrelse * dpr)
    side = max(n, pixels - pixels % n)
    pixmap = QPixmap.fromImage(billede.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.FastTransformation))
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


class TelefonDialog(QDialog):
    """Ny telefon (enhed=None) eller ret oplysninger. Efter exec(): self.resultat."""

    def __init__(self, parent, service, enhed=None):
        super().__init__(parent)
        self.service = service
        self.enhed = enhed
        self.resultat = None
        self.setWindowTitle("Ny telefon" if enhed is None else f"Telefon – {enhed.navn}")
        self.setMinimumWidth(480)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.felter = {"navn": QLineEdit(), "telefonnummer": QLineEdit(), "note": QPlainTextEdit()}
        navn = self.felter["navn"]
        navn.setMaxLength(md.MAKS_NAVN)
        navn.setPlaceholderText("Fx ISM589 – som i ERP")
        navn.setValidator(QRegularExpressionValidator(QRegularExpression("[A-Za-z0-9-]*"), navn))
        navn.textEdited.connect(lambda t: navn.setText(t.upper()) if t != t.upper() else None)
        self.felter["telefonnummer"].setPlaceholderText("Fx +45 12 34 56 78")
        self.felter["note"].setFixedHeight(80)
        self.felter["note"].setTabChangesFocus(True)
        for noegle, etiket in (("navn", "Enhedsnavn (ERP) *"), ("telefonnummer", "Telefonnummer"),
                               ("note", "Note")):
            form.addRow(etiket, self.felter[noegle])
            if enhed is not None:
                felt = self.felter[noegle]
                (felt.setPlainText if noegle == "note" else felt.setText)(getattr(enhed, noegle))

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Opret og klargør" if enhed is None else "Gem")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.fejl_label)
        layout.addWidget(knapper)
        navn.setFocus()

    def data(self) -> dict:
        return {k: (f.toPlainText() if isinstance(f, QPlainTextEdit) else f.text())
                for k, f in self.felter.items()}

    def accept(self):
        def kald():
            try:
                if self.enhed is None:
                    return self.service.opret(self.data())
                return self.service.opdater_info(self.enhed, self.data())
            except ValideringsFejl as fejl:
                self.fejl_label.setText(str(fejl))
                return FEJL
        resultat = udfoer(self, kald)
        if resultat is not FEJL:
            self.resultat = resultat
            super().accept()


class _Bro(QObject):
    """Flytter telefonens rapport fra serverens tråd til brugerfladens tråd."""
    rapport = Signal(dict)
    hentet = Signal(str)


class KlargoeringDialog(QDialog):
    """Indstillinger → QR-kode → telefonen melder tilbage. Efter exec(): self.klargjort."""

    def __init__(self, parent, service, enhed):
        super().__init__(parent)
        self.service = service
        self.enhed = enhed
        self.klargoering = None
        self.server = None
        self.klargjort = False
        self._bro = _Bro()
        self._bro.rapport.connect(self._modtag_rapport)
        self._bro.hentet.connect(self._telefon_hentede)
        self.setWindowTitle(f"Klargør telefon – {enhed.navn}")

        husk = service.huskede_indstillinger()
        self.ssid = QLineEdit(husk["wifi_ssid"])
        self.ssid.setPlaceholderText("Samme net som denne pc")
        self.kode = QLineEdit(husk["wifi_kode"])
        self.kode.setEchoMode(QLineEdit.EchoMode.Password)
        vis_kode = QCheckBox("Vis")
        vis_kode.toggled.connect(lambda vis: self.kode.setEchoMode(
            QLineEdit.EchoMode.Normal if vis else QLineEdit.EchoMode.Password))
        kode_raekke = QHBoxLayout()
        kode_raekke.addWidget(self.kode, 1)
        kode_raekke.addWidget(vis_kode)
        self.sikkerhed = QComboBox()
        self.sikkerhed.addItems(WIFI_TYPER)
        self.sikkerhed.setCurrentText(husk["wifi_type"] or "WPA")
        # FL-UPDATE: APK-fil på pc'en ELLER link – hver sit felt, valgt med radioknapper.
        self.fl_som_fil = QRadioButton("APK-fil på pc'en")
        self.fl_som_link = QRadioButton("Link")
        (self.fl_som_link if husk["fl_kilde"] == "link" else self.fl_som_fil).setChecked(True)
        kilde_raekke = QHBoxLayout()
        kilde_raekke.addWidget(self.fl_som_fil)
        kilde_raekke.addWidget(self.fl_som_link)
        kilde_raekke.addStretch()
        self.fl_fil = QLineEdit(husk["fl_fil"])
        self.fl_fil.setPlaceholderText("C:\\…\\FL-UPDATE.apk")
        self.vaelg_apk = QPushButton("Vælg…")
        self.vaelg_apk.clicked.connect(lambda: self._vaelg(self.fl_fil, "Vælg FL-UPDATE.apk",
                                                           "Android-app (*.apk)"))
        self.fl_link = QLineEdit(husk["fl_link"])
        self.fl_link.setPlaceholderText("https://mx.fl-it.net/…/FL-UPDATE.apk")
        fl_raekke = QHBoxLayout()
        fl_raekke.addWidget(self.fl_fil, 1)
        fl_raekke.addWidget(self.vaelg_apk)
        fl_raekke.addWidget(self.fl_link, 1)
        self.fl_som_fil.toggled.connect(self._vis_fl_kilde)
        self._vis_fl_kilde()
        self.baggrund = QLineEdit(husk["baggrund"])
        self.baggrund.setPlaceholderText("Valgfrit – JPG/PNG på denne pc")
        vaelg = QPushButton("Vælg…")
        vaelg.clicked.connect(lambda: self._vaelg(self.baggrund, "Vælg baggrundsbillede",
                                                  "Billeder (*.jpg *.jpeg *.png)"))
        baggrund_raekke = QHBoxLayout()
        baggrund_raekke.addWidget(self.baggrund, 1)
        baggrund_raekke.addWidget(vaelg)
        self.mail = QCheckBox("Firma-mail (IMAP) i Gmail-appen")
        self.mail.setToolTip("Gmail-appen bliver synlig, og medarbejderen kan tilføje sin "
                             "firma-mail (IMAP). Google-konti kan stadig ikke tilføjes. Kan "
                             "også slås til senere: Handling → Slå firma-mail til.")
        self.ekstra_apps = QLineEdit(husk["ekstra_apps"])
        self.ekstra_apps.setPlaceholderText("Valgfrit – pakkenavne, kommasepareret")
        self.ekstra_apps.setToolTip("Apps, der skal kunne ses ud over Telefon, SMS, Kontakter, "
                                    "Kamera, Galleri, Ur, Lommeregner og Indstillinger "
                                    "(fx com.android.chrome).")
        self.kontakt = QLineEdit(husk["kontakt"])
        self.kontakt.setMaxLength(120)
        self.kontakt.setToolTip("Vises på telefonens låseskærm og når brugeren rammer en spærret "
                                "funktion.")

        self.netkort = QComboBox()
        for navn, ip in netvaerk():
            self.netkort.addItem(f"{navn} – {ip}", ip)
        self.netkort.setToolTip("Det netværk på pc'en, telefonen henter fra. Telefonen er på "
                                "Wi-Fi – vælg pc'ens Wi-Fi, også når pc'en har netværksstik.")

        form = QFormLayout()
        form.addRow("Pc'ens netværk", self.netkort)
        form.addRow("Wi-Fi (SSID)", self.ssid)
        form.addRow("Wi-Fi-kode", kode_raekke)
        form.addRow("Sikkerhed", self.sikkerhed)
        form.addRow("FL-UPDATE *", kilde_raekke)
        form.addRow("", fl_raekke)
        form.addRow("Baggrundsbillede", baggrund_raekke)
        form.addRow("Ekstra apps", self.ekstra_apps)
        form.addRow("Kontakt (låseskærm)", self.kontakt)
        form.addRow("", self.mail)

        self.vis_knap = lav_knap("Vis QR-kode", "primary")
        self.vis_knap.clicked.connect(self._vis_qr)
        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        self.qr = QLabel("QR-koden vises her.")
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setFixedSize(QR_STOERRELSE + 20, QR_STOERRELSE + 20)
        self.qr.setStyleSheet("background: white; color: #666;")
        self.stor_knap = lav_knap("Vis QR-koden i fuld skærm")
        self.stor_knap.setToolTip("Hjælper, når telefonen ikke kan læse koden – fx på en bærbar.")
        self.stor_knap.clicked.connect(self._vis_stor_qr)
        self.stor_knap.hide()
        self._qr_tekst = ""
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setFixedWidth(QR_STOERRELSE + 20)

        trin = QLabel(
            "<ol style='margin-left:-20px'>"
            "<li>Fabriksnulstil telefonen og tænd den.</li>"
            "<li>Tryk <b>6 gange</b> på velkomstskærmen – QR-læseren åbner.</li>"
            "<li>Scan QR-koden. Telefonen kobler på Wi-Fi og henter IN-BASE Klargøring "
            "fra denne pc.</li>"
            "<li>Vent. Telefonen låser sig, skjuler unødvendige apps, sætter baggrund og "
            "installerer FL-UPDATE. Status vises her, når den er færdig.</li>"
            "<li>Åbn FL-UPDATE og tillad den at <i>installere apps</i> – så henter den FL-TMS.</li>"
            "</ol>")
        trin.setWordWrap(True)
        trin.setTextFormat(Qt.TextFormat.RichText)
        note = QLabel("Pc og telefon skal være på samme Wi-Fi, og vinduet skal være åbent, til "
                      "telefonen er færdig. Har pc'en både netværksstik og Wi-Fi, så vælg Wi-Fi "
                      "under Pc'ens netværk. Spørger Windows Firewall, så tillad adgang – også på "
                      "offentlige netværk, hvis firmaets Wi-Fi står som offentligt. Gæste-Wi-Fi "
                      "tillader ofte ikke, at telefon og pc taler sammen.")
        note.setObjectName("hjaelpTekst")
        note.setWordWrap(True)

        venstre = QVBoxLayout()
        venstre.addWidget(self.qr)
        venstre.addWidget(self.stor_knap)
        venstre.addWidget(self.status)
        venstre.addStretch()
        hoejre = QVBoxLayout()
        hoejre.addLayout(form)
        hoejre.addWidget(self.vis_knap, 0, Qt.AlignmentFlag.AlignRight)
        hoejre.addWidget(self.fejl_label)
        hoejre.addWidget(trin)
        hoejre.addWidget(note)
        hoejre.addStretch()
        indhold = QHBoxLayout()
        indhold.setSpacing(24)
        indhold.addLayout(venstre)
        indhold.addLayout(hoejre, 1)

        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knapper.button(QDialogButtonBox.StandardButton.Close).setText("Luk")
        knapper.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addLayout(indhold)
        layout.addWidget(knapper)
        self.setMinimumWidth(900)

        mangler = service.klargoering_mangler()
        if mangler:
            self.fejl_label.setText(mangler)
            self.vis_knap.setEnabled(False)

    def _vis_fl_kilde(self):
        fil = self.fl_som_fil.isChecked()
        for widget in (self.fl_fil, self.vaelg_apk):
            widget.setVisible(fil)
        self.fl_link.setVisible(not fil)

    def _vaelg(self, felt: QLineEdit, titel: str, filter_: str):
        fil, _ = QFileDialog.getOpenFileName(self, titel, felt.text(), filter_)
        if fil:
            felt.setText(fil)

    def indstillinger(self) -> dict:
        return {"wifi_ssid": self.ssid.text(), "wifi_kode": self.kode.text(),
                "wifi_type": self.sikkerhed.currentText(),
                "fl_kilde": "fil" if self.fl_som_fil.isChecked() else "link",
                "fl_fil": self.fl_fil.text(), "fl_link": self.fl_link.text(),
                "baggrund": self.baggrund.text(), "ekstra_apps": self.ekstra_apps.text(),
                "kontakt": self.kontakt.text(), "mail": self.mail.isChecked()}

    def _vis_qr(self):
        self.fejl_label.setText("")
        try:
            self.klargoering = self.service.ny_klargoering(self.enhed, self.indstillinger())
        except ValideringsFejl as fejl:
            self.fejl_label.setText(str(fejl))
            return
        try:
            self._stop_server()
            k = self.klargoering
            self.server = KlargoeringsServer(k.apk, k.token, self._bro.rapport.emit,
                                             baggrund=Path(k.baggrund) if k.baggrund else None,
                                             fl_update=k.fl_update_fil,
                                             vaert=self.netkort.currentData(),
                                             paa_hentning=self._bro.hentet.emit)
            url = self.server.start()
            self._qr_tekst = k.qr_tekst(url)
            self.qr.setPixmap(qr_pixmap(self._qr_tekst, dpr=self.devicePixelRatioF()))
            self.stor_knap.show()
        except OSError as fejl:
            self.fejl_label.setText(f"Klargøringsserveren kunne ikke starte ({fejl}). Er port 8765 "
                                    "optaget af et andet IN-BASE-vindue?")
            return
        except DataFejl as fejl:
            self.fejl_label.setText(str(fejl))
            return
        if k.advarsler:
            self.fejl_label.setText("QR-koden virker, men:\n• " + "\n• ".join(k.advarsler))
        self.vis_knap.setText("Lav ny QR-kode")
        self.status.setText(f"Venter på telefonen … (pc: {url})\n\nNulstillingskode: "
                            f"{k.nulstillingskode}  (gemt i IN-BASE)")

    def _vis_stor_qr(self):
        """QR-koden over hele skærmen – klik eller Esc lukker. Serveren kører videre."""
        vindue = QDialog(self)
        vindue.setStyleSheet("background: white;")
        skaerm = self.screen().geometry()
        billede = QLabel()
        billede.setAlignment(Qt.AlignmentFlag.AlignCenter)
        billede.setPixmap(qr_pixmap(self._qr_tekst, min(skaerm.width(), skaerm.height()) - 40,
                                    self.devicePixelRatioF()))
        billede.mousePressEvent = lambda _e: vindue.accept()
        layout = QVBoxLayout(vindue)
        layout.addWidget(billede)
        vindue.showFullScreen()
        vindue.exec()

    def _telefon_hentede(self, sti: str):
        """Viser, at telefonen har nået pc'en – sker det aldrig, er det net/firewall."""
        tekst = {"/inbase-klargoering.apk": "Telefonen har hentet styrings-appen …",
                 "/baggrund": "Telefonen har hentet baggrundsbilledet …",
                 "/fl-update.apk": "Telefonen har hentet FL-UPDATE …"}.get(sti)
        if tekst and not self.klargjort:
            self.status.setText(self.status.text() + "\n✔ " + tekst)

    def _modtag_rapport(self, rapport: dict):
        resultat = udfoer(self, self.service.registrer_klargjort, self.klargoering, rapport)
        if resultat is FEJL:
            return
        self.klargjort = True
        fejl = rapport.get("fejl") or []
        tekst = (f"✔ {resultat.navn} er klargjort: {resultat.visningsmodel}, "
                 f"serienr. {resultat.serienummer or '–'}, IMEI {resultat.imei or '–'}.")
        if rapport.get("fl_update"):
            tekst += f"\nFL-UPDATE installeret ({rapport['fl_update']})."
        else:
            tekst += "\n\n⚠ FL-UPDATE blev IKKE installeret – se fejlen nedenfor og klargør igen."
        if fejl:
            tekst += "\n\nTelefonen meldte fejl:\n• " + "\n• ".join(str(f) for f in fejl)
        self.status.setText(tekst)

    def _stop_server(self):
        if self.server is not None:
            self.server.stop()
            self.server = None

    def done(self, resultat):
        self._stop_server()
        super().done(resultat)


class OpdateringDialog(QDialog):
    """Opdater telefoner: serverer styrings-appen, så klargjorte telefoner (v4+) kan hente den
    nye version fra administrator-menuen – uden nulstilling. Serveren kører, mens vinduet er åbent."""

    def __init__(self, parent, apk: Path):
        super().__init__(parent)
        self.setWindowTitle("Opdater telefoner")
        self.setMinimumWidth(560)
        self._antal = 0
        self._bro = _Bro()
        self._bro.hentet.connect(self._telefon_hentede)
        # Ingen telefon melder tilbage her – engangskoden bruges ikke, men skal være hemmelig.
        self.server = KlargoeringsServer(apk, secrets.token_urlsafe(12), lambda _r: None,
                                         paa_hentning=self._bro.hentet.emit)
        adresse = QLabel("")
        adresse.setStyleSheet("font-size: 22px; font-weight: bold;")
        adresse.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status = QLabel("Venter på telefoner …")
        self.status.setWordWrap(True)
        try:
            self.server.start()
            # Alle pc'ens adresser – telefonen bruger den på samme Wi-Fi (den øverste er Wi-Fi).
            net = netvaerk()
            adresse.setText("\n".join(f"{ip}:{self.server.port}" for _navn, ip in net))
            adresse.setToolTip("\n".join(f"{navn}: {ip}" for navn, ip in net))
        except OSError as fejl:
            self.server = None
            self.status.setText(f"Serveren kunne ikke starte ({fejl}). Er port 8765 optaget af "
                                "et andet IN-BASE-vindue?")
        trin = QLabel(
            "<ol style='margin-left:-20px'>"
            "<li>Telefonen skal være på samme Wi-Fi som denne pc.</li>"
            "<li>Åbn <b>IN-BASE indstillinger</b> på telefonen (eller tast *#*#46227#*#*).</li>"
            "<li>Indtast telefonens <b>nulstillingskode</b> og pc'ens adresse herunder.</li>"
            "<li>Vælg <b>Opdater appen fra IN-BASE</b>. Telefonen henter og installerer den nye "
            "version og lægger reglerne på igen.</li>"
            "</ol>")
        trin.setWordWrap(True)
        trin.setTextFormat(Qt.TextFormat.RichText)
        note = QLabel("Virker kun på telefoner klargjort med IN-BASE Klargøring 4.0 eller nyere. "
                      "Ældre telefoner skal fabriksnulstilles og klargøres igen.")
        note.setObjectName("hjaelpTekst")
        note.setWordWrap(True)
        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knapper.button(QDialogButtonBox.StandardButton.Close).setText("Luk")
        knapper.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(trin)
        layout.addWidget(QLabel("Pc'ens adresse (brug den første – pc'ens Wi-Fi):"))
        layout.addWidget(adresse)
        layout.addWidget(self.status)
        layout.addWidget(note)
        layout.addWidget(knapper)

    def _telefon_hentede(self, sti: str):
        if sti == "/inbase-klargoering.apk":
            self._antal += 1
            self.status.setText(f"✔ {self._antal} telefon(er) har hentet den nye version.")

    def done(self, resultat):
        if self.server is not None:
            self.server.stop()
            self.server = None
        super().done(resultat)
