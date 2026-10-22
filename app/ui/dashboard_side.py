"""Dashboard / Action Center: samler det, der kræver handling, på tværs af
onboarding og offboarding – uden at blande modulernes egne sider sammen.

Fane 1 "Kræver handling": Action Center (afvigelser og næste handling) og
dagsoversigt. Fane 2 "Nøgletal": filtrerbare målepunkter.
"""
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from app.services.action_center import KRITISK, MODUL_NAVN
from app.ui.action_liste import ActionListe
from app.ui.hjaelpere import dansk_dato, lav_kort, lav_sidehoved
from app.ui.rapport_panel import RapportPanel


class DashboardSide(QWidget):
    def __init__(self, rapporter, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)
        hoved, self.dato_label = lav_sidehoved("Dashboard", "")
        layout.addLayout(hoved)

        self.faner = QTabWidget()
        self.faner.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.faner.addTab(self._opbyg_handling(), "Kræver handling")
        self.rapport = RapportPanel(rapporter)
        self.faner.addTab(self.rapport, "Nøgletal")
        self.faner.setTabToolTip(0, "Afvigelser og opgaver på tværs af onboarding og offboarding")
        self.faner.setTabToolTip(1, "Behandlingstider, frister og arbejdsfordeling")
        layout.addWidget(self.faner, 1)

    def _opbyg_handling(self):
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        self.resume = {}
        kort_raekke = QHBoxLayout()
        kort_raekke.setSpacing(12)
        for noegle, titel in (("kritisk", "Forsinkede opgaver"), ("onboarding", "Onboarding – åbne"),
                              ("offboarding", "Offboarding – åbne"), ("alle", "Punkter i alt")):
            kort = lav_kort()
            lag = QVBoxLayout(kort)
            lag.setContentsMargins(16, 12, 16, 12)
            lag.setSpacing(2)
            titel_label = QLabel(titel)
            titel_label.setObjectName("statTitle")
            vaerdi = QLabel("0")
            vaerdi.setObjectName("statValue")
            lag.addWidget(titel_label)
            lag.addWidget(vaerdi)
            self.resume[noegle] = vaerdi
            kort_raekke.addWidget(kort, 1)
        layout.addLayout(kort_raekke)

        lister = QHBoxLayout()
        lister.setSpacing(14)
        self.action = ActionListe(
            "Action Center",
            "Afvigelser og næste handling – klik for at åbne, højreklik for hurtige handlinger",
            parent=self,
        )
        self.dag = ActionListe("Dagsoversigt", "Opgaver med frist i dag", parent=self)
        lister.addWidget(self.action.kort, 3)
        lister.addWidget(self.dag.kort, 2)
        layout.addLayout(lister, 1)
        return side

    def opdater(self, sager_pr_modul: dict, alarmer, dagens):
        """sager_pr_modul: {proces: aktive + arkiverede sager} (arkiverede bruges af nøgletal)."""
        alle = [s for sager in sager_pr_modul.values() for s in sager]
        self.resume["kritisk"].setText(str(sum(a.niveau == KRITISK for a in alarmer)))
        for proces in MODUL_NAVN:
            aabne = [s for s in sager_pr_modul.get(proces, [])
                     if not s.arkiveret and not s.er_afsluttet()]
            self.resume[proces].setText(str(len(aabne)))
        self.resume["alle"].setText(str(len(alarmer)))
        self.action.vis_alarmer(alarmer)
        self.dag.vis_opgaver(dagens)
        self.rapport.opdater(alle)
        self.dato_label.setText(
            f"Det, der kræver handling på tværs af onboarding og offboarding · "
            f"{dansk_dato(QDate.currentDate())}"
        )

