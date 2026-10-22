"""En sag (onboarding eller offboarding): opgaver, milepæle, fremdrift og tidslinje.

Dialogen arbejder på en kopi af sagen (self.sag). Controlleren gemmer kopien
via servicen, når brugeren trykker "Gem sag".
"""
from datetime import date

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.opgave import Opgave
from app.ui.hjaelpere import lav_knap, pille_css, vis_dato
from app.ui.opgave_dialog import OpgaveDialog
from app.ui.theme import OPGAVE_STIL, TONER, status_stil


class OpgaveRaekke(QFrame):
    """Én opgave: status-vælger, navn, ansvarlig/frist og Rediger-knap."""

    def __init__(self, dialog, opgave, fokus=False, kun_laesning=False):
        super().__init__()
        self.dialog = dialog
        self.opgave = opgave
        self.laast = dialog.sag.er_laast(opgave)
        self.setObjectName("opgaveRaekke")
        self.setProperty("fokus", fokus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(14)

        self.status_input = QComboBox()
        self.status_input.addItems(Opgave.STATUSER)
        self.status_input.setFixedWidth(130)
        self.status_input.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_input.setEnabled(not kun_laesning and not self.laast)
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
            rediger.clicked.connect(lambda: self.dialog.rediger_opgave(self.opgave))
            layout.addWidget(rediger, 0, Qt.AlignmentFlag.AlignTop)

        self.opdater()

    def opdater(self):
        o = self.opgave
        self.status_input.blockSignals(True)
        self.status_input.setCurrentText(o.status)
        self.status_input.blockSignals(False)
        stil = TONER["graa"] if self.laast else OPGAVE_STIL[o.status]
        self.status_input.setStyleSheet(
            f"QComboBox {{ background: {stil['bg']}; color: {stil['tekst']};"
            f" border: none; font-weight: 700; }}"
        )

        self.navn_label.setText(o.navn + ("" if o.obligatorisk else "  (valgfri)"))
        meta = f"{o.ansvarlig or 'Ingen ansvarlig'} · Frist: {vis_dato(o.frist) or 'ingen'}"
        if o.udstyr:
            meta += f" · Udstyr: {o.udstyr}"
        self.meta_label.setText(meta)

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
        if self.laast:
            aktiv = self.dialog.sag.milepael_navn(self.dialog.sag.aktiv_milepael())
            noter.append(f"Låst – bliver tilgængelig, når '{aktiv}' er færdig")
        if o.beskrivelse:
            noter.append(o.beskrivelse)
        if o.begrundelse:
            noter.append(f"Begrundelse: {o.begrundelse}")
        if o.naeste_handling and not o.afsluttet:
            noter.append(f"Næste handling: {o.naeste_handling}")
        self.note_label.setText("\n".join(noter))
        self.note_label.setVisible(bool(noter))

    def _status_valgt(self, status):
        if status == Opgave.UNDTAGET and not self.opgave.begrundelse:
            # En undtagelse skal begrundes – åbn opgaven og bed om årsagen.
            if not self.dialog.rediger_opgave(self.opgave, ny_status=status):
                self.opdater()   # annulleret: sæt vælgeren tilbage
            return
        milepael_foer = self.dialog.sag.aktiv_milepael()
        self.opgave.saet_status(status)
        if self.dialog.sag.aktiv_milepael() != milepael_foer:
            # En milepæl er blevet færdig (eller genåbnet): lås op/lås rækkerne.
            QTimer.singleShot(0, self.dialog.byg_raekker)
        else:
            self.opdater()
        self.dialog.opgaver_aendret()


class SagDialog(QDialog):
    """Arbejder på en kopi af sagen; hent resultatet i self.sag."""

    FANE_OPGAVER = 0
    FANE_TIDSLINJE = 1

    def __init__(self, parent, sag, ansvarlige=(), fokus_opgave_id=None,
                 kun_laesning=False, start_fane=FANE_OPGAVER):
        super().__init__(parent)
        self.sag = sag.kopi()
        self.ansvarlige = list(ansvarlige)
        self.fokus_opgave_id = fokus_opgave_id
        self.kun_laesning = kun_laesning

        self.setWindowTitle(f"{self._titel()}: {self.sag.navn}")
        self.setMinimumSize(720, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        layout.addLayout(self._opbyg_hoved())

        self.faner = QTabWidget()
        self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.faner.addTab(self._opbyg_opgave_fane(), "Opgaver")
        self.faner.addTab(self._opbyg_tidslinje_fane(), "Tidslinje")
        self.faner.setTabToolTip(0, "Sagens opgaver – skift status, rediger eller tilføj")
        self.faner.setTabToolTip(1, "Hele forløbet: hvem gjorde hvad og hvornår")
        self.faner.setCurrentIndex(start_fane)
        layout.addWidget(self.faner, 1)

        layout.addWidget(self._streg())
        layout.addLayout(self._opbyg_bund())

        self.byg_raekker()
        self.opgaver_aendret()
        self._byg_tidslinje()

    def _titel(self):
        return "Onboarding" if self.sag.MILEPAELE else "Afviklingssag"

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_opgave_fane(self):
        fane = QWidget()
        layout = QVBoxLayout(fane)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
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
        return fane

    def _opbyg_tidslinje_fane(self):
        fane = QWidget()
        layout = QVBoxLayout(fane)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        forklaring = QLabel(
            "Hele forløbet registreres automatisk og kan ikke redigeres. "
            "Notater tilføjes som nye hændelser."
        )
        forklaring.setObjectName("hjaelpTekst")
        forklaring.setWordWrap(True)
        top.addWidget(forklaring, 1)
        if not self.kun_laesning:
            notat_knap = lav_knap("+ Tilføj notat")
            notat_knap.clicked.connect(self.tilfoej_notat)
            top.addWidget(notat_knap)
        layout.addLayout(top)

        self.manipuleret_label = QLabel(
            "Advarsel: Tidslinjen er ændret uden for programmet – én eller flere "
            "hændelser stemmer ikke med den oprindelige registrering."
        )
        self.manipuleret_label.setObjectName("advarsel")
        self.manipuleret_label.setWordWrap(True)
        layout.addWidget(self.manipuleret_label)

        self.tidslinje = QTableWidget()
        self.tidslinje.setColumnCount(4)
        self.tidslinje.setHorizontalHeaderLabels(["Tidspunkt", "Bruger", "Hændelse", "Kommentar"])
        self.tidslinje.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tidslinje.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tidslinje.setShowGrid(False)
        self.tidslinje.setWordWrap(True)
        self.tidslinje.setAlternatingRowColors(True)
        self.tidslinje.verticalHeader().setVisible(False)
        self.tidslinje.horizontalHeader().setStretchLastSection(True)
        self.tidslinje.setColumnWidth(0, 130)
        self.tidslinje.setColumnWidth(1, 110)
        self.tidslinje.setColumnWidth(2, 250)
        layout.addWidget(self.tidslinje, 1)
        return fane

    @staticmethod
    def _streg():
        streg = QFrame()
        streg.setObjectName("streg")
        streg.setFixedHeight(1)
        return streg

    def _opbyg_hoved(self):
        m = self.sag
        hoved = QHBoxLayout()
        tekst = QVBoxLayout()
        tekst.setSpacing(2)
        titel = QLabel(f"{self._titel()}: {m.navn}")
        titel.setObjectName("sagTitel")
        under = QLabel(m.beskrivelse())
        under.setObjectName("pageSub")
        under.setWordWrap(True)
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

    def _grupper(self):
        """[(overskrift eller None, [opgaver])] – opgaver grupperet efter milepæl."""
        sag = self.sag
        if not sag.MILEPAELE:
            return [(None, sag.opgaver)]
        grupper = []
        for noegle, navn in sag.MILEPAELE:
            opgaver = [o for o in sag.opgaver if o.milepael == noegle]
            if opgaver:
                faerdig = "  ✓" if sag.milepael_faerdig(noegle) else ""
                grupper.append((navn.upper() + faerdig, opgaver))
        uden = [o for o in sag.opgaver if o.milepael not in dict(sag.MILEPAELE)]
        if uden:
            grupper.append(("ØVRIGE OPGAVER", uden))
        return grupper

    def byg_raekker(self):
        while self.raekke_layout.count():
            widget = self.raekke_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

        fokus_raekke = None
        for overskrift, opgaver in self._grupper():
            if overskrift:
                label = QLabel(overskrift)
                label.setObjectName("milepaelTitel")
                self.raekke_layout.addWidget(label)
            for opgave in opgaver:
                fokus = opgave.id == self.fokus_opgave_id
                raekke = OpgaveRaekke(self, opgave, fokus, self.kun_laesning)
                self.raekke_layout.addWidget(raekke)
                if fokus:
                    fokus_raekke = raekke

        if not self.sag.opgaver:
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
        m = self.sag
        afsluttede, total = m.opgave_optaelling()
        self.antal_label.setText(f"{afsluttede} af {total}")
        self.fremdrift.setMaximum(max(total, 1))
        self.fremdrift.setValue(afsluttede)

        self.status_badge.setText(m.status + (" (manuel)" if m.status_manuel else ""))
        self.status_badge.setStyleSheet(pille_css(status_stil(m.status)))

    def rediger_opgave(self, opgave, ny_status=None):
        """Åbner opgaven. Returnerer True hvis noget blev gemt eller slettet."""
        dialog = OpgaveDialog(self, opgave, self.ansvarlige, milepaele=self.sag.MILEPAELE)
        if ny_status:
            dialog.status_input.setCurrentText(ny_status)
            dialog.fokuser_begrundelse()
        if not dialog.exec():
            return False
        if dialog.slettet:
            self.sag.opgaver.remove(opgave)
        self.byg_raekker()
        self.opgaver_aendret()
        return True

    def tilfoej_opgave(self):
        dialog = OpgaveDialog(
            self, None, self.ansvarlige, standard_frist=self.sag.startdato(),
            milepaele=self.sag.MILEPAELE,
        )
        if dialog.exec():
            self.sag.opgaver.append(dialog.opgave)
            self.fokus_opgave_id = dialog.opgave.id
            self.byg_raekker()
            self.opgaver_aendret()

    ### ----- tidslinje ------------------------------------------------------

    def _reference_tekst(self, reference):
        """Viser opgavens navn i stedet for dens id, hvis referencen er en opgave."""
        opgave = self.sag.find_opgave(reference)
        if opgave is not None:
            return opgave.navn
        find_rykker = getattr(self.sag, "find_rykker", None)
        rykker = find_rykker(reference) if find_rykker else None
        if rykker is not None:
            return f"Rykker: {rykker.emne}"
        return reference

    def _byg_tidslinje(self):
        historik = self.sag.historik
        self.manipuleret_label.setVisible(not historik.er_intakt())
        haendelser = historik.haendelser()
        self.tidslinje.setRowCount(len(haendelser))
        for raekke, h in enumerate(haendelser):
            tid = h.get("tid", "")
            vis_tid = f"{vis_dato(tid[:10])} {tid[11:16]}".strip()
            reference = self._reference_tekst(h.get("reference", ""))
            kommentar = " · ".join(
                t for t in (h.get("kommentar", ""), reference) if t
            )
            for kolonne, tekst in enumerate(
                (vis_tid, h.get("bruger", ""), h.get("handling", ""), kommentar)
            ):
                item = QTableWidgetItem(tekst)
                item.setToolTip(tekst)
                self.tidslinje.setItem(raekke, kolonne, item)
        self.tidslinje.resizeRowsToContents()
        self.tidslinje.scrollToBottom()

    def tilfoej_notat(self):
        tekst, ok = QInputDialog.getMultiLineText(
            self, "Tilføj notat",
            "Notatet tilføjes tidslinjen og kan ikke ændres bagefter.\n"
            "Det gemmes sammen med sagen.",
        )
        if ok and tekst.strip():
            self.sag.historik.tilfoej("Notat", tekst.strip())
            self._byg_tidslinje()
