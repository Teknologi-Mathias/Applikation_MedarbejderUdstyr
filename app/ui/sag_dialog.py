"""Afviklingssagen for én medarbejder: opgaver, ansvarlige, frister og fremdrift."""
from datetime import date

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.opgave import Opgave
from app.ui.hjaelpere import dansk_dato, laes_dato, lav_knap, pille_css, vis_dato
from app.ui.opgave_dialog import OpgaveDialog
from app.ui.theme import OPGAVE_STIL, STATUS_STIL


class OpgaveRaekke(QFrame):
    """Én opgave: status-vælger, navn, ansvarlig/frist og Rediger-knap."""

    def __init__(self, sag, opgave, fokus=False, kun_laesning=False):
        super().__init__()
        self.sag = sag
        self.opgave = opgave
        self.setObjectName("opgaveRaekke")
        self.setProperty("fokus", fokus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(14)

        self.status_input = QComboBox()
        self.status_input.addItems(Opgave.STATUSER)
        self.status_input.setFixedWidth(130)
        self.status_input.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_input.setEnabled(not kun_laesning)
        self.status_input.currentTextChanged.connect(self._status_valgt)

        tekst = QVBoxLayout()
        tekst.setSpacing(2)
        self.navn_label = QLabel()
        self.navn_label.setObjectName("opgaveNavn")
        self.meta_label = QLabel()
        self.meta_label.setObjectName("opgaveMeta")
        self.forsinket_label = QLabel()
        self.forsinket_label.setObjectName("opgaveForsinket")
        self.note_label = QLabel()
        self.note_label.setObjectName("opgaveMeta")
        for label in (self.navn_label, self.meta_label, self.forsinket_label, self.note_label):
            label.setWordWrap(True)
            tekst.addWidget(label)

        layout.addWidget(self.status_input, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(tekst, 1)
        if not kun_laesning:
            rediger = lav_knap("Rediger")
            rediger.clicked.connect(lambda: self.sag.rediger_opgave(self.opgave))
            layout.addWidget(rediger, 0, Qt.AlignmentFlag.AlignTop)

        self.opdater()

    def opdater(self):
        o = self.opgave
        self.status_input.blockSignals(True)
        self.status_input.setCurrentText(o.status)
        self.status_input.blockSignals(False)
        stil = OPGAVE_STIL[o.status]
        self.status_input.setStyleSheet(
            f"QComboBox {{ background: {stil['bg']}; color: {stil['tekst']};"
            f" border: none; font-weight: 700; }}"
        )

        self.navn_label.setText(o.navn + ("" if o.obligatorisk else "  (valgfri)"))
        self.meta_label.setText(
            f"{o.ansvarlig or 'Ingen ansvarlig'} · Frist: {vis_dato(o.frist) or 'ingen'}"
        )

        dage_over = o.dage_over_frist(date.today())
        if dage_over is not None and dage_over > 0:
            self.forsinket_label.setText(
                f"{dage_over} {'dag' if dage_over == 1 else 'dage'} over frist"
            )
        elif dage_over == 0:
            self.forsinket_label.setText("Frist i dag")
        else:
            self.forsinket_label.setText("")
        self.forsinket_label.setVisible(bool(self.forsinket_label.text()))

        noter = []
        if o.begrundelse:
            noter.append(f"Begrundelse: {o.begrundelse}")
        if o.naeste_handling and not o.afsluttet:
            noter.append(f"Næste handling: {o.naeste_handling}")
        self.note_label.setText("\n".join(noter))
        self.note_label.setVisible(bool(noter))

    def _status_valgt(self, status):
        if status == Opgave.UNDTAGET and not self.opgave.begrundelse:
            # En undtagelse skal begrundes – åbn opgaven og bed om årsagen.
            if not self.sag.rediger_opgave(self.opgave, ny_status=status):
                self.opdater()   # annulleret: sæt vælgeren tilbage
            return
        self.opgave.status = status
        self.opdater()
        self.sag.opgaver_aendret()


class SagDialog(QDialog):
    """Arbejder på en kopi af medarbejderen; hent resultatet i self.medarbejder."""

    def __init__(self, parent, medarbejder, ansvarlige=(), fokus_opgave_id=None,
                 kun_laesning=False):
        super().__init__(parent)
        self.medarbejder = medarbejder.kopi()
        self.ansvarlige = list(ansvarlige)
        self.fokus_opgave_id = fokus_opgave_id
        self.kun_laesning = kun_laesning

        self.setWindowTitle(f"Afviklingssag: {self.medarbejder.navn}")
        self.setMinimumSize(720, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        layout.addLayout(self._opbyg_hoved())
        layout.addWidget(self._streg())
        layout.addLayout(self._opbyg_fremdrift())

        self.raekke_layout = QVBoxLayout()
        self.raekke_layout.setSpacing(8)
        indre = QWidget()
        indre.setObjectName("scrollInner")
        indre_layout = QVBoxLayout(indre)
        indre_layout.setContentsMargins(0, 0, 6, 0)
        indre_layout.addLayout(self.raekke_layout)
        indre_layout.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(indre)
        layout.addWidget(self.scroll, 1)

        layout.addWidget(self._streg())
        layout.addLayout(self._opbyg_bund())

        self._byg_raekker()
        self.opgaver_aendret()

    ### ----- opbygning ------------------------------------------------------

    @staticmethod
    def _streg():
        streg = QFrame()
        streg.setFrameShape(QFrame.Shape.HLine)
        streg.setStyleSheet("color: #E2E8F0;")
        return streg

    def _opbyg_hoved(self):
        m = self.medarbejder
        hoved = QHBoxLayout()
        tekst = QVBoxLayout()
        tekst.setSpacing(2)
        titel = QLabel(f"Afviklingssag: {m.navn}")
        titel.setObjectName("sagTitel")
        dato = laes_dato(m.fratraedelsesdato)
        sidste_dag = dansk_dato(dato) if dato.isValid() else str(m.fratraedelsesdato)
        under = QLabel(f"Lønnummer {m.loennr} · Sidste arbejdsdag {sidste_dag}")
        under.setObjectName("pageSub")
        tekst.addWidget(titel)
        tekst.addWidget(under)
        if m.status_manuel:
            laast = QLabel(
                f"Status er låst manuelt"
                f"{': ' + m.status_begrundelse if m.status_begrundelse else ''} "
                "(ændres under Rediger)"
            )
            laast.setObjectName("hjaelpTekst")
            tekst.addWidget(laast)

        self.status_badge = QLabel()
        hoved.addLayout(tekst, 1)
        hoved.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        return hoved

    def _opbyg_fremdrift(self):
        boks = QVBoxLayout()
        boks.setSpacing(6)
        top = QHBoxLayout()
        under = QLabel("Opgaver – afsluttet når de er udført eller undtaget")
        under.setObjectName("hjaelpTekst")
        self.antal_label = QLabel()
        self.antal_label.setObjectName("cardTitle")
        top.addWidget(under)
        top.addStretch()
        top.addWidget(self.antal_label)

        self.fremdrift = QProgressBar()
        self.fremdrift.setObjectName("fremdrift")
        self.fremdrift.setTextVisible(False)
        self.fremdrift.setFixedHeight(6)

        boks.addLayout(top)
        boks.addWidget(self.fremdrift)
        return boks

    def _opbyg_bund(self):
        bund = QHBoxLayout()
        if self.kun_laesning:
            knapper = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            knapper.button(QDialogButtonBox.StandardButton.Close).setText("Luk")
            knapper.rejected.connect(self.reject)
        else:
            tilfoej = lav_knap("+ Tilføj opgave")
            tilfoej.clicked.connect(self.tilfoej_opgave)
            bund.addWidget(tilfoej)
            knapper = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save
                | QDialogButtonBox.StandardButton.Cancel
            )
            gem_knap = knapper.button(QDialogButtonBox.StandardButton.Save)
            gem_knap.setText("Gem sag")
            gem_knap.setProperty("variant", "primary")
            knapper.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuller")
            knapper.accepted.connect(self.accept)
            knapper.rejected.connect(self.reject)
        bund.addStretch()
        bund.addWidget(knapper)
        return bund

    def _byg_raekker(self):
        while self.raekke_layout.count():
            widget = self.raekke_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

        fokus_raekke = None
        for opgave in self.medarbejder.opgaver:
            fokus = opgave.id == self.fokus_opgave_id
            raekke = OpgaveRaekke(self, opgave, fokus, self.kun_laesning)
            self.raekke_layout.addWidget(raekke)
            if fokus:
                fokus_raekke = raekke

        if not self.medarbejder.opgaver:
            tom = QLabel("Sagen har ingen opgaver endnu. Tilføj dem med '+ Tilføj opgave'.")
            tom.setObjectName("hjaelpTekst")
            tom.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tom.setMinimumHeight(80)
            self.raekke_layout.addWidget(tom)

        if fokus_raekke is not None:
            # Vent til layoutet er beregnet, før der scrolles hen til opgaven.
            QTimer.singleShot(0, lambda: self._vis_fokus(fokus_raekke))

    def _vis_fokus(self, raekke):
        self.scroll.ensureWidgetVisible(raekke)
        if raekke.status_input.isEnabled():
            raekke.status_input.setFocus()

    ### ----- ændringer ------------------------------------------------------

    def opgaver_aendret(self):
        """Opdaterer overskriftens status og fremdrift efter en ændring."""
        m = self.medarbejder
        afsluttede, total = m.opgave_optaelling()
        self.antal_label.setText(f"{afsluttede} af {total}")
        self.fremdrift.setMaximum(max(total, 1))
        self.fremdrift.setValue(afsluttede)

        self.status_badge.setText(m.status + (" (manuel)" if m.status_manuel else ""))
        self.status_badge.setStyleSheet(pille_css(STATUS_STIL[m.status]))

    def rediger_opgave(self, opgave, ny_status=None):
        """Åbner opgaven. Returnerer True hvis noget blev gemt eller slettet."""
        dialog = OpgaveDialog(self, opgave, self.ansvarlige)
        if ny_status:
            dialog.status_input.setCurrentText(ny_status)
            dialog.fokuser_begrundelse()
        if not dialog.exec():
            return False
        if dialog.slettet:
            self.medarbejder.opgaver.remove(opgave)
        self._byg_raekker()
        self.opgaver_aendret()
        return True

    def tilfoej_opgave(self):
        dialog = OpgaveDialog(
            self, None, self.ansvarlige, standard_frist=self.medarbejder.fratraedelsesdato
        )
        if dialog.exec():
            self.medarbejder.opgaver.append(dialog.opgave)
            self.fokus_opgave_id = dialog.opgave.id
            self._byg_raekker()
            self.opgaver_aendret()
