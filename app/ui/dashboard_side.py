"""Dashboard: statistikkort, diagrammer, Action Center og Dagsoversigt."""
from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import alarmer
from app.medarbejder import Medarbejder
from app.ui.diagrammer import BarChart, DonutChart
from app.ui.hjaelpere import (
    UGEDAGE_KORT,
    dansk_dato,
    laes_dato,
    lav_kort,
    lav_raekke,
    lav_sidehoved,
    vis_dato,
)
from app.ui.theme import ALARM_STIL, FARVER, OPGAVE_STIL, STATUS_STIL

# Data på hver klikbar listerække: (lønnr., opgave-id eller None).
SAG_ROLE = Qt.ItemDataRole.UserRole


class DashboardSide(QWidget):
    DIAGRAM_DAGE = 14

    # Udsendes ved klik i Action Center/Dagsoversigt: (lønnr., opgave-id eller "").
    aabn_sag = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aktive = []
        self._arkiverede = []
        self._opbyg()

    ### ----- opbygning ------------------------------------------------------

    def _opbyg(self):
        ydre = QVBoxLayout(self)
        ydre.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ydre.addWidget(scroll)

        indre = QWidget()
        indre.setObjectName("scrollInner")
        scroll.setWidget(indre)

        layout = QVBoxLayout(indre)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        hoved, self.dato_label = lav_sidehoved(
            "Dashboard", "Overblik over udstyr, fratrædelser og opgaver."
        )
        layout.addLayout(hoved)
        layout.addLayout(self._opbyg_statistik_kort())
        layout.addLayout(self._opbyg_diagrammer())
        layout.addLayout(self._opbyg_lister())

    def _opbyg_statistik_kort(self):
        raekke = QHBoxLayout()
        raekke.setSpacing(14)
        self.kort = {}
        for noegle, titel, farve in (
            ("aktive", "Aktive medarbejdere", FARVER["primary"]),
            ("afventer", Medarbejder.STATUS_AFVENTER, STATUS_STIL[Medarbejder.STATUS_AFVENTER]["farve"]),
            ("delvist", Medarbejder.STATUS_DELVIST, STATUS_STIL[Medarbejder.STATUS_DELVIST]["farve"]),
            ("afviklet", Medarbejder.STATUS_AFVIKLET, STATUS_STIL[Medarbejder.STATUS_AFVIKLET]["farve"]),
            ("arkiverede", "Arkiverede", "#94A3B8"),
        ):
            kort, vaerdi, sub = self._opret_statistik_kort(titel, farve)
            self.kort[noegle] = (vaerdi, sub)
            raekke.addWidget(kort, 1)
        return raekke

    def _opbyg_diagrammer(self):
        raekke = QHBoxLayout()
        raekke.setSpacing(14)

        donut_kort = lav_kort()
        donut_layout = QVBoxLayout(donut_kort)
        donut_layout.setContentsMargins(20, 18, 20, 18)
        donut_layout.setSpacing(8)
        donut_titel = QLabel("Statusfordeling")
        donut_titel.setObjectName("cardTitle")
        donut_under = QLabel("Aktive medarbejdere")
        donut_under.setObjectName("cardSub")
        self.donut = DonutChart()
        donut_layout.addWidget(donut_titel)
        donut_layout.addWidget(donut_under)
        donut_layout.addWidget(self.donut, 1)
        self.legend_labels = {}
        for status in Medarbejder.STATUSER:
            label = QLabel("")
            label.setTextFormat(Qt.TextFormat.RichText)
            self.legend_labels[status] = label
            donut_layout.addWidget(label)

        soejle_kort = lav_kort()
        soejle_layout = QVBoxLayout(soejle_kort)
        soejle_layout.setContentsMargins(20, 18, 20, 18)
        soejle_layout.setSpacing(8)
        soejle_titel = QLabel(f"Fratrædelser de næste {self.DIAGRAM_DAGE} dage")
        soejle_titel.setObjectName("cardTitle")
        soejle_under = QLabel("Antal aktive medarbejdere, der fratræder pr. dag")
        soejle_under.setObjectName("cardSub")
        self.soejlediagram = BarChart()
        soejle_layout.addWidget(soejle_titel)
        soejle_layout.addWidget(soejle_under)
        soejle_layout.addWidget(self.soejlediagram, 1)

        raekke.addWidget(donut_kort, 4)
        raekke.addWidget(soejle_kort, 7)
        return raekke

    def _opbyg_lister(self):
        raekke = QHBoxLayout()
        raekke.setSpacing(14)

        action_kort, self.action_liste, self.action_antal = self._opret_liste_kort(
            "Action Center",
            "Hvad mangler, hvem skal handle – klik for at åbne opgaven",
        )
        dag_kort, self.dag_liste, self.dag_antal = self._opret_liste_kort(
            "Dagsoversigt",
            "Opgaver med frist i dag",
        )
        raekke.addWidget(action_kort, 3)
        raekke.addWidget(dag_kort, 2)
        return raekke

    def _opret_statistik_kort(self, titel, farve):
        kort = lav_kort()
        kort.setMinimumHeight(112)

        layout = QVBoxLayout(kort)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(7)
        prik = QLabel("●")
        prik.setStyleSheet(f"color: {farve}; font-size: 11px; background: transparent;")
        titel_label = QLabel(titel)
        titel_label.setObjectName("statTitle")
        top.addWidget(prik)
        top.addWidget(titel_label)
        top.addStretch()

        vaerdi_label = QLabel("0")
        vaerdi_label.setObjectName("statValue")
        sub_label = QLabel("")
        sub_label.setObjectName("statSub")

        layout.addLayout(top)
        layout.addWidget(vaerdi_label)
        layout.addWidget(sub_label)
        return kort, vaerdi_label, sub_label

    def _opret_liste_kort(self, titel, undertitel):
        kort = lav_kort()
        layout = QVBoxLayout(kort)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        titel_label = QLabel(titel)
        titel_label.setObjectName("cardTitle")
        antal_label = QLabel("0")
        antal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        antal_label.setMinimumWidth(28)
        antal_label.setStyleSheet(
            f"background: {FARVER['primary_soft']}; color: {FARVER['primary']};"
            "border-radius: 10px; font-weight: 700; font-size: 12px; padding: 3px 8px;"
        )
        top.addWidget(titel_label)
        top.addStretch()
        top.addWidget(antal_label)

        under_label = QLabel(undertitel)
        under_label.setObjectName("cardSub")

        liste = QListWidget()
        liste.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        liste.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        liste.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        liste.setMinimumHeight(300)
        liste.setProperty("klikbar", True)
        liste.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        liste.itemClicked.connect(self._raekke_klikket)

        layout.addLayout(top)
        layout.addWidget(under_label)
        layout.addWidget(liste, 1)
        return kort, liste, antal_label

    ### ----- opdatering -----------------------------------------------------

    def opdater(self, aktive, arkiverede):
        self._aktive = aktive
        self._arkiverede = arkiverede
        self._opdater_statistik()
        self._opdater_diagram()
        self._opdater_action_center()
        self._opdater_dagsoversigt()

    def _opdater_statistik(self):
        aktive = self._aktive
        antal_aktive = len(aktive)
        tael = {
            status: sum(1 for m in aktive if m.status == status)
            for status in Medarbejder.STATUSER
        }
        antal_forsinkede = len(alarmer.forsinkede(aktive, date.today()))

        def procent(antal):
            return round(antal / antal_aktive * 100) if antal_aktive else 0

        vaerdi, sub = self.kort["aktive"]
        vaerdi.setText(str(antal_aktive))
        if antal_forsinkede:
            sub.setText(
                f"{antal_forsinkede} forsinkede "
                f"{'opgave' if antal_forsinkede == 1 else 'opgaver'}"
            )
            sub.setStyleSheet(f"color: {STATUS_STIL[Medarbejder.STATUS_AFVENTER]['tekst']};")
        else:
            sub.setText("Ingen forsinkede opgaver")
            sub.setStyleSheet("")

        for noegle, status in (
            ("afventer", Medarbejder.STATUS_AFVENTER),
            ("delvist", Medarbejder.STATUS_DELVIST),
            ("afviklet", Medarbejder.STATUS_AFVIKLET),
        ):
            vaerdi, sub = self.kort[noegle]
            vaerdi.setText(str(tael[status]))
            sub.setText(f"{procent(tael[status])}% af aktive")

        vaerdi, sub = self.kort["arkiverede"]
        vaerdi.setText(str(len(self._arkiverede)))
        sub.setText("Afsluttede forløb")

        # Donut + forklaring
        self.donut.saet_data(
            [(s, tael[s], STATUS_STIL[s]["farve"]) for s in Medarbejder.STATUSER],
            antal_aktive,
            "aktive",
        )
        for status in Medarbejder.STATUSER:
            farve = STATUS_STIL[status]["farve"]
            self.legend_labels[status].setText(
                f'<span style="color:{farve}; font-size:14px;">●</span>&nbsp;&nbsp;'
                f"{status} &nbsp;<b>{tael[status]}</b> "
                f'<span style="color:{FARVER["muted"]};">({procent(tael[status])}%)</span>'
            )

        self.dato_label.setText(
            f"Overblik over udstyr, fratrædelser og opgaver · "
            f"{dansk_dato(QDate.currentDate())}"
        )

    def _opdater_diagram(self):
        i_dag = QDate.currentDate()
        antal_pr_dag = {}
        for m in self._aktive:
            dato = laes_dato(m.fratraedelsesdato)
            if dato.isValid():
                antal_pr_dag[dato] = antal_pr_dag.get(dato, 0) + 1

        data = []
        for i in range(self.DIAGRAM_DAGE):
            dato = i_dag.addDays(i)
            data.append((
                dato.day(),
                UGEDAGE_KORT[dato.dayOfWeek() - 1],
                antal_pr_dag.get(dato, 0),
                i == 0,
                dato.dayOfWeek() >= 6,
            ))
        self.soejlediagram.saet_data(data)

    @staticmethod
    def _fyld_liste(liste, raekker, tom_tekst):
        liste.clear()
        if not raekker:
            item = QListWidgetItem()
            label = QLabel(tom_tekst)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                f"color: {FARVER['muted']}; padding: 44px 0; background: transparent;"
            )
            item.setSizeHint(label.sizeHint())
            liste.addItem(item)
            liste.setItemWidget(item, label)
            return
        for widget, sag in raekker:
            item = QListWidgetItem()
            item.setData(SAG_ROLE, sag)
            item.setSizeHint(widget.sizeHint())
            liste.addItem(item)
            liste.setItemWidget(item, widget)

    def _raekke_klikket(self, item):
        sag = item.data(SAG_ROLE)
        if sag:
            loennr, opgave_id = sag
            self.aabn_sag.emit(loennr, opgave_id or "")

    def _opdater_action_center(self):
        alle = alarmer.action_center(self._aktive, date.today())
        raekker = [
            (lav_raekke(a.titel, a.undertitel, a.badge, ALARM_STIL[a.niveau]),
             (a.loennr, a.opgave_id))
            for a in alle
        ]
        self._fyld_liste(self.action_liste, raekker, "Intet kræver handling lige nu.")
        self.action_antal.setText(str(len(alle)))

    def _opdater_dagsoversigt(self):
        opgaver = alarmer.dagsoversigt(self._aktive, date.today())
        raekker = [
            (lav_raekke(
                o.navn,
                f"{m.navn} · Ansvarlig: {o.ansvarlig or 'ingen angivet'} · "
                f"Frist {vis_dato(o.frist)}",
                o.status,
                OPGAVE_STIL[o.status],
            ), (m.loennr, o.id))
            for m, o in opgaver
        ]
        self._fyld_liste(self.dag_liste, raekker, "Ingen opgaver har frist i dag.")
        self.dag_antal.setText(str(len(opgaver)))
