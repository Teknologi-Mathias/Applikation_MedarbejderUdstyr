"""Dialoger til Telefoner (MDM): oplysninger om en telefon, klargøring med QR-kode, Find telefon
og Lås skærmlåsen op.

Regler ligger i MdmService – dialogerne viser og indsamler. Klargøringsdialogen
starter den midlertidige server (app/infrastructure/mdm/lokal_server.py), mens
den er åben, og stopper den igen, når den lukkes.
"""
import secrets
from pathlib import Path

from PySide6.QtCore import QObject, QRegularExpression, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QImage,
    QPainter,
    QPixmap,
    QRegularExpressionValidator,
)
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.domain import mdm_enhed as md
from app.infrastructure.mdm.lokal_server import KlargoeringsServer, netvaerk
from app.infrastructure.mdm.qr import qr_matrix
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.ui.baggrund import koer_i_baggrund
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_info, lav_knap, med_info, vis_dato

QR_STOERRELSE = 460
WIFI_TYPER = ("WPA", "WEP", "NONE")
FIND_INTERVAL_MS = 30_000          # Find telefon: hent den ene telefon igen, mens vinduet er åbent


def vis_tid(tekst: str) -> str:
    """"2026-11-04T14:32:10" -> "04-11-2026 14:32"."""
    return f"{vis_dato(tekst[:10])} {tekst[11:16]}".strip() if tekst else ""


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
            form.addRow(med_info(etiket, "Telefonens navn i ERP, fx ISM589. Vises på låseskærmen "
                                 "og bruges til Find telefon og oplåsning. Tildeling til en "
                                 "medarbejder sker i ERP, ikke her.")
                        if noegle == "navn" else etiket, self.felter[noegle])
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
        form.addRow(med_info("Wi-Fi (SSID)", "Netværket, telefonen kobler på under "
                             "klargøringen. Det skal være samme net som pc'en. Telefonen husker "
                             "det bagefter."), self.ssid)
        form.addRow("Wi-Fi-kode", kode_raekke)
        form.addRow("Sikkerhed", self.sikkerhed)
        form.addRow(med_info("FL-UPDATE *", "Frode Laursens installationsapp. Telefonen henter den "
                             "fra pc'en og installerer den. Bagefter henter FL-UPDATE selv "
                             "FL-TMS. Filen ændres ikke."), kilde_raekke)
        form.addRow("", fl_raekke)
        form.addRow("Baggrundsbillede", baggrund_raekke)
        form.addRow(med_info("Ekstra apps", "Pakkenavne på apps, der ellers bliver skjult, adskilt "
                             "med komma, fx com.google.android.apps.photos. Kun apps, der "
                             "allerede findes på telefonen."), self.ekstra_apps)
        form.addRow(med_info("Kontakt (låseskærm)", "Vises på låseskærmen og når brugeren rammer "
                             "en spærret funktion. Skriv hvem der hjælper, og et nummer."),
                    self.kontakt)
        form.addRow("", med_info(self.mail, "Gmail-appen bliver synlig, så en IMAP-konto kan "
                                 "tilføjes. Google-konti er stadig spærret. Kan slås til og fra "
                                 "senere uden nulstilling (Handling → Slå firma-mail til)."))

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
    """Opdater telefoner.

    Automatisk (styrings-app 8.0+): "Udgiv til alle telefoner" lægger appen i Supabase
    (migrering 026), og telefonerne henter og installerer den selv ved deres næste tjek – uden
    kode og uden pc i nærheden.

    Manuelt (ældre telefoner, én gang): serverer styrings-appen fra denne pc, så klargjorte
    telefoner (v4+) kan hente den nye version fra administrator-menuen på samme Wi-Fi. Serveren
    kører, mens vinduet er åbent."""

    def __init__(self, parent, service, apk: Path, enheder=()):
        super().__init__(parent)
        self.setWindowTitle("Opdater telefoner")
        self.setMinimumWidth(600)
        self.service = service
        self.enheder = list(enheder)
        self._antal = 0
        self._bro = _Bro()
        self._bro.hentet.connect(self._telefon_hentede)

        auto_titel = QLabel("<b>Automatisk</b> – telefoner med styrings-app 8.0 eller nyere")
        self.auto_status = QLabel("")
        self.auto_status.setWordWrap(True)
        self.udgiv = lav_knap("Udgiv til alle telefoner", "primary")
        self.udgiv.clicked.connect(self._udgiv)
        udgiv_raekke = QHBoxLayout()
        udgiv_raekke.addWidget(self.udgiv)
        udgiv_raekke.addWidget(lav_info(
            "Appen lægges i Supabase. Hver telefon ser den ved sit næste tjek (oplåsning, lader "
            "eller senest inden for en time), henter den (ca. 2 MB, også over mobildata) og "
            "installerer den selv – uden kode. Android installerer kun en app, der er signeret "
            "med jeres nøgle. Kolonnen App på Telefoner viser, hvilke der er opdateret."))
        udgiv_raekke.addStretch()

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
        manuel_titel = QLabel("<b>Manuelt</b> – ældre telefoner (én gang, derefter automatisk)")
        trin = QLabel(
            "<ol style='margin-left:-20px'>"
            "<li>Telefonen skal være på samme Wi-Fi som denne pc.</li>"
            "<li>Åbn <b>IN-BASE indstillinger</b> på telefonen (eller tast *#*#46227#*#*).</li>"
            "<li>Indtast telefonens <b>nulstillingskode</b> – eller <b>masterkoden</b>, der virker "
            "på alle telefoner – og pc'ens adresse herunder.</li>"
            "<li>Vælg <b>Opdater appen fra IN-BASE</b>. Telefonen henter og installerer den nye "
            "version og lægger reglerne på igen.</li>"
            "</ol>")
        trin.setWordWrap(True)
        trin.setTextFormat(Qt.TextFormat.RichText)
        note = QLabel("Virker kun på telefoner klargjort med IN-BASE Klargøring 4.0 eller nyere. "
                      "Ældre telefoner skal fabriksnulstilles og klargøres igen. Masterkoden står "
                      "i android/masterkode.txt hos den, der bygger styrings-appen.")
        note.setObjectName("hjaelpTekst")
        note.setWordWrap(True)
        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knapper.button(QDialogButtonBox.StandardButton.Close).setText("Luk")
        knapper.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(auto_titel)
        layout.addWidget(self.auto_status)
        layout.addLayout(udgiv_raekke)
        layout.addSpacing(16)
        layout.addWidget(manuel_titel)
        layout.addWidget(trin)
        layout.addWidget(QLabel("Pc'ens adresse (brug den første – pc'ens Wi-Fi):"))
        layout.addWidget(adresse)
        layout.addWidget(self.status)
        layout.addWidget(note)
        layout.addWidget(knapper)
        try:
            self._vis_auto(self.service.app_udgivet())
        except (DataFejl, ValideringsFejl) as fejl:      # fx migrering 026 ikke kørt
            self.auto_status.setText(f"Automatisk opdatering er ikke tilgængelig: {fejl}")
            self.udgiv.setEnabled(False)

    def _vis_auto(self, udgivet: dict) -> None:
        pc = self.service.app_paa_pc()
        linjer = [f"På denne pc: {pc['version']}." if pc else
                  "Versionen af styrings-appen på denne pc kendes ikke – byg den igen."]
        if udgivet:
            opdateret = sum(1 for e in self.enheder if e.app_version == udgivet["version"])
            linjer.append(f"Udgivet til telefonerne: {udgivet['version']} "
                          f"({vis_tid(udgivet['udgivet'])}, {udgivet['udgivet_af']}). "
                          f"{opdateret} af {len(self.enheder)} telefoner har den.")
        else:
            linjer.append("Ingen version er udgivet endnu.")
        self.auto_status.setText(" ".join(linjer))
        nyere = bool(pc) and pc["version_kode"] > udgivet.get("version_kode", 0)
        self.udgiv.setEnabled(nyere)
        self.udgiv.setText(f"Udgiv {pc['version']} til alle telefoner" if nyere
                           else "Den nyeste version er udgivet")

    def _udgiv(self) -> None:
        pc = self.service.app_paa_pc()
        if QMessageBox.question(
                self, "Udgiv til alle telefoner",
                f"Udgive styrings-app {pc.get('version', '')} til alle telefoner?\n\n"
                "Telefonerne installerer den selv ved deres næste tjek. Afprøv den først på en "
                "testtelefon (manuelt herunder).") != QMessageBox.StandardButton.Yes:
            return
        udgivet = udfoer(self, self.service.udgiv_app)
        if udgivet is not FEJL:
            self._vis_auto(udgivet)

    def _telefon_hentede(self, sti: str):
        if sti == "/inbase-klargoering.apk":
            self._antal += 1
            self.status.setText(f"✔ {self._antal} telefon(er) har hentet den nye version.")

    def done(self, resultat):
        if self.server is not None:
            self.server.stop()
            self.server = None
        super().done(resultat)


class _AnmodningDialog(QDialog):
    """Fælles for Find telefon og Lås skærmlåsen op: venter på telefonens svar.

    Telefonen kan ikke kaldes udefra – den svarer ved sit næste tjek (forkert mønster, oplåsning,
    lader/pc, nettet tilbage eller én gang i timen). Mens vinduet er åbent, hentes kun den ene
    telefon hvert 30. sekund. Lukkes vinduet, står anmodningen fortsat.

    Underklasser sætter FELT (anmodningen på MdmEnhed) og ANMOD/ANNULLER (MdmService-metoder),
    tilføjer egne knapper i self.raekke og viser resultatet i _vis()."""
    FELT = ANMOD = ANNULLER = ""

    def __init__(self, parent, service, enhed, titel: str, note: str):
        super().__init__(parent)
        self.service = service
        self.enhed = enhed
        self.setWindowTitle(f"{titel} – {enhed.navn}")
        self.setMinimumWidth(520)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.igen = lav_knap("Prøv igen")
        self.igen.clicked.connect(self._anmod_igen)
        self.annuller = lav_knap("Annullér anmodning")
        self.annuller.clicked.connect(self._annuller)
        note_label = QLabel(note)
        note_label.setObjectName("hjaelpTekst")
        note_label.setWordWrap(True)
        knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        knapper.button(QDialogButtonBox.StandardButton.Close).setText("Luk")
        knapper.rejected.connect(self.reject)
        self.raekke = QHBoxLayout()
        self.raekke.addWidget(self.igen)
        self.raekke.addWidget(self.annuller)
        self.raekke.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addWidget(self.status)
        layout.addLayout(self.raekke)
        layout.addWidget(note_label)
        layout.addWidget(knapper)
        self._timer = QTimer(self)
        self._timer.setInterval(FIND_INTERVAL_MS)
        self._timer.timeout.connect(self._hent)
        self._timer.start()

    @property
    def anmodet(self) -> str:
        return getattr(self.enhed, self.FELT)

    def _vis(self) -> None:
        self.annuller.setVisible(bool(self.anmodet))
        self.igen.setVisible(not self.anmodet)

    def _vis_linjer(self, linjer: list[str]) -> None:
        if self.enhed.senest_set:
            linjer.append(f"Senest set: {vis_tid(self.enhed.senest_set)}.")
        self.status.setText("<br><br>".join(linjer) or "Ingen anmodning.")

    def _hent(self) -> None:
        if not self.anmodet:
            return
        koer_i_baggrund(self.service.hent, self.enhed, naar_faerdig=self._hentet,
                        ved_fejl=lambda fejl: None)     # prøver igen om 30 sekunder

    def _hentet(self, enhed) -> None:
        if enhed is not None and self.isVisible():
            self.enhed = enhed
            self._vis()

    def _anmod_igen(self) -> None:
        enhed = udfoer(self, getattr(self.service, self.ANMOD), self.enhed)
        if enhed is not FEJL:
            self.enhed = enhed
            self._vis()

    def _annuller(self) -> None:
        if udfoer(self, getattr(self.service, self.ANNULLER), self.enhed) is not FEJL:
            self.enhed = md.MdmEnhed.fra_dict({**self.enhed.til_dict(), self.FELT: ""})
            self._vis()

    def done(self, resultat):
        self._timer.stop()
        super().done(resultat)


class FindTelefonDialog(_AnmodningDialog):
    """Find telefon: venter på telefonens svar og viser positionen."""
    FELT, ANMOD, ANNULLER = "find_anmodet", "find_telefon", "annuller_find"

    def __init__(self, parent, service, enhed):
        super().__init__(
            parent, service, enhed, "Find telefon",
            "Telefonen svarer, når skærmen tændes, når den kommer på nettet igen, eller senest "
            "inden for ca. en time. Ligger den slukket eller uden dækning, svarer den, så snart "
            "den er tilbage. Kræver IN-BASE Klargøring 7.0.")
        self.igen.setText("Find igen")
        self.kort = lav_knap("Åbn i kort", "primary")
        self.kort.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._link())))
        self.kopier = lav_knap("Kopiér link")
        self.kopier.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._link()))
        self.raekke.insertWidget(0, self.kort)
        self.raekke.insertWidget(1, self.kopier)
        self._vis()

    def _link(self) -> str:
        return md.kortlink(self.enhed.position)

    def _vis(self) -> None:
        super()._vis()
        e, pos = self.enhed, self.enhed.position
        linjer = []
        if e.find_anmodet:
            linjer.append(f"<b>Venter på {e.navn}</b> – anmodet {vis_tid(e.find_anmodet)}.")
        if pos.get("fejl"):
            linjer.append(f"Telefonen svarede {vis_tid(pos.get('modtaget', ''))}, men fandt "
                          f"ingen position: {pos['fejl']}")
        elif self._link():
            hvornaar = "Seneste kendte position" if e.find_anmodet else "Position"
            detaljer = ", ".join(d for d in (
                f"±{pos['noejagtighed']} m" if pos.get("noejagtighed") is not None else "",
                f"batteri {pos['batteri']} %" if pos.get("batteri") is not None else "") if d)
            linjer.append(f"<b>{hvornaar}</b> {vis_tid(pos.get('modtaget', ''))}: "
                          f"{pos['lat']:.5f}, {pos['lng']:.5f}"
                          + (f" ({detaljer})" if detaljer else ""))
        self._vis_linjer(linjer)
        self.kort.setEnabled(bool(self._link()))
        self.kopier.setEnabled(bool(self._link()))


class LaasOpDialog(_AnmodningDialog):
    """Lås skærmlåsen op (glemt mønster): telefonen sætter skærmlåskoden som midlertidig PIN."""
    FELT, ANMOD, ANNULLER = "laas_op_anmodet", "laas_op", "annuller_laas_op"

    def __init__(self, parent, service, enhed, pin: str):
        super().__init__(
            parent, service, enhed, "Lås skærmlåsen op",
            "Telefonen skal have mobildata eller et kendt Wi-Fi. Kræver IN-BASE Klargøring 8.0, "
            "og at telefonen er låst op én gang efter opdateringen (så melder den klar).")
        self.pin = pin
        self._vis()

    def _vis(self) -> None:
        super()._vis()
        e, svar = self.enhed, self.enhed.laas_op_svar
        linjer = []
        if not e.laas_op_klar:
            linjer.append(f"⚠ {e.navn} har ikke meldt klar til oplåsning. Den er måske ikke "
                          "opdateret til version 8.0 eller ikke låst op siden opdateringen – så "
                          "virker det ikke.")
        if e.laas_op_anmodet:
            linjer.append(
                f"<b>Venter på {e.navn}</b> – anmodet {vis_tid(e.laas_op_anmodet)}.<br>"
                "Bed brugeren om at <b>tegne et forkert mønster</b> eller <b>sætte telefonen i "
                "laderen eller en pc</b>. Så tjekker den med det samme – ellers inden for en time.")
        elif svar.get("ok"):
            linjer.append(
                f"<b>✔ {e.navn} er låst op</b> {vis_tid(svar.get('modtaget', ''))}.<br>"
                f"Skærmlåsen er nu PIN-koden <b>{self.pin}</b>.<br><br>"
                "Sæt standardmønsteret igen:<br>"
                f"1. Lås op med PIN-koden {self.pin}.<br>"
                "2. Åbn <b>IN-BASE indstillinger</b> og indtast samme kode.<br>"
                "3. Vælg <b>Skift skærmlås (godkendt)</b> og tegn standardmønsteret.")
        elif svar.get("fejl"):
            linjer.append(f"Telefonen svarede {vis_tid(svar.get('modtaget', ''))}, men kunne "
                          f"ikke låses op: {svar['fejl']}")
        self._vis_linjer(linjer)
