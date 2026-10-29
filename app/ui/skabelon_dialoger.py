"""Editorer til de tre slags skabeloner, med forhåndsvisning og validering."""
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import afhaengighed
from app.domain import arbejdsspor as sp
from app.domain import skabelon as sk
from app.domain.behov import BETINGELSER
from app.domain.onboarding import OnboardingForloeb
from app.ui.hjaelpere import lav_knap, lav_kort


def _gem_annuller(dialog):
    knapper = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    gem = knapper.button(QDialogButtonBox.StandardButton.Save)
    gem.setText("Gem skabelon")
    gem.setProperty("variant", "primary")
    knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
    knapper.accepted.connect(dialog.accept)
    knapper.rejected.connect(dialog.reject)
    return knapper


def _fejl_label():
    label = QLabel("")
    label.setObjectName("advarsel")
    label.setWordWrap(True)
    label.setVisible(False)
    return label


def _vis_fejl(label, fejl, overskrift):
    label.setText(overskrift + "\n• " + "\n• ".join(fejl) if fejl else "")
    label.setVisible(bool(fejl))


class VariabelPanel(QWidget):
    """Knapper der indsætter {variabel} i det tekstfelt, der har fokus."""

    def __init__(self, variabler, felter, standard_felt):
        super().__init__()
        self.felter = felter
        self.standard_felt = standard_felt

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        titel = QLabel("Variabler – klik for at indsætte")
        titel.setObjectName("hjaelpTekst")
        layout.addWidget(titel)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (navn, forklaring) in enumerate(variabler.items()):
            knap = QPushButton(f"{{{navn}}}")
            knap.setToolTip(forklaring)
            # Uden fokus på knappen bliver markøren i tekstfeltet.
            knap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            knap.setCursor(Qt.CursorShape.PointingHandCursor)
            knap.setStyleSheet("padding: 4px 8px; font-weight: 500; font-size: 12px;")
            knap.clicked.connect(lambda _=False, n=navn: self._indsaet(n))
            grid.addWidget(knap, i // 3, i % 3)
        layout.addLayout(grid)

    def _indsaet(self, navn):
        felt = QApplication.focusWidget()
        if felt not in self.felter:
            felt = self.standard_felt
        if isinstance(felt, QPlainTextEdit):
            felt.insertPlainText(f"{{{navn}}}")
        else:
            felt.insert(f"{{{navn}}}")
        felt.setFocus()


### ----- mails --------------------------------------------------------------

class MailSkabelonDialog(QDialog):
    """Efter exec(): self.skabelon er den redigerede skabelon (dict)."""

    def __init__(self, parent, skabelon, medarbejdere):
        super().__init__(parent)
        self.skabelon = dict(skabelon)
        self.medarbejdere = [m for m in medarbejdere if m.manglende_udstyr()]
        self.setWindowTitle("Mailskabelon")
        self.setMinimumSize(1060, 660)

        self.navn_input = QLineEdit(self.skabelon["navn"])
        self.kategori_input = QComboBox()
        self.kategori_input.addItems(sk.MAIL_KATEGORIER)
        self.kategori_input.setCurrentText(self.skabelon["kategori"])
        self.tone_input = QComboBox()
        self.tone_input.addItems(sk.TONER)
        self.tone_input.setCurrentText(self.skabelon["tone"])
        self.frist_input = QSpinBox()
        self.frist_input.setRange(1, 90)
        self.frist_input.setSuffix(" dage")
        self.frist_input.setValue(int(self.skabelon.get("frist_dage", 7)))
        self.aktiv_input = QCheckBox("Aktiv (kan vælges ved rykkere)")
        self.aktiv_input.setChecked(self.skabelon["aktiv"])
        self.emne_input = QLineEdit(self.skabelon["emne"])
        self.broedtekst_input = QPlainTextEdit(self.skabelon["broedtekst"])

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("Navn", self.navn_input)
        form.addRow("Kategori", self.kategori_input)
        form.addRow("Tone", self.tone_input)
        form.addRow("Standardfrist", self.frist_input)
        form.addRow("", self.aktiv_input)
        form.addRow("Emne", self.emne_input)

        venstre = QVBoxLayout()
        venstre.setSpacing(10)
        venstre.addLayout(form)
        venstre.addWidget(QLabel("Brødtekst"))
        venstre.addWidget(self.broedtekst_input, 1)
        venstre.addWidget(VariabelPanel(
            sk.MAIL_VARIABLER, (self.emne_input, self.broedtekst_input), self.broedtekst_input
        ))

        # Forhåndsvisning
        self.eksempel_input = QComboBox()
        self.eksempel_input.addItem("Fiktiv eksempelperson")
        for m in self.medarbejdere:
            self.eksempel_input.addItem(f"{m.navn} (lønnr. {m.loennr})")
        self.vis_emne = QLineEdit()
        self.vis_emne.setReadOnly(True)
        self.vis_tekst = QPlainTextEdit()
        self.vis_tekst.setReadOnly(True)
        self.vis_fejl = _fejl_label()

        kort = lav_kort(skygge=False)
        kort.setObjectName("forhaandsvisning")
        hoejre = QVBoxLayout(kort)
        hoejre.setContentsMargins(16, 14, 16, 14)
        hoejre.setSpacing(8)
        titel = QLabel("Forhåndsvisning")
        titel.setObjectName("sektionTitel")
        forklaring = QLabel(
            "Vælg en rigtig medarbejder med manglende udstyr for at se den "
            "færdige besked. Frist = i dag + standardfrist."
        )
        forklaring.setObjectName("hjaelpTekst")
        forklaring.setWordWrap(True)
        hoejre.addWidget(titel)
        hoejre.addWidget(forklaring)
        hoejre.addWidget(self.eksempel_input)
        hoejre.addWidget(self.vis_emne)
        hoejre.addWidget(self.vis_tekst, 1)
        hoejre.addWidget(self.vis_fejl)

        indhold = QHBoxLayout()
        indhold.setSpacing(18)
        indhold.addLayout(venstre, 1)
        indhold.addWidget(kort, 1)

        self.fejl_label = _fejl_label()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(indhold, 1)
        layout.addWidget(self.fejl_label)
        layout.addWidget(_gem_annuller(self))

        for signal in (
            self.emne_input.textChanged, self.broedtekst_input.textChanged,
            self.eksempel_input.currentIndexChanged, self.frist_input.valueChanged,
        ):
            signal.connect(self._opdater)
        self._opdater()

    def _data(self):
        return dict(
            self.skabelon,
            navn=self.navn_input.text().strip(),
            kategori=self.kategori_input.currentText(),
            tone=self.tone_input.currentText(),
            frist_dage=self.frist_input.value(),
            aktiv=self.aktiv_input.isChecked(),
            emne=self.emne_input.text().strip(),
            broedtekst=self.broedtekst_input.toPlainText(),
        )

    def _opdater(self):
        index = self.eksempel_input.currentIndex()
        medarbejder = (
            self.medarbejdere[index - 1] if index > 0 else sk.eksempel_medarbejder()
        )
        data = self._data()
        frist = (date.today() + timedelta(days=data["frist_dage"])).isoformat()
        emne, tekst, fejl = sk.byg_mail(data, medarbejder, frist)
        self.vis_emne.setText(emne)
        self.vis_tekst.setPlainText(tekst)
        _vis_fejl(self.vis_fejl, fejl, "Beskeden ville blive afvist:")

    def accept(self):
        data = self._data()
        fejl = []
        if not data["navn"]:
            fejl.append("Skabelonen skal have et navn.")
        if not data["emne"]:
            fejl.append("Skabelonen skal have et emne.")
        ukendte = sk.brugte_variabler(data["emne"], data["broedtekst"]) - set(sk.MAIL_VARIABLER)
        fejl += [f"Ukendt variabel {{{v}}}." for v in sorted(ukendte)]
        _vis_fejl(self.fejl_label, fejl, "Skabelonen kan ikke gemmes:")
        if fejl:
            return
        self.skabelon = data
        super().accept()


### ----- påmindelser --------------------------------------------------------

class PaamindelseDialog(QDialog):
    """Skabelon til Windows-notifikation, knyttet til en foruddefineret regel."""

    def __init__(self, parent, skabelon, vis_testnotifikation=None):
        super().__init__(parent)
        self.skabelon = dict(skabelon)
        self.vis_testnotifikation = vis_testnotifikation
        self.setWindowTitle("Påmindelse (Windows-notifikation)")
        self.setMinimumSize(900, 560)

        self.navn_input = QLineEdit(self.skabelon["navn"])
        self.regel_input = QComboBox()
        self.regel_noegler = list(sk.REGLER)
        for noegle in self.regel_noegler:
            self.regel_input.addItem(sk.REGLER[noegle][0])
        if self.skabelon["regel"] in self.regel_noegler:
            self.regel_input.setCurrentIndex(self.regel_noegler.index(self.skabelon["regel"]))
        self.dage_input = QSpinBox()
        self.dage_input.setRange(0, 365)
        self.dage_input.setSuffix(" dage")
        self.dage_input.setValue(int(self.skabelon.get("dage", 0)))
        self.gentag_input = QSpinBox()
        self.gentag_input.setRange(0, 365)
        self.gentag_input.setSpecialValueText("Kun én gang")
        self.gentag_input.setSuffix(" dage")
        self.gentag_input.setValue(int(self.skabelon.get("gentag_dage", 1)))
        self.aktiv_input = QCheckBox("Aktiv (vises som Windows-notifikation)")
        self.aktiv_input.setChecked(self.skabelon["aktiv"])
        self.titel_input = QLineEdit(self.skabelon["titel"])
        self.tekst_input = QPlainTextEdit(self.skabelon["tekst"])
        self.tekst_input.setMaximumHeight(110)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("Navn", self.navn_input)
        form.addRow("Regel", self.regel_input)
        form.addRow("X =", self.dage_input)
        form.addRow("Gentag efter", self.gentag_input)
        form.addRow("", self.aktiv_input)
        form.addRow("Titel", self.titel_input)
        form.addRow("Tekst", self.tekst_input)

        venstre = QVBoxLayout()
        venstre.addLayout(form)
        venstre.addWidget(VariabelPanel(
            sk.PAAMINDELSE_VARIABLER, (self.titel_input, self.tekst_input), self.tekst_input
        ))
        venstre.addStretch()

        kort = lav_kort(skygge=False)
        kort.setObjectName("forhaandsvisning")
        hoejre = QVBoxLayout(kort)
        hoejre.setContentsMargins(16, 14, 16, 14)
        hoejre.setSpacing(8)
        titel = QLabel("Forhåndsvisning")
        titel.setObjectName("sektionTitel")
        self.vis_titel = QLabel()
        self.vis_titel.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.vis_titel.setWordWrap(True)
        self.vis_tekst = QLabel()
        self.vis_tekst.setWordWrap(True)
        self.vis_fejl = _fejl_label()
        hoejre.addWidget(titel)
        hoejre.addWidget(self.vis_titel)
        hoejre.addWidget(self.vis_tekst)
        hoejre.addWidget(self.vis_fejl)
        hoejre.addStretch()
        if vis_testnotifikation:
            test_knap = lav_knap("Vis som testnotifikation")
            test_knap.clicked.connect(
                lambda: vis_testnotifikation(self.vis_titel.text(), self.vis_tekst.text())
            )
            hoejre.addWidget(test_knap)

        indhold = QHBoxLayout()
        indhold.setSpacing(18)
        indhold.addLayout(venstre, 3)
        indhold.addWidget(kort, 2)

        self.fejl_label = _fejl_label()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(indhold, 1)
        layout.addWidget(self.fejl_label)
        layout.addWidget(_gem_annuller(self))

        for signal in (
            self.titel_input.textChanged, self.tekst_input.textChanged,
            self.regel_input.currentIndexChanged, self.dage_input.valueChanged,
        ):
            signal.connect(self._opdater)
        self._opdater()

    def _data(self):
        return dict(
            self.skabelon,
            navn=self.navn_input.text().strip(),
            regel=self.regel_noegler[self.regel_input.currentIndex()],
            dage=self.dage_input.value(),
            gentag_dage=self.gentag_input.value(),
            aktiv=self.aktiv_input.isChecked(),
            titel=self.titel_input.text().strip(),
            tekst=self.tekst_input.toPlainText().strip(),
        )

    def _opdater(self):
        data = self._data()
        self.dage_input.setEnabled(sk.REGLER[data["regel"]][1])
        eksempel = {
            "navn": "Mette Jensen",
            "opgave": "Modtag telefon og SIM-kort",
            "ansvarlig": "IT",
            "frist": (date.today() - timedelta(days=3)).strftime("%d-%m-%Y"),
            "dage": str(data["dage"] or 3),
            "manglende_udstyr": "Telefon og SIM-kort, Tøj",
        }
        titel, fejl1 = sk.flet(data["titel"], eksempel, sk.PAAMINDELSE_VARIABLER)
        tekst, fejl2 = sk.flet(data["tekst"], eksempel, sk.PAAMINDELSE_VARIABLER)
        self.vis_titel.setText(titel)
        self.vis_tekst.setText(tekst)
        _vis_fejl(self.vis_fejl, fejl1 + fejl2, "Fejl i teksten:")

    def accept(self):
        data = self._data()
        fejl = []
        if not data["navn"]:
            fejl.append("Skabelonen skal have et navn.")
        if not data["titel"]:
            fejl.append("Notifikationen skal have en titel.")
        ukendte = sk.brugte_variabler(data["titel"], data["tekst"]) - set(sk.PAAMINDELSE_VARIABLER)
        fejl += [f"Ukendt variabel {{{v}}}." for v in sorted(ukendte)]
        _vis_fejl(self.fejl_label, fejl, "Skabelonen kan ikke gemmes:")
        if fejl:
            return
        self.skabelon = data
        super().accept()


### ----- sager (udstyr ved oprettelse) --------------------------------------

# Kolonner i skabelonens opgavetabel: (felt, overskrift, slags, bredde).
# Onboarding har arbejdsspor (nøgle, spor, afdeling, forudsætninger, betingelse);
# offboarding har udstyr. Felter uden kolonne bevares uændret ved gem.
_ONBOARDING_KOLONNER = (
    ("navn", "Opgave", "tekst", 210), ("noegle", "Nøgle", "tekst", 120),
    ("spor", "Spor", "spor", 110), ("afdeling", "Afdeling", "afdeling", 120),
    ("afhaenger_af", "Afhænger af (nøgler)", "liste", 170),
    ("betingelse", "Betingelse", "betingelse", 140), ("milepael", "Milepæl", "milepael", 140),
    ("frist_dage", "Frist (dage)", "tekst", 80), ("beskrivelse", "Beskrivelse", "tekst", 200),
    ("obligatorisk", "Obligatorisk", "flueben", 0),
)
_OFFBOARDING_KOLONNER = (
    ("navn", "Opgave", "tekst", 230), ("beskrivelse", "Beskrivelse", "tekst", 220),
    ("udstyr", "Udstyr (tom = intern)", "tekst", 170), ("ansvarlig", "Ansvarlig", "tekst", 130),
    ("frist_dage", "Frist (dage)", "tekst", 90), ("obligatorisk", "Obligatorisk", "flueben", 0),
)
POST_ROLE = Qt.ItemDataRole.UserRole + 10
RAEKKE_HOEJDE = 42          # px – drop down-cellerne skal kunne ses helt
COMBO_EKSTRA = 86           # px ud over teksten: cellens kant, padding, drop-pil og luft (theme.py)


class SagSkabelonDialog(QDialog):
    """Arbejdsgangsskabelon (onboarding eller offboarding).

    Offboarding: kolonnen Udstyr. Onboarding: arbejdsspor – nøgle, spor,
    afdeling, forudsætninger (andre opgavers nøgler), betingelse (HR's behov) og
    milepæl – samt valg af stillinger. Gemmes som en ny version (se SkabelonService),
    som afviser cirkulære og ukendte forudsætninger.
    """

    def __init__(self, parent, skabelon):
        super().__init__(parent)
        self.skabelon = dict(skabelon)
        self.onboarding = self.skabelon.get("proces") == OnboardingForloeb.PROCES
        self.milepaele = OnboardingForloeb.MILEPAELE if self.onboarding else ()
        self.felter = _ONBOARDING_KOLONNER if self.onboarding else _OFFBOARDING_KOLONNER
        proces_navn = "onboarding" if self.onboarding else "offboarding"
        self.setWindowTitle(f"Skabelon – {proces_navn}")
        self.setMinimumSize(1100 if self.onboarding else 1000, 600)

        self.navn_input = QLineEdit(self.skabelon["navn"])
        self.beskrivelse_input = QLineEdit(self.skabelon.get("beskrivelse", ""))
        self.aktiv_input = QCheckBox("Aktiv (kan vælges ved oprettelse)")
        self.aktiv_input.setChecked(self.skabelon["aktiv"])
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.addRow("Navn", self.navn_input)
        form.addRow("Beskrivelse", self.beskrivelse_input)
        self.stilling_felter = {}
        if self.onboarding:
            raekke = QHBoxLayout()
            raekke.setSpacing(22)
            for stilling in OnboardingForloeb.STILLINGER:
                felt = QCheckBox(stilling)
                felt.setChecked(stilling in (self.skabelon.get("stillinger") or []))
                self.stilling_felter[stilling] = felt
                raekke.addWidget(felt)
            raekke.addStretch()
            form.addRow("Stillinger", raekke)
        form.addRow("", self.aktiv_input)

        version = self.skabelon.get("version", 1)
        forklaring = QLabel(
            f"Version {version}. Ændringer gemmes som version {version + 1} og påvirker kun "
            "nye forløb – igangværende sager beholder deres egne opgaver. "
            + ("Frist (dage) regnes fra ansættelsesdatoen. Opgaverne kører parallelt: en "
               "opgave kan udføres, når opgaverne under 'Afhænger af' (nøgler, adskilt med "
               "komma) er afsluttet. En betingelse gør opgaven relevant, når HR har valgt "
               "behovet. Milepælen er et kontrolpunkt for sagens status. Ingen stillinger "
               "valgt = alle stillinger."
               if self.onboarding else
               "Frist (dage) regnes fra sidste arbejdsdag – 0 = samme dag, negativ = før. "
               "Udfyld Udstyr for ting, medarbejderen skal returnere; de nævnes i rykkere.")
        )
        forklaring.setObjectName("hjaelpTekst")
        forklaring.setWordWrap(True)

        self.tabel = QTableWidget(0, len(self.felter))
        self.tabel.setHorizontalHeaderLabels([titel for _, titel, _, _ in self.felter])
        self.tabel.verticalHeader().setVisible(False)
        # Plads til drop down-cellerne (Spor, Afdeling, Betingelse, Milepæl).
        self.tabel.verticalHeader().setDefaultSectionSize(RAEKKE_HOEJDE)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        for kolonne, (_, _, _, bredde) in enumerate(self.felter):
            if bredde:
                self.tabel.setColumnWidth(kolonne, bredde)
        for post in self.skabelon["opgaver"]:
            self._tilfoej_raekke(post)

        tilfoej = lav_knap("+ Tilføj opgave")
        fjern = lav_knap("Fjern valgt", "danger")
        op = lav_knap("Flyt op")
        ned = lav_knap("Flyt ned")
        tilfoej.clicked.connect(lambda: self._tilfoej_raekke({}, fokus=True))
        fjern.clicked.connect(self._fjern)
        op.clicked.connect(lambda: self._flyt(-1))
        ned.clicked.connect(lambda: self._flyt(1))
        knaprad = QHBoxLayout()
        for knap in (tilfoej, op, ned):
            knaprad.addWidget(knap)
        knaprad.addStretch()
        knaprad.addWidget(fjern)

        self.fejl_label = _fejl_label()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(forklaring)
        layout.addLayout(knaprad)
        layout.addWidget(self.tabel, 1)
        layout.addWidget(self.fejl_label)
        layout.addWidget(_gem_annuller(self))

    def _valg(self, slags):
        """[(værdi, tekst)] til en valgliste."""
        if slags == "spor":
            return [("", "Øvrigt")] + [(n, t) for n, t in sp.SPOR if n != sp.OEVRIGT]
        if slags == "afdeling":
            return [("", "Ingen")] + [(a, a) for a in sp.AFDELINGER]
        if slags == "betingelse":
            return [("", "Altid")] + list(BETINGELSER.items())
        return [("", "Ingen")] + list(self.milepaele)

    def _tilfoej_raekke(self, post, fokus=False, raekke=None):
        raekke = self.tabel.rowCount() if raekke is None else raekke
        self.tabel.insertRow(raekke)
        for kolonne, (felt, _, slags, _) in enumerate(self.felter):
            vaerdi = post.get(felt, 0 if felt == "frist_dage" else "")
            if slags == "flueben":
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(Qt.CheckState.Checked if post.get("obligatorisk", True)
                                   else Qt.CheckState.Unchecked)
                self.tabel.setItem(raekke, kolonne, item)
            elif slags in ("spor", "afdeling", "betingelse", "milepael"):
                valg = QComboBox()
                for data, tekst in self._valg(slags):
                    valg.addItem(tekst, data)
                valg.setCurrentIndex(max(valg.findData(vaerdi or ""), 0))
                self.tabel.setCellWidget(raekke, kolonne, valg)
                # Kolonnen er mindst så bred som den længste valgmulighed (ingen afskåret
                # tekst): teksten + temaets padding, drop-pil (28 px) og margen. Temaets
                # skrift skal være lagt på, før der måles.
                valg.ensurePolished()
                laengst = max(valg.fontMetrics().horizontalAdvance(valg.itemText(i))
                              for i in range(valg.count()))
                self.tabel.setColumnWidth(kolonne, max(self.tabel.columnWidth(kolonne),
                                                       laengst + COMBO_EKSTRA))
            else:
                tekst = ", ".join(vaerdi) if slags == "liste" else str(vaerdi)
                self.tabel.setItem(raekke, kolonne, QTableWidgetItem(tekst))
        # Hele den oprindelige post gemmes, så felter uden kolonne ikke går tabt.
        self.tabel.item(raekke, 0).setData(POST_ROLE, dict(post))
        if fokus:
            self.tabel.setCurrentCell(raekke, 0)
            self.tabel.editItem(self.tabel.item(raekke, 0))

    def _raekke_data(self, raekke):
        post = dict(self.tabel.item(raekke, 0).data(POST_ROLE) or {})
        for kolonne, (felt, _, slags, _) in enumerate(self.felter):
            item = self.tabel.item(raekke, kolonne)
            if slags == "flueben":
                post[felt] = item.checkState() == Qt.CheckState.Checked
            elif slags in ("spor", "afdeling", "betingelse", "milepael"):
                post[felt] = self.tabel.cellWidget(raekke, kolonne).currentData() or ""
            elif slags == "liste":
                tekst = item.text() if item else ""
                post[felt] = [n.strip() for n in tekst.split(",") if n.strip()]
            else:
                post[felt] = item.text().strip() if item else ""
        if self.onboarding:
            post["udstyr"] = post.get("udstyr", "")
        else:
            post["milepael"] = ""
        return post

    def _fjern(self):
        raekke = self.tabel.currentRow()
        if raekke >= 0:
            self.tabel.removeRow(raekke)

    def _flyt(self, retning):
        raekke = self.tabel.currentRow()
        ny = raekke + retning
        if raekke < 0 or not 0 <= ny < self.tabel.rowCount():
            return
        data = self._raekke_data(raekke)
        self.tabel.removeRow(raekke)
        self._tilfoej_raekke(data, raekke=ny)
        self.tabel.setCurrentCell(ny, 0)

    def accept(self):
        fejl, opgaver = [], []
        navn = self.navn_input.text().strip()
        if not navn:
            fejl.append("Skabelonen skal have et navn.")
        for raekke in range(self.tabel.rowCount()):
            post = self._raekke_data(raekke)
            if not post["navn"]:
                fejl.append(f"Opgave i række {raekke + 1} mangler et navn.")
                continue
            try:
                post["frist_dage"] = int(post["frist_dage"] or 0)
            except ValueError:
                fejl.append(f"'{post['navn']}': Frist (dage) skal være et helt tal.")
                continue
            opgaver.append(post)
        fejl += afhaengighed.find_fejl(opgaver)
        _vis_fejl(self.fejl_label, fejl, "Skabelonen kan ikke gemmes:")
        if fejl:
            return
        self.skabelon = dict(
            self.skabelon, navn=navn, aktiv=self.aktiv_input.isChecked(), opgaver=opgaver,
            beskrivelse=self.beskrivelse_input.text().strip(),
            stillinger=[s for s, felt in self.stilling_felter.items() if felt.isChecked()],
        )
        super().accept()
