"""Et moduls "Oversigt": statuskort, statusfordeling, kommende datoer og
modulets egne punkter fra Action Center. Fælles for onboarding og offboarding."""
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.action_liste import ActionListe
from app.ui.diagrammer import BarChart, DonutChart
from app.ui.hjaelpere import UGEDAGE_KORT, dansk_dato, laes_dato, lav_kort, lav_sidehoved, scroll_side
from app.ui.moduler import Modul
from app.ui.theme import FARVER, status_stil


class ModulOversigtSide(QWidget):
    DIAGRAM_DAGE = 14

    def __init__(self, modul: Modul, parent=None):
        super().__init__(parent)
        self.modul = modul
        # Statusser der vises som kort (annullerede ligger i arkivet).
        self.statusser = [s for s in modul.statusser if s != "Annulleret"]

        layout = scroll_side(self)
        hoved, self.dato_label = lav_sidehoved(f"{modul.navn} – oversigt", "")
        layout.addLayout(hoved)
        layout.addLayout(self._opbyg_kort())
        layout.addLayout(self._opbyg_diagrammer())

        lister = QHBoxLayout()
        lister.setSpacing(14)
        self.action = ActionListe("Kræver handling", f"Afvigelser og næste handling i {modul.navn.lower()}",
                                  vis_modul=False, parent=self)
        self.dag = ActionListe("Frist i dag", "Opgaver med frist i dag", vis_modul=False, parent=self)
        lister.addWidget(self.action.kort, 3)
        lister.addWidget(self.dag.kort, 2)
        layout.addLayout(lister)

    def _opbyg_kort(self):
        raekke = QGridLayout()
        raekke.setSpacing(12)
        self.kort = {}
        noegler = ["__aabne"] + self.statusser
        pr_raekke = len(noegler) if len(noegler) <= 4 else 3
        for i, noegle in enumerate(noegler):
            kort = lav_kort()
            kort.setMinimumHeight(104)
            lag = QVBoxLayout(kort)
            lag.setContentsMargins(16, 12, 16, 12)
            lag.setSpacing(2)
            top = QHBoxLayout()
            prik = QLabel("●")
            titel = QLabel("Åbne forløb" if noegle == "__aabne" else noegle)
            titel.setObjectName("statTitle")
            titel.setWordWrap(True)
            top.addWidget(prik)
            top.addWidget(titel, 1)
            vaerdi = QLabel("0")
            vaerdi.setObjectName("statValue")
            sub = QLabel("")
            sub.setObjectName("statSub")
            lag.addLayout(top)
            lag.addWidget(vaerdi)
            lag.addWidget(sub)
            self.kort[noegle] = (prik, vaerdi, sub)
            raekke.addWidget(kort, i // pr_raekke, i % pr_raekke)
        return raekke

    def _opbyg_diagrammer(self):
        raekke = QHBoxLayout()
        raekke.setSpacing(14)

        donut_kort = lav_kort()
        donut_layout = QVBoxLayout(donut_kort)
        donut_layout.setContentsMargins(20, 18, 20, 18)
        titel = QLabel("Statusfordeling")
        titel.setObjectName("cardTitle")
        self.donut = DonutChart()
        donut_layout.addWidget(titel)
        donut_layout.addWidget(self.donut, 1)
        self.forklaring = QLabel("")
        self.forklaring.setTextFormat(Qt.TextFormat.RichText)
        self.forklaring.setWordWrap(True)
        donut_layout.addWidget(self.forklaring)

        soejle_kort = lav_kort()
        soejle_layout = QVBoxLayout(soejle_kort)
        soejle_layout.setContentsMargins(20, 18, 20, 18)
        soejle_titel = QLabel(self.modul.datotitel)
        soejle_titel.setObjectName("cardTitle")
        self.soejlediagram = BarChart()
        soejle_layout.addWidget(soejle_titel)
        soejle_layout.addWidget(self.soejlediagram, 1)

        raekke.addWidget(donut_kort, 4)
        raekke.addWidget(soejle_kort, 7)
        return raekke

    def opdater(self, aktive, arkiverede, alarmer, dagens):
        i_dag = date.today()
        aabne = [s for s in aktive if not s.er_afsluttet()]
        tael = {status: sum(1 for s in aktive if s.status == status) for status in self.statusser}
        forsinkede = sum(1 for s in aabne if s.forsinkede_opgaver(i_dag))

        prik, vaerdi, sub = self.kort["__aabne"]
        prik.setStyleSheet(f"color: {FARVER['primary_hover']}; font-size: 11px;")
        vaerdi.setText(str(len(aabne)))
        sub.setText(f"{forsinkede} med forsinkede opgaver · {len(arkiverede)} arkiveret")
        for status in self.statusser:
            prik, vaerdi, sub = self.kort[status]
            prik.setStyleSheet(f"color: {status_stil(status)['farve']}; font-size: 11px;")
            vaerdi.setText(str(tael[status]))
            sub.setText(f"{round(tael[status] / len(aktive) * 100) if aktive else 0}% af aktive")

        self.donut.saet_data(
            [(s, tael[s], status_stil(s)["farve"]) for s in self.statusser], len(aktive), "aktive"
        )
        self.forklaring.setText("<br>".join(
            f'<span style="color:{status_stil(s)["farve"]};">●</span>&nbsp;{s} <b>{tael[s]}</b>'
            for s in self.statusser
        ))
        self._opdater_diagram(aabne)
        self.action.vis_alarmer(alarmer)
        self.dag.vis_opgaver(dagens)
        self.dato_label.setText(
            f"Aktive {self.modul.flertal}, afvigelser og kommende datoer · "
            f"{dansk_dato(QDate.currentDate())}"
        )

    def _opdater_diagram(self, sager):
        i_dag = QDate.currentDate()
        antal = {}
        for sag in sager:
            dato = laes_dato(self.modul.datofelt(sag))
            if dato.isValid():
                antal[dato] = antal.get(dato, 0) + 1
        data = []
        for i in range(self.DIAGRAM_DAGE):
            dato = i_dag.addDays(i)
            data.append((dato.day(), UGEDAGE_KORT[dato.dayOfWeek() - 1], antal.get(dato, 0),
                         i == 0, dato.dayOfWeek() >= 6))
        self.soejlediagram.saet_data(data)


def alarmer_for(modul_proces, alarmer):
    return [a for a in alarmer if a.modul == modul_proces]

