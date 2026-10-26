"""Siden Brugerkartotek: opret, (de)aktivér, skift rolle, moduladgang, nulstil kode
og slet brugere (kun administratorer).

Brugere logger på med brugernavn (fx HAFRA) – der bruges ingen e-mail. I
Supabase-tilstand opretter "Opret bruger" en rigtig Supabase Auth-konto via
Edge Function admin-create-user, og de øvrige handlinger går via
admin-manage-user (serveren tjekker, at du er aktiv administrator). Den nye
bruger får en midlertidig kode og vælger sin egen ved første log på.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import session
from app.domain import adgang
from app.domain.arbejdsspor import AFDELINGER
from app.repositories.fejl import DataFejl, ValideringsFejl
from app.services.auth_service import ROLLE_ADMIN, ROLLE_BRUGER, ROLLER
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_knap, lav_kort, lav_sidehoved, vis_dato

BETA_TEKST = (
    "BETA – Adgangskoder er IKKE sikkert gemt. Brugerfilen ligger i datamappen "
    "og kan læses af alle med adgang til den. Brug aldrig en privat adgangskode "
    "eller en kode, I bruger andre steder."
)


def _beta_label():
    label = QLabel(BETA_TEKST)
    label.setObjectName("beta")
    label.setWordWrap(True)
    return label


class KodeDialog(QDialog):
    """Opret bruger (ny=True) eller skift adgangskode for en eksisterende bruger."""

    def __init__(self, parent, auth, ny=True, brugernavn=""):
        super().__init__(parent)
        self.auth = auth
        self.ny = ny
        self.setWindowTitle("Opret bruger" if ny else f"Skift adgangskode: {brugernavn}")
        self.setMinimumWidth(480)

        self.brugernavn_input = QLineEdit(brugernavn)
        self.brugernavn_input.setPlaceholderText("fx HAFRA – bruges til at logge på")
        self.navn_input = QLineEdit()
        self.navn_input.setPlaceholderText("Visningsnavn (valgfrit)")
        self.rolle_input = QComboBox()
        self.rolle_input.addItems(ROLLER)
        self.rolle_input.setCurrentText(ROLLE_BRUGER)
        self.kode_input = QLineEdit()
        self.kode_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gentag_input = QLineEdit()
        self.gentag_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.forstaaet_input = QCheckBox(
            "Jeg har læst BETA-advarslen"
        )
        self.forstaaet_input.setVisible(auth.BETA)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        if ny:
            form.addRow("Brugernavn", self.brugernavn_input)
            form.addRow("Navn", self.navn_input)
            form.addRow("Rolle", self.rolle_input)
        form.addRow("Midlertidig kode" if auth.MIDLERTIDIG_KODE else "Adgangskode", self.kode_input)
        form.addRow("Gentag kode", self.gentag_input)

        rolle_hjaelp = QLabel(
            "Administrator: alt, inkl. brugere, skabeloner, data og sletning. "
            "Bruger: arbejder med sager, rykkere og arkiv."
        )
        rolle_hjaelp.setObjectName("hjaelpTekst")
        rolle_hjaelp.setWordWrap(True)
        kode_hjaelp = QLabel(
            f"Koden er midlertidig (mindst {auth.MIN_KODE} tegn). Giv den til brugeren "
            "på en sikker måde – brugeren skal vælge sin egen kode ved første log på."
        )
        kode_hjaelp.setObjectName("hjaelpTekst")
        kode_hjaelp.setWordWrap(True)
        kode_hjaelp.setVisible(auth.MIDLERTIDIG_KODE)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)

        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        gem = knapper.button(QDialogButtonBox.StandardButton.Save)
        gem.setText("Opret bruger" if ny else "Skift kode")
        gem.setProperty("variant", "primary")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        if auth.BETA:
            layout.addWidget(_beta_label())
        layout.addLayout(form)
        if ny:
            layout.addWidget(rolle_hjaelp)
        layout.addWidget(kode_hjaelp)
        layout.addWidget(self.forstaaet_input)
        layout.addWidget(self.fejl_label)
        layout.addWidget(knapper)

    def accept(self):
        if self.kode_input.text() != self.gentag_input.text():
            self.fejl_label.setText("De to adgangskoder er ikke ens.")
            return
        if self.auth.BETA and not self.forstaaet_input.isChecked():
            self.fejl_label.setText("Bekræft, at du har læst BETA-advarslen.")
            return
        try:
            if self.ny:
                self.auth.opret(
                    self.brugernavn_input.text(),
                    self.navn_input.text(),
                    self.rolle_input.currentText(),
                    self.kode_input.text(),
                )
            else:
                self.auth.nulstil_kode(self.brugernavn_input.text(), self.kode_input.text())
        except (ValideringsFejl, DataFejl) as fejl:   # DataFejl omfatter OfflineFejl
            self.fejl_label.setText(str(fejl))
            return
        super().accept()


class FluebenDialog(QDialog):
    """Flueben for én bruger (moduler eller afdelinger). Efter exec(): self.valgte."""

    def __init__(self, parent, titel: str, intro: str, valg: dict, valgte):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.valgte = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        intro_label = QLabel(intro)
        intro_label.setObjectName("hjaelpTekst")
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)
        self.felter = {}
        for noegle, navn in valg.items():
            felt = QCheckBox(navn)
            felt.setChecked(noegle in valgte)
            self.felter[noegle] = felt
            layout.addWidget(felt)
        knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        knapper.button(QDialogButtonBox.StandardButton.Save).setText("Gem")
        knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        knapper.accepted.connect(self.accept)
        knapper.rejected.connect(self.reject)
        layout.addWidget(knapper)

    def accept(self):
        self.valgte = [n for n, felt in self.felter.items() if felt.isChecked()]
        super().accept()


def _moduler_tekst(bruger: dict) -> str:
    if bruger.get("rolle") == ROLLE_ADMIN:
        return "Alle (administrator)"
    navne = [adgang.MODULER[m].split(" - ")[0] for m in adgang.moduler_for(bruger)]
    return ", ".join(navne) or "Ingen"


class BrugerSide(QWidget):
    def __init__(self, auth):
        super().__init__()
        self.auth = auth
        self._brugere = {}             # brugernavn -> brugerdict
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        hoved, _ = lav_sidehoved(
            "Brugerkartotek",
            "Brugere med adgang til IN-BASE og deres rolle. Kun administratorer ser denne side.",
        )
        layout.addLayout(hoved)
        if auth.BETA:
            layout.addWidget(_beta_label())

        knapper = QHBoxLayout()
        opret = lav_knap("+ Opret bruger", "primary")
        kode = lav_knap("Nulstil adgangskode")
        rolle = lav_knap("Skift rolle")
        moduler = lav_knap("Moduladgang…", tooltip="Hvilke moduler brugeren må se")
        afdelinger = lav_knap("Afdelinger…", tooltip="Hvilke afdelinger brugeren er medlem af "
                                                     "(styrer arbejdsbakken)")
        self.aktiv_knap = lav_knap("Deaktivér / aktivér",
                                   tooltip="En deaktiveret bruger kan ikke logge på og har "
                                           "ingen adgang til data")
        slet = lav_knap("Slet bruger", "danger")
        opret.clicked.connect(self.opret)
        kode.clicked.connect(self.skift_kode)
        rolle.clicked.connect(self.skift_rolle)
        moduler.clicked.connect(self.skift_moduler)
        afdelinger.clicked.connect(self.skift_afdelinger)
        self.aktiv_knap.clicked.connect(self.skift_aktiv)
        slet.clicked.connect(self.slet)
        knapper.addStretch()
        for knap in (opret, kode, rolle, moduler, afdelinger, self.aktiv_knap, slet):
            knapper.addWidget(knap)
        layout.addLayout(knapper)

        kort = lav_kort(skygge=False)
        kort_layout = QVBoxLayout(kort)
        kort_layout.setContentsMargins(8, 8, 8, 8)
        self.tabel = QTableWidget(0, 7)
        self.tabel.setHorizontalHeaderLabels(["Brugernavn", "Navn", "Rolle", "Status", "Oprettet",
                                              "Afdelinger", "Moduler"])
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setShowGrid(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(42)
        self.tabel.horizontalHeader().setStretchLastSection(True)
        for kolonne, bredde in enumerate((150, 200, 120, 110, 100, 200)):
            self.tabel.setColumnWidth(kolonne, bredde)
        kort_layout.addWidget(self.tabel)
        layout.addWidget(kort, 1)

    def opdater(self):
        alle = udfoer(self, self.auth.brugere)
        if alle is FEJL:
            return
        self._brugere = {b["brugernavn"]: b for b in alle}
        self.tabel.setRowCount(len(alle))
        for raekke, b in enumerate(alle):
            mig = b["brugernavn"] == session.brugernavn()
            celler = (
                b["brugernavn"] + ("  (dig)" if mig else ""),
                b.get("navn", ""),
                b.get("rolle", ""),
                "Aktiv" if b.get("aktiv", True) else "Deaktiveret",
                vis_dato(b.get("oprettet", "")[:10]),
                ", ".join(adgang.afdelinger_for(b)) or "–",
                _moduler_tekst(b),
            )
            for kolonne, tekst in enumerate(celler):
                item = QTableWidgetItem(tekst)
                item.setData(Qt.ItemDataRole.UserRole, b["brugernavn"])
                self.tabel.setItem(raekke, kolonne, item)

    def _valgt(self):
        rows = self.tabel.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Ingen valgt", "Vælg en bruger i listen først.")
            return None
        return self.tabel.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def opret(self):
        if KodeDialog(self, self.auth, ny=True).exec():
            self.opdater()

    def skift_kode(self):
        brugernavn = self._valgt()
        if brugernavn and KodeDialog(self, self.auth, ny=False, brugernavn=brugernavn).exec():
            QMessageBox.information(
                self, "Adgangskode",
                f"Koden for {brugernavn} er skiftet."
                + (" Brugeren skal vælge en ny kode ved næste log på."
                   if self.auth.MIDLERTIDIG_KODE else ""))

    def skift_rolle(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        nuvaerende = self._brugere.get(brugernavn, {}).get("rolle", ROLLE_BRUGER)
        rolle, ok = QInputDialog.getItem(
            self, "Skift rolle", f"Ny rolle for {brugernavn}:", list(ROLLER),
            list(ROLLER).index(nuvaerende) if nuvaerende in ROLLER else 0, False)
        if ok and rolle != nuvaerende:
            udfoer(self, self.auth.saet_rolle, brugernavn, rolle, session.brugernavn())
            self.opdater()

    def skift_moduler(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        bruger = self._brugere.get(brugernavn, {})
        if bruger.get("rolle") == ROLLE_ADMIN:
            QMessageBox.information(self, "Moduladgang",
                                    "Administratorer har altid adgang til alle moduler.")
            return
        dialog = FluebenDialog(
            self, f"Moduladgang – {brugernavn}",
            "Vælg de moduler, brugeren må se. Moduler uden adgang vises med 🔒 i "
            "menuen. Dashboard og Indstillinger kan alle altid se.",
            adgang.MODULER, adgang.moduler_for(bruger))
        if dialog.exec() and udfoer(self, self.auth.saet_moduler, brugernavn,
                                    dialog.valgte) is not FEJL:
            self.opdater()

    def skift_afdelinger(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        dialog = FluebenDialog(
            self, f"Afdelinger – {brugernavn}",
            "Vælg de afdelinger, brugeren er medlem af. En bruger kan være i flere. "
            "Afdelingen afgør, hvad der vises under \"Min afdeling\" i arbejdsbakken – "
            "alle brugere kan stadig behandle alle sager.",
            {a: a for a in AFDELINGER}, adgang.afdelinger_for(self._brugere.get(brugernavn)))
        if dialog.exec() and udfoer(self, self.auth.saet_afdelinger, brugernavn,
                                    dialog.valgte) is not FEJL:
            self.opdater()

    def skift_aktiv(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        aktiv = self._brugere.get(brugernavn, {}).get("aktiv", True)
        tekst = (f"Vil du deaktivere {brugernavn}?\n\nBrugeren kan ikke længere logge på, og en "
                 "igangværende session mister straks adgangen til data. Historikken bevares."
                 if aktiv else f"Vil du aktivere {brugernavn} igen?")
        svar = QMessageBox.question(self, "Deaktivér bruger" if aktiv else "Aktivér bruger", tekst)
        if svar != QMessageBox.StandardButton.Yes:
            return
        udfoer(self, self.auth.saet_aktiv, brugernavn, not aktiv, session.brugernavn())
        self.opdater()

    def slet(self):
        brugernavn = self._valgt()
        if brugernavn is None:
            return
        svar = QMessageBox.warning(
            self, "Slet bruger",
            f"Vil du slette brugeren '{brugernavn}'?\n\n"
            "Brugerens navn bevares i tidslinjerne, men brugeren kan ikke længere logge på. "
            "Overvej at deaktivere i stedet – så kan kontoen genaktiveres.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if svar != QMessageBox.StandardButton.Yes:
            return
        udfoer(self, self.auth.slet, brugernavn, session.brugernavn())
        self.opdater()
