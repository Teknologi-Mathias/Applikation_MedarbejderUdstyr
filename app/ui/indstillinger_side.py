"""Indstillinger: personlige valg, påmindelser, organisation og (for
administratorer) brugere samt data & sikkerhed.

Alle ændringer går gennem services:
- Tema og Windows-notifikationer: IndstillingerService (pr. bruger, lokalt).
- Adgangskode: AuthService (verificerer den nuværende kode, hasher den nye).
- Arbejd offline: LagringService (kun JSON-tilstanden; i Supabase-tilstand
  forklarer kortet, at forbindelse er påkrævet).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import session
from app.domain import behov as bh
from app.domain import skabelon as sk
from app.domain.onboarding import OnboardingForloeb
from app.services.indstillinger_service import TEMAER
from app.ui.bruger_side import BrugerSide
from app.ui.data_side import DataSide
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved, scroll_side, vis_dato
from app.ui.skabelon_side import SkabelonSide


def _kort(titel, forklaring=""):
    kort = lav_kort(skygge=False)
    layout = QVBoxLayout(kort)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    titel_label = QLabel(titel)
    titel_label.setObjectName("cardTitle")
    layout.addWidget(titel_label)
    if forklaring:
        tekst = QLabel(forklaring)
        tekst.setObjectName("cardSub")
        tekst.setWordWrap(True)
        layout.addWidget(tekst)
    return kort, layout


class GenereltPanel(QWidget):
    tema_valgt = Signal(str)
    notifikationer_valgt = Signal(bool)
    lagring_skiftet = Signal()

    def __init__(self, tjenester):
        super().__init__()
        self.t = tjenester
        layout = scroll_side(self)
        layout.setContentsMargins(0, 12, 8, 12)

        # --- udseende og notifikationer ---
        kort, lag = _kort("Udseende og notifikationer",
                          "Gemmes for din bruger på denne pc.")
        form = QFormLayout()
        self.tema_input = QComboBox()
        for noegle, navn in TEMAER.items():
            self.tema_input.addItem(navn, noegle)
        self.tema_input.currentIndexChanged.connect(self._tema_valgt)
        self.notifikationer_input = QCheckBox("Vis Windows-notifikationer om påmindelser")
        self.notifikationer_input.toggled.connect(self._notifikationer_valgt)
        form.addRow("Tema", self.tema_input)
        form.addRow("", self.notifikationer_input)
        lag.addLayout(form)
        note = QLabel("Slås notifikationer fra, vises de samme ting stadig i Action Center.")
        note.setObjectName("hjaelpTekst")
        lag.addWidget(note)
        layout.addWidget(kort)

        # --- adgangskode ---
        kort, lag = _kort(
            "Skift adgangskode",
            "BETA: Adgangskoder gemmes som saltede hashes i en fil, der ikke er "
            "beskyttet. Brug ikke en privat kode." if tjenester.auth.BETA else
            f"Adgangskoden håndteres af Supabase Auth og skal være mindst "
            f"{tjenester.auth.MIN_KODE} tegn.",
        )
        form = QFormLayout()
        self.nuvaerende = QLineEdit()
        self.ny_kode = QLineEdit()
        self.gentag = QLineEdit()
        for felt in (self.nuvaerende, self.ny_kode, self.gentag):
            felt.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Nuværende kode", self.nuvaerende)
        form.addRow("Ny kode", self.ny_kode)
        form.addRow("Gentag ny kode", self.gentag)
        lag.addLayout(form)
        self.kode_status = QLabel("")
        self.kode_status.setWordWrap(True)
        knap = lav_knap("Skift adgangskode", "primary")
        knap.clicked.connect(self._skift_kode)
        raekke = QHBoxLayout()
        raekke.addWidget(self.kode_status, 1)
        raekke.addWidget(knap)
        lag.addLayout(raekke)
        layout.addWidget(kort)

        # --- forbindelse / offline ---
        if tjenester.lagring.understoetter_offline:
            kort, lag = _kort(
                "Arbejd offline",
                "Arbejd videre på en lokal kopi, hvis den centrale datamappe er ustabil "
                "eller utilgængelig. Ændringer i sager gemmes lokalt og synkroniseres, når "
                "du går online. Er en sag ændret centralt imens, overskrives intet – du "
                "afgør konflikten nedenfor. Brugere, skabeloner og fælles indstillinger kan "
                "ikke ændres offline. (Kun i den lokale JSON-tilstand.)",
            )
        else:
            kort, lag = _kort(
                "Forbindelse",
                "IN-BASE arbejder direkte i den fælles database. Alle ændringer gemmes "
                "med det samme og ses af kolleger på andre pc'er. Uden forbindelse kan "
                "der ikke arbejdes – intet gemmes lokalt, så ingen arbejder på forældede "
                "data.",
            )
        self.lagring_status = QLabel("")
        self.lagring_status.setWordWrap(True)
        self.offline_knap = lav_knap("Arbejd offline")
        self.offline_knap.clicked.connect(self._skift_lagring)
        self.offline_knap.setVisible(tjenester.lagring.understoetter_offline)
        raekke = QHBoxLayout()
        raekke.addWidget(self.lagring_status, 1)
        raekke.addWidget(self.offline_knap)
        lag.addLayout(raekke)
        self.ventende = QListWidget()
        self.ventende.setFixedHeight(110)
        ventende_label = QLabel("Ændringer, der endnu ikke er synkroniseret:")
        lag.addWidget(ventende_label)
        lag.addWidget(self.ventende)
        for widget in (ventende_label, self.ventende):
            widget.setVisible(tjenester.lagring.understoetter_offline)
        self.konflikt_label = QLabel("Konflikter fra seneste synkronisering:")
        self.konflikter = QListWidget()
        self.konflikter.setFixedHeight(110)
        brug_central = lav_knap("Behold central udgave")
        brug_min = lav_knap("Brug min offline-ændring", "danger")
        brug_central.clicked.connect(lambda: self._loes(False))
        brug_min.clicked.connect(lambda: self._loes(True))
        self.konflikt_knapper = QHBoxLayout()
        self.konflikt_knapper.addStretch()
        self.konflikt_knapper.addWidget(brug_central)
        self.konflikt_knapper.addWidget(brug_min)
        for widget in (self.konflikt_label, self.konflikter):
            lag.addWidget(widget)
        lag.addLayout(self.konflikt_knapper)
        layout.addWidget(kort)
        layout.addStretch()

    ### ----- visning --------------------------------------------------------

    def opdater(self):
        praef = self.t.indstillinger.praeference(session.brugernavn() or "")
        for felt in (self.tema_input, self.notifikationer_input):
            felt.blockSignals(True)
        self.tema_input.setCurrentIndex(max(self.tema_input.findData(praef["tema"]), 0))
        self.notifikationer_input.setChecked(bool(praef["windows_notifikationer"]))
        for felt in (self.tema_input, self.notifikationer_input):
            felt.blockSignals(False)

        lagring = self.t.lagring
        if lagring.offline:
            info = lagring.offline_info()
            self.lagring_status.setObjectName("lagringOffline")
            self.lagring_status.setText(
                f"OFFLINE – arbejder på lokal kopi fra {vis_dato(info.get('kopieret', ''))} "
                f"{info.get('kopieret', '')[11:16]}. Ændringer er IKKE gemt centralt endnu."
            )
            self.offline_knap.setText("Gå online og synkronisér")
        else:
            self.lagring_status.setObjectName("lagringOnline")
            self.lagring_status.setText(f"ONLINE – {lagring.kilde}")
            self.offline_knap.setText("Arbejd offline")
        self.lagring_status.style().unpolish(self.lagring_status)
        self.lagring_status.style().polish(self.lagring_status)

        self.ventende.clear()
        for post in lagring.ventende_aendringer():
            navn = (post.get("data") or {}).get("navn", post["sag_id"][:8])
            self.ventende.addItem(f"{post['tid'][:16].replace('T', ' ')} · {post['op']} · "
                                  f"{post['proces']} · {navn} ({post['bruger']})")
        if not self.ventende.count():
            self.ventende.addItem("Ingen")
        konflikter = lagring.konflikter()
        self.konflikter.clear()
        for k in konflikter:
            navn = (k.get("data") or {}).get("navn", k["sag_id"][:8])
            self.konflikter.addItem(f"{navn} · {k['op']} · {k.get('aarsag', '')}")
        for widget in (self.konflikt_label, self.konflikter):
            widget.setVisible(bool(konflikter))
        for i in range(self.konflikt_knapper.count()):
            widget = self.konflikt_knapper.itemAt(i).widget()
            if widget:
                widget.setVisible(bool(konflikter))

    ### ----- handlinger -----------------------------------------------------

    def _tema_valgt(self):
        tema = self.tema_input.currentData()
        if udfoer(self, self.t.indstillinger.gem_praeference, session.brugernavn(),
                  tema=tema) is not FEJL:
            self.tema_valgt.emit(tema)

    def _notifikationer_valgt(self, til):
        if udfoer(self, self.t.indstillinger.gem_praeference, session.brugernavn(),
                  windows_notifikationer=til) is not FEJL:
            self.notifikationer_valgt.emit(til)

    def _skift_kode(self):
        resultat = udfoer(self, self.t.auth.skift_egen_kode, session.brugernavn(),
                          self.nuvaerende.text(), self.ny_kode.text(), self.gentag.text())
        for felt in (self.nuvaerende, self.ny_kode, self.gentag):
            felt.clear()
        if resultat is not FEJL:
            self.kode_status.setObjectName("info")
            self.kode_status.setText("Adgangskoden er skiftet.")
        else:
            self.kode_status.setObjectName("feltFejl")
            self.kode_status.setText("Adgangskoden er IKKE skiftet.")
        self.kode_status.style().unpolish(self.kode_status)
        self.kode_status.style().polish(self.kode_status)

    def _skift_lagring(self):
        lagring = self.t.lagring
        if lagring.offline:
            resultat = udfoer(self, lagring.gaa_online)
            if resultat is not FEJL:
                tekst = f"Online igen. {resultat.anvendt} ændringer er synkroniseret."
                if resultat.konflikter:
                    tekst += (f"\n\n{len(resultat.konflikter)} ændringer var i konflikt med "
                              "ændringer foretaget centralt og er IKKE gemt. Se listen under "
                              "Indstillinger → Generelt.")
                QMessageBox.information(self, "Synkronisering", tekst)
        else:
            besked = udfoer(self, lagring.gaa_offline)
            if besked is not FEJL:
                QMessageBox.information(self, "Offline", besked)
        self.lagring_skiftet.emit()
        self.opdater()

    def _loes(self, brug_min):
        index = self.konflikter.currentRow()
        if index < 0:
            QMessageBox.information(self, "Konflikt", "Vælg en konflikt i listen først.")
            return
        udfoer(self, self.t.lagring.loes_konflikt, index, brug_min)
        self.lagring_skiftet.emit()
        self.opdater()


class UdstyrsprofilKort(QWidget):
    """Standardprofiler for udstyr pr. stilling: forvalget i "Opret kandidat".

    Kun udstyr og antal – størrelser vælges pr. person. Udstyr, stillingen ikke
    må få, kan ikke vælges. Adskilt fra arbejdsgangsskabelonerne (opgaverne)."""

    def __init__(self, tjenester):
        super().__init__()
        self.t = tjenester
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        kort, lag = _kort("Udstyrsprofiler pr. stilling",
                          "Forvælges, når HR vælger stilling under Opret kandidat. HR kan altid "
                          "tilpasse valget og vælger størrelser pr. person. En profil bestiller "
                          "intet.")
        gitter = QGridLayout()
        gitter.setHorizontalSpacing(14)
        for k, titel in enumerate(("Stilling", "Polo", "Fleece", "Telefon", "E-mail", "Firmabil")):
            label = QLabel(titel)
            label.setObjectName("statTitle")
            gitter.addWidget(label, 0, k)
        self.felter = {}
        for r, stilling in enumerate(OnboardingForloeb.STILLINGER, start=1):
            toej = {}
            for k, noegle in enumerate(bh.BEKLAEDNING, start=1):
                antal = QSpinBox()
                antal.setRange(0, bh.MAKS_ANTAL)
                antal.setSpecialValueText("Nej")
                antal.setSuffix(" stk.")
                gitter.addWidget(antal, r, k)
                toej[noegle] = antal
            telefon = QComboBox()
            telefon.addItem("Nej", "")
            for abonnement in bh.tilladte_abonnementer(stilling):
                telefon.addItem(abonnement, abonnement)
            udvidet = bh.tilladt_udvidet(stilling)
            mail, bil = QCheckBox(), QCheckBox()
            for felt in (mail, bil):
                felt.setEnabled(udvidet)
                if not udvidet:
                    felt.setToolTip("Kun for " + ", ".join(bh.UDVIDET_UDSTYR))
            # E-mailen ligger på telefonen: kan kun vælges sammen med en telefon.
            telefon.currentIndexChanged.connect(
                lambda _i, t=telefon, m=mail, u=udvidet: self._telefon_valgt(t, m, u))
            self._telefon_valgt(telefon, mail, udvidet)
            gitter.addWidget(QLabel(stilling), r, 0)
            gitter.addWidget(telefon, r, 3)
            gitter.addWidget(mail, r, 4)
            gitter.addWidget(bil, r, 5)
            self.felter[stilling] = (toej, telefon, mail, bil)
        lag.addLayout(gitter)
        gem = lav_knap("Gem profiler", "primary")
        gem.clicked.connect(self._gem)
        lag.addWidget(gem, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(kort)

    @staticmethod
    def _telefon_valgt(telefon, mail, udvidet):
        med_telefon = bool(telefon.currentData())
        if not med_telefon:
            mail.setChecked(False)
        mail.setEnabled(udvidet and med_telefon)

    def opdater(self):
        profiler = self.t.indstillinger.udstyrsprofiler()
        for stilling, (toej, telefon, mail, bil) in self.felter.items():
            p = profiler[stilling]
            for noegle, antal in toej.items():
                antal.setValue(p.toej(noegle).antal if p.toej(noegle).valgt else 0)
            telefon.setCurrentIndex(max(telefon.findData(p.abonnement if p.mobil else ""), 0))
            mail.setChecked(p.email)
            bil.setChecked(p.firmabil)

    def profiler(self) -> dict:
        resultat = {}
        for stilling, (toej, telefon, mail, bil) in self.felter.items():
            resultat[stilling] = bh.Behov(
                **{n: bh.Toej(a.value() > 0, "", a.value()) for n, a in toej.items()},
                mobil=bool(telefon.currentData()), abonnement=telefon.currentData() or "",
                email=mail.isChecked(), firmabil=bil.isChecked(),
            ).til_dict()
        return resultat

    def _gem(self):
        if udfoer(self, self.t.indstillinger.opdater,
                  udstyrsprofiler=self.profiler()) is not FEJL:
            QMessageBox.information(self, "Udstyrsprofiler", "Gemt.")


class OrganisationPanel(QWidget):
    def __init__(self, tjenester):
        super().__init__()
        self.t = tjenester
        layout = scroll_side(self)
        layout.setContentsMargins(0, 12, 8, 12)
        kort, lag = _kort("Organisation og regler",
                          "Fælles for alle brugere.")
        form = QFormLayout()
        self.omraader = QPlainTextEdit()
        self.omraader.setPlaceholderText("Ét område pr. linje")
        self.omraader.setMaximumHeight(160)
        self.ansvarlige = QPlainTextEdit()
        self.ansvarlige.setPlaceholderText("Én afdeling pr. linje")
        self.ansvarlige.setMaximumHeight(120)
        self.stille = QSpinBox()
        self.stille.setRange(1, 365)
        self.stille.setSuffix(" dage")
        self.naermer = QSpinBox()
        self.naermer.setRange(1, 90)
        self.naermer.setSuffix(" dage")
        form.addRow("Områder", self.omraader)
        form.addRow("Ansvarlige", self.ansvarlige)
        note = QLabel("Brugerne fra brugerkartoteket kan altid vælges som ansvarlig.")
        note.setObjectName("hjaelpTekst")
        form.addRow("", note)
        form.addRow("Sag uden aktivitet markeres efter", self.stille)
        form.addRow("Vis kommende datoer inden for", self.naermer)
        lag.addLayout(form)
        gem = lav_knap("Gem", "primary")
        gem.clicked.connect(self._gem)
        lag.addWidget(gem, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(kort)
        self.udstyrsprofiler = UdstyrsprofilKort(tjenester)
        layout.addWidget(self.udstyrsprofiler)
        layout.addStretch()

    def opdater(self):
        self.udstyrsprofiler.opdater()
        ind = self.t.indstillinger.hent()
        self.omraader.setPlainText("\n".join(ind["omraader"]))
        self.ansvarlige.setPlainText("\n".join(ind["ansvarlige"]))
        self.stille.setValue(int(ind["stillestaaende_dage"]))
        self.naermer.setValue(int(ind["naermer_sig_dage"]))

    def _gem(self):
        if udfoer(self, self.t.indstillinger.opdater,
                  omraader=self.omraader.toPlainText().splitlines(),
                  ansvarlige=self.ansvarlige.toPlainText().splitlines(),
                  stillestaaende_dage=self.stille.value(),
                  naermer_sig_dage=self.naermer.value()) is not FEJL:
            QMessageBox.information(self, "Organisation", "Gemt.")


class IndstillingerSide(QWidget):
    def __init__(self, tjenester, hent_arkiv, hent_sager, vis_testnotifikation):
        super().__init__()
        self.t = tjenester
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        hoved, _ = lav_sidehoved("Indstillinger", "Personlige valg og fælles opsætning.")
        layout.addLayout(hoved)

        self.generelt = GenereltPanel(tjenester)
        self.paamindelser = SkabelonSide(
            tjenester.skabeloner, [sk.PAAMINDELSE], indlejret=True,
            hent_sager=hent_sager, vis_testnotifikation=vis_testnotifikation,
        )
        self.organisation = OrganisationPanel(tjenester)
        self.brugere = BrugerSide(tjenester.auth)
        self.data = DataSide(tjenester, hent_arkiv)

        self.faner = QTabWidget()
        self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self._paneler = [
            (self.generelt, "Generelt", "Tema, notifikationer, adgangskode og offline", False),
            (self.paamindelser, "Påmindelser", "Regler for Windows-notifikationer", False),
            (self.organisation, "Organisation", "Områder, ansvarlige og regler for Action Center", False),
            (self.brugere, "Brugere", "Brugerkartotek og roller", True),
            (self.data, "Data & sikkerhed", "Backup, gendannelse og slettepolitik", True),
        ]
        for panel, navn, tip, _ in self._paneler:
            index = self.faner.addTab(panel, navn)
            self.faner.setTabToolTip(index, tip)
        self.faner.currentChanged.connect(lambda _i: self.opdater())
        layout.addWidget(self.faner, 1)

    def anvend_rolle(self, admin: bool):
        for index, (_, _, _, kun_admin) in enumerate(self._paneler):
            self.faner.setTabVisible(index, admin or not kun_admin)
        self.paamindelser.saet_redigerbar(not self.t.lagring.offline)
        if not admin and self._paneler[self.faner.currentIndex()][3]:
            self.faner.setCurrentIndex(0)

    def opdater(self):
        panel = self.faner.currentWidget()
        if hasattr(panel, "opdater"):
            panel.opdater()
