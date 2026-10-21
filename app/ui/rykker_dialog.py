"""Opret rykker: vælg skabelon og frist, se beskeden, og åbn en kladde i mailprogrammet.

Første version bruger mailto:, som åbner standardmailprogrammet med modtager,
emne og brødtekst udfyldt. Programmet kan ikke se, om mailen bliver sendt –
derfor registreres rykkeren som "Kladde oprettet", indtil brugeren selv
markerer den som sendt.
"""
from datetime import date, timedelta
from urllib.parse import quote

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from app import skabeloner
from app.rykker import Rykker


def mailto_url(modtager, emne, broedtekst):
    # Linjeskift skal være CRLF i mailto-links for at virke i Outlook.
    tekst = broedtekst.replace("\r\n", "\n").replace("\n", "\r\n")
    return (
        f"mailto:{quote(modtager, safe='@.+-_')}"
        f"?subject={quote(emne, safe='')}&body={quote(tekst, safe='')}"
    )


class RykkerDialog(QDialog):
    """Efter exec(): self.rykker er den oprettede rykker (eller None)."""

    def __init__(self, parent, medarbejder, mailskabeloner, valgt=None):
        super().__init__(parent)
        self.medarbejder = medarbejder
        self.mailskabeloner = list(mailskabeloner)
        self.rykker = None

        self.setWindowTitle(f"Opret rykker: {medarbejder.navn}")
        self.setMinimumSize(640, 600)

        tidligere = len(medarbejder.rykkere)
        info = QLabel(
            f"{medarbejder.navn} har fået {tidligere} "
            f"{'rykker' if tidligere == 1 else 'rykkere'} før. "
            "Skabelonen er valgt ud fra det, men kan ændres."
            if tidligere else
            "Første rykker til medarbejderen. Skabelonen kan ændres."
        )
        info.setObjectName("info")
        info.setWordWrap(True)

        self.skabelon_input = QComboBox()
        for s in self.mailskabeloner:
            self.skabelon_input.addItem(f"{s['navn']}  ·  {s['kategori']} · {s['tone']}")
        if valgt in self.mailskabeloner:
            self.skabelon_input.setCurrentIndex(self.mailskabeloner.index(valgt))

        self.frist_input = QDateEdit()
        self.frist_input.setCalendarPopup(True)
        self.frist_input.setDisplayFormat("dd-MM-yyyy")

        self.til_felt = QLineEdit(medarbejder.email or "")
        self.til_felt.setReadOnly(True)
        self.emne_felt = QLineEdit()
        self.emne_felt.setReadOnly(True)
        self.broedtekst_felt = QPlainTextEdit()
        self.broedtekst_felt.setReadOnly(True)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Skabelon", self.skabelon_input)
        form.addRow("Frist", self.frist_input)
        form.addRow("Til", self.til_felt)
        form.addRow("Emne", self.emne_felt)

        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("advarsel")
        self.fejl_label.setWordWrap(True)

        note = QLabel(
            "Kladden åbnes i dit mailprogram. Programmet kan ikke se, om den bliver "
            "sendt – marker rykkeren som sendt under Handling, når den er afsendt."
        )
        note.setObjectName("hjaelpTekst")
        note.setWordWrap(True)

        self.knapper = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.opret_knap = self.knapper.button(QDialogButtonBox.StandardButton.Ok)
        self.opret_knap.setText("Opret kladde i mailprogram")
        self.opret_knap.setProperty("variant", "primary")
        self.knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
        self.knapper.accepted.connect(self.accept)
        self.knapper.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(QLabel("Besked"))
        layout.addWidget(self.broedtekst_felt, 1)
        layout.addWidget(self.fejl_label)
        layout.addWidget(note)
        layout.addWidget(self.knapper)

        self.skabelon_input.currentIndexChanged.connect(self._skabelon_skiftet)
        self.frist_input.dateChanged.connect(self._opdater)
        self._skabelon_skiftet()

    def _skabelon(self):
        index = self.skabelon_input.currentIndex()
        return self.mailskabeloner[index] if 0 <= index < len(self.mailskabeloner) else None

    def _skabelon_skiftet(self):
        skabelon = self._skabelon()
        dage = int(skabelon.get("frist_dage", 7)) if skabelon else 7
        frist = date.today() + timedelta(days=dage)
        self.frist_input.setDate(QDate(frist.year, frist.month, frist.day))
        self._opdater()

    def _frist_iso(self):
        return self.frist_input.date().toString("yyyy-MM-dd")

    def _opdater(self):
        skabelon = self._skabelon()
        if skabelon is None:
            self.emne, self.broedtekst = "", ""
            fejl = ["Der er ingen aktive mailskabeloner. Opret en under Skabeloner."]
        else:
            self.emne, self.broedtekst, fejl = skabeloner.byg_mail(
                skabelon, self.medarbejder, self._frist_iso()
            )
        if self.frist_input.date() < QDate.currentDate():
            fejl.append("Fristen ligger i fortiden.")

        self.emne_felt.setText(self.emne)
        self.broedtekst_felt.setPlainText(self.broedtekst)
        self.fejl_label.setText("Beskeden kan ikke oprettes:\n• " + "\n• ".join(fejl))
        self.fejl_label.setVisible(bool(fejl))
        self.opret_knap.setEnabled(not fejl)

    def accept(self):
        skabelon = self._skabelon()
        if skabelon is None or not self.opret_knap.isEnabled():
            return
        url = mailto_url(self.medarbejder.email, self.emne, self.broedtekst)
        if not QDesktopServices.openUrl(QUrl.fromEncoded(url.encode("ascii"))):
            self.fejl_label.setText(
                "Mailprogrammet kunne ikke åbnes. Er der valgt et standardmailprogram "
                "i Windows?"
            )
            self.fejl_label.setVisible(True)
            return
        self.rykker = Rykker(
            skabelon["navn"], skabelon["kategori"], self.emne, self._frist_iso()
        )
        super().accept()
