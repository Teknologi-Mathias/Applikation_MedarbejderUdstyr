"""Ny version af IN-BASE: hvad er nyt, hent (med fremdrift) og installér.

Dialogen henter selv installeren, hvis den ikke allerede er hentet i
baggrunden. Ved "Opdater og genstart" accepteres dialogen med installer_sti;
hovedvinduet starter installeren og lukker programmet (app/ui/hovedvindue.py).
Er opdateringen tvungen (for gammel eller tilbagetrukket version), kan den ikke
udskydes – "Afslut" lukker programmet i stedet.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from app import version_tupel
from app.ui.baggrund import koer_i_baggrund
from app.ui.hjaelpere import lav_knap


class _Fremdrift(QObject):
    """Fremdrift fra baggrundstråden – signalet leveres på UI-tråden."""
    aendret = Signal(int, int)


class OpdateringDialog(QDialog):
    def __init__(self, parent, service, status, hentet: Path | None = None):
        super().__init__(parent)
        self.service = service
        self.status = status
        self.installer_sti: Path | None = hentet
        maal = status.maal
        self.setWindowTitle("IN-BASE skal opdateres" if status.tvungen else "Ny version af IN-BASE")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        titel = QLabel(f"Version {maal.version} er klar" if maal
                       else "Din version af IN-BASE kan ikke bruges længere")
        titel.setObjectName("sagTitel")
        layout.addWidget(titel)

        tekst = QLabel(self._tekst())
        tekst.setWordWrap(True)
        layout.addWidget(tekst)
        if maal and maal.noter:
            noter = QLabel(maal.noter)
            noter.setObjectName("hjaelpTekst")
            noter.setWordWrap(True)
            layout.addWidget(noter)

        self.fremdrift = QProgressBar()
        self.fremdrift.setObjectName("fremdrift")
        self.fremdrift.setTextVisible(False)
        self.fremdrift.setFixedHeight(6)
        self.fremdrift.setVisible(False)
        layout.addWidget(self.fremdrift)
        self.fejl_label = QLabel("")
        self.fejl_label.setObjectName("feltFejl")
        self.fejl_label.setWordWrap(True)
        self.fejl_label.setVisible(False)
        layout.addWidget(self.fejl_label)

        knapper = QHBoxLayout()
        knapper.addStretch()
        self.senere = lav_knap("Afslut IN-BASE" if status.tvungen else "Senere")
        self.senere.clicked.connect(self.reject)
        self.opdater_knap = lav_knap("Opdater og genstart", "primary")
        self.opdater_knap.clicked.connect(self._opdater)
        self.opdater_knap.setVisible(maal is not None)
        self.opdater_knap.setEnabled(service.kan_installere)
        if not service.kan_installere:
            self.opdater_knap.setToolTip("Opdateringer installeres kun i den installerede app.")
        knapper.addWidget(self.senere)
        knapper.addWidget(self.opdater_knap)
        layout.addLayout(knapper)

        self._signal = _Fremdrift(self)
        self._signal.aendret.connect(self._vis_fremdrift)

    def _tekst(self) -> str:
        nu, maal = self.service.version, self.status.maal
        if maal is None:
            return (f"Du har version {nu}, som ikke længere må bruges, og der er ingen nyere "
                    "version til dig endnu. Kontakt en administrator.")
        if maal.tupel < version_tupel(nu):
            start = f"Version {nu} er trukket tilbage. IN-BASE går tilbage til version {maal.version}."
        else:
            start = f"Du har version {nu}."
        slut = (" Opdateringen er påkrævet, før du kan arbejde videre." if self.status.tvungen
                else " IN-BASE lukker, opdateres og starter igen – det tager under et minut. "
                     "Ændringer, du allerede har gemt, er gemt.")
        return start + slut

    def _vis_fremdrift(self, hentet: int, i_alt: int) -> None:
        self.fremdrift.setRange(0, i_alt or 0)
        if i_alt:
            self.fremdrift.setValue(hentet)

    def _opdater(self) -> None:
        if self.installer_sti is not None:
            self.accept()
            return
        self.opdater_knap.setEnabled(False)
        self.opdater_knap.setText("Henter…")
        self.fejl_label.setVisible(False)
        self.fremdrift.setVisible(True)
        koer_i_baggrund(self.service.hent, self.status.maal,
                        lambda hentet, i_alt: self._signal.aendret.emit(hentet, i_alt),
                        naar_faerdig=self._hentet, ved_fejl=self._fejl)

    def _hentet(self, sti: Path) -> None:
        self.installer_sti = sti
        self.accept()

    def _fejl(self, fejl: Exception) -> None:
        self.fremdrift.setVisible(False)
        self.fejl_label.setText(str(fejl))
        self.fejl_label.setVisible(True)
        self.opdater_knap.setText("Prøv igen")
        self.opdater_knap.setEnabled(True)
