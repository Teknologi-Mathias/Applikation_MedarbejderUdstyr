"""Siden Kalender: dag- og ugevisning af egne og kollegers kalendere.

Alle ser alle kalendere (migrering 022). Venstre: kalenderlisten i to grupper –
Mine kalendere og Kollegers kalendere – hvor hver kalender slås til og fra med et
klik, samt ny kalender og import. Højre: KalenderVisning.

Hver kalender vises i sin egen farve: deler to kalendere farve, får den sidste en
ledig farve i visningen. Egne kalendere kan ændres; kollegers åbnes
skrivebeskyttet (administratorer kan slette – moderation). Private begivenheder i
andres kalendere vises som "Optaget" og kan ikke åbnes.

Data hentes, når siden åbnes, ved skift af periode og efter en handling – og fra
hovedvinduet, når minut-tjekket ser en ændring. Hvilke kalendere der er slået fra,
huskes pr. bruger på pc'en (KalenderService.skjulte).
"""
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.domain import kalender as kl
from app.domain.kalender import Begivenhed
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import MAANEDER, dansk_dato, lav_knap, lav_kort, lav_sidehoved
from app.ui.kalender_dialoger import (
    BegivenhedDialog,
    ImportDialog,
    KalenderDialog,
    farve_ikon,
    spoerg_omfang,
)
from app.ui.kalender_visning import KalenderVisning, dage_i, tidsrum

DAG, UGE = "dag", "uge"
ID_ROLE = Qt.ItemDataRole.UserRole


def periodetekst(visning: str, dage: list[date]) -> str:
    if visning == DAG:
        return dansk_dato(QDate(dage[0].year, dage[0].month, dage[0].day)).capitalize()
    foerste, sidste = dage[0], dage[-1]
    if foerste.month == sidste.month:
        periode = f"{foerste.day}.–{sidste.day}. {MAANEDER[sidste.month - 1]} {sidste.year}"
    else:
        periode = (f"{foerste.day}. {MAANEDER[foerste.month - 1]}"
                   + (f" {foerste.year}" if foerste.year != sidste.year else "")
                   + f" – {sidste.day}. {MAANEDER[sidste.month - 1]} {sidste.year}")
    return f"Uge {foerste.isocalendar().week} · {periode}"


def alarm_tekst(forekomst, nu) -> str:
    """Påmindelsens tekst, fx "I dag kl. 10:00 · Mødelokale 2"."""
    dage = (forekomst.start.date() - nu.date()).days
    dag = {0: "I dag", 1: "I morgen"}.get(dage, f"{forekomst.start:%d-%m-%Y}")
    tid = dag if forekomst.heldag else f"{dag} kl. {forekomst.start:%H:%M}"
    return tid + (f" · {forekomst.begivenhed.sted}" if forekomst.begivenhed.sted else "")


def egne_farver(kalendre: list) -> dict:
    """Kalender-id -> farve, så ingen to kalendere ser ens ud. Egne kalendere og de
    ældste beholder deres farve; en senere kalender med samme farve får en ledig."""
    farver, brugte = {}, []
    for k in sorted(kalendre, key=lambda k: not k.er_egen):
        farve = k.farve if k.farve.upper() not in brugte else kl.ledig_farve(brugte)
        farver[k.id] = farve
        brugte.append(farve.upper())
    return farver


class KalenderSide(QWidget):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._dag = date.today()
        self._visning = UGE
        self._kalendre = []
        self._forekomster = []
        self._farver = {}
        self._skjulte = None            # fravalgte kalendere (hentes ved første opdatering)
        self._rullet = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        hoved, _ = lav_sidehoved("Kalender", "Din og dine kollegers kalendere. Klik eller træk i "
                                 "kalenderen for at oprette en begivenhed.")
        layout.addLayout(hoved)

        vaerktoej = QHBoxLayout()
        forrige, i_dag, naeste = lav_knap("◀", tooltip="Forrige"), lav_knap("I dag"), \
            lav_knap("▶", tooltip="Næste")
        forrige.clicked.connect(lambda: self._flyt(-1))
        naeste.clicked.connect(lambda: self._flyt(1))
        i_dag.clicked.connect(self.gaa_til_i_dag)
        self.periode = QLabel("")
        self.periode.setObjectName("sektionTitel")
        self.dag_knap, self.uge_knap = lav_knap("Dag"), lav_knap("Uge")
        gruppe = QButtonGroup(self)
        for knap, visning in ((self.dag_knap, DAG), (self.uge_knap, UGE)):
            knap.setCheckable(True)
            gruppe.addButton(knap)
            knap.clicked.connect(lambda _c=False, v=visning: self.vaelg_visning(v))
        self.uge_knap.setChecked(True)
        ny = lav_knap("+ Ny begivenhed", "primary")
        ny.clicked.connect(self._ny_nu)
        for widget in (forrige, i_dag, naeste):
            vaerktoej.addWidget(widget)
        vaerktoej.addSpacing(12)
        vaerktoej.addWidget(self.periode)
        vaerktoej.addStretch()
        vaerktoej.addWidget(self.dag_knap)
        vaerktoej.addWidget(self.uge_knap)
        vaerktoej.addSpacing(12)
        vaerktoej.addWidget(ny)
        layout.addLayout(vaerktoej)

        krop = QHBoxLayout()
        krop.setSpacing(16)
        panel = lav_kort(skygge=False)
        panel.setFixedWidth(250)
        panel_lag = QVBoxLayout(panel)
        panel_lag.setContentsMargins(14, 14, 14, 14)
        titel = QLabel("Kalendere")
        titel.setObjectName("cardTitle")
        self.liste = QListWidget()
        self.liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._kalender_menu)
        self.liste.itemChanged.connect(self._kalender_vist)
        self.liste.itemDoubleClicked.connect(self._dobbeltklik)
        ny_kalender = lav_knap("+ Ny kalender")
        ny_kalender.clicked.connect(self._ny_kalender)
        importer = lav_knap("Importér .ics…", tooltip="Fx Google Kalender via Google Takeout")
        importer.clicked.connect(self._importer)
        hjaelp = QLabel("Klik på en kalender for at vise eller skjule den.")
        hjaelp.setObjectName("hjaelpTekst")
        hjaelp.setWordWrap(True)
        panel_lag.addWidget(titel)
        panel_lag.addWidget(self.liste, 1)
        panel_lag.addWidget(hjaelp)
        panel_lag.addWidget(ny_kalender)
        panel_lag.addWidget(importer)

        ramme = lav_kort(skygge=False)
        ramme_lag = QVBoxLayout(ramme)
        ramme_lag.setContentsMargins(0, 0, 0, 0)
        self.visning = KalenderVisning()
        self.visning.ny_begivenhed.connect(self._ny)
        self.visning.aabn.connect(self._aabn)
        ramme_lag.addWidget(self.visning)
        krop.addWidget(panel)
        krop.addWidget(ramme, 1)
        layout.addLayout(krop, 1)
        self._vis_periode()

    ### ----- data -----------------------------------------------------------

    def _dage(self) -> list[date]:
        return dage_i(self._visning, self._dag)

    def opdater(self) -> None:
        if not self.service.har_adgang():
            self.ryd()
            return
        kalendre = udfoer(self, self.service.kalendre)
        if kalendre is FEJL:
            return
        forekomster = udfoer(self, self.service.forekomster, *tidsrum(self._dage()))
        if forekomster is FEJL:
            return
        if self._skjulte is None:
            self._skjulte = self.service.skjulte()
        self._kalendre, self._forekomster = kalendre, forekomster
        self._farver = egne_farver(kalendre)
        self._vis_kalendre()
        self._vis()

    def ryd(self) -> None:
        self._kalendre, self._forekomster, self._farver, self._skjulte = [], [], {}, None
        self.liste.clear()
        self.visning.vis(self._dage(), [], {})

    def showEvent(self, event):
        super().showEvent(event)
        if not self._rullet:
            self._rullet = True
            self.visning.rul_til_morgen()

    def _skjult(self, kalender) -> bool:
        return kalender.id in (self._skjulte or set())

    def _vis(self) -> None:
        skjulte = self._skjulte or set()
        synlige = [f for f in self._forekomster if f.begivenhed.kalender_id not in skjulte]
        self.visning.vis(self._dage(), synlige, self._farver)
        self._vis_periode()

    def _vis_periode(self) -> None:
        self.periode.setText(periodetekst(self._visning, self._dage()))

    def _vis_kalendre(self) -> None:
        grupper = (("Mine kalendere", [k for k in self._kalendre if k.er_egen]),
                   ("Kollegers kalendere", [k for k in self._kalendre if not k.er_egen]))
        self.liste.blockSignals(True)
        self.liste.clear()
        for overskrift, kalendre in grupper:
            if not kalendre:
                continue
            hoved = QListWidgetItem(overskrift)
            hoved.setFlags(Qt.ItemFlag.NoItemFlags)
            skrift = QFont(self.liste.font())
            skrift.setBold(True)
            hoved.setFont(skrift)
            self.liste.addItem(hoved)
            for k in sorted(kalendre, key=lambda k: (k.ejer_navn.lower(), k.navn.lower())):
                tekst = k.navn if k.er_egen else f"{k.ejer_navn or k.ejer} · {k.navn}"
                item = QListWidgetItem(farve_ikon(self._farver.get(k.id, k.farve)), tekst)
                item.setData(ID_ROLE, k.id)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                              | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked if self._skjult(k)
                                   else Qt.CheckState.Checked)
                self.liste.addItem(item)
        self.liste.blockSignals(False)

    def _kalender_vist(self, item: QListWidgetItem) -> None:
        kalender_id = item.data(ID_ROLE)
        if kalender_id is None:
            return
        self._skjulte = set(self._skjulte or set())
        if item.checkState() == Qt.CheckState.Checked:
            self._skjulte.discard(kalender_id)
        else:
            self._skjulte.add(kalender_id)
        udfoer(self, self.service.gem_skjulte, self._skjulte)
        self._vis()

    ### ----- navigation -----------------------------------------------------

    def vaelg_visning(self, visning: str) -> None:
        self._visning = visning
        (self.dag_knap if visning == DAG else self.uge_knap).setChecked(True)
        self.opdater()

    def _flyt(self, retning: int) -> None:
        self._dag += timedelta(days=retning * (1 if self._visning == DAG else 7))
        self.opdater()

    def gaa_til_i_dag(self) -> None:
        self._dag = date.today()
        self.opdater()
        self.visning.rul_til_morgen()

    ### ----- begivenheder ---------------------------------------------------

    def _egne(self) -> list:
        """Kalendere, brugeren kan oprette begivenheder i."""
        return [k for k in self._kalendre if k.er_egen]

    def _ny_nu(self) -> None:
        start = kl.dagens_start(self._dag) + timedelta(hours=9)
        self._ny(start, start + timedelta(hours=1), False)

    def _ny(self, start, slut, heldag: bool) -> None:
        kalendre = self._egne()
        if not kalendre:
            return
        synlig = next((k for k in kalendre if not self._skjult(k)), kalendre[0])
        ny = Begivenhed(synlig.id, "", start, slut, heldag=heldag)

        def gem(resultat) -> bool:
            return self._efter(udfoer(dialog, self.service.gem, resultat,
                                      efter_konflikt=self.opdater))

        dialog = BegivenhedDialog(self, kalendre, ny, gem)
        dialog.exec()

    def _aabn(self, forekomst) -> None:
        b = forekomst.begivenhed
        kalender = self._kalender(b.kalender_id)
        if b.maskeret or kalender is None:
            QToolTip.showText(QCursor.pos(), "Optaget – aftalen er privat.", self)
            return
        serie = udfoer(self, self.service.serie_for, forekomst, efter_konflikt=self.opdater)
        if serie is FEJL:
            return
        udgangspunkt = b.kopi(start=forekomst.start, slut=forekomst.slut,
                              gentagelse=serie.gentagelse if forekomst.i_serie else b.gentagelse)

        def gem(resultat) -> bool:
            omfang = None
            if forekomst.i_serie:
                omfang = spoerg_omfang(dialog, "Gem ændringer i")
                if omfang is None:
                    return False
            return self._efter(udfoer(dialog, self.service.gem_forekomst, forekomst, resultat,
                                      omfang, efter_konflikt=self.opdater))

        def slet() -> bool:
            if forekomst.i_serie:
                omfang = spoerg_omfang(dialog, "Slet")
                if omfang is None:
                    return False
            else:
                omfang = None
                if QMessageBox.question(dialog, "Slet begivenhed", f"Slet '{b.titel}'?") \
                        != QMessageBox.StandardButton.Yes:
                    return False
            return self._efter(udfoer(dialog, self.service.slet_forekomst, forekomst, omfang,
                                      efter_konflikt=self.opdater))

        if kalender.er_egen:
            dialog = BegivenhedDialog(self, self._egne(), udgangspunkt, gem, slet)
        else:       # en kollegas – kun visning; administratorer kan slette (moderation)
            dialog = BegivenhedDialog(self, [kalender], udgangspunkt, None,
                                      slet if self.service.kan_administrere(kalender) else None)
        dialog.exec()

    def _efter(self, resultat) -> bool:
        """Efter en gemning/sletning: hent igen. True, hvis handlingen lykkedes."""
        if resultat is FEJL:
            return False
        self.opdater()
        return True

    ### ----- kalendere ------------------------------------------------------

    def _kalender(self, kalender_id: str):
        return next((k for k in self._kalendre if k.id == kalender_id), None)

    def _dobbeltklik(self, item: QListWidgetItem) -> None:
        kalender = self._kalender(item.data(ID_ROLE))
        if kalender is not None and kalender.er_egen:
            self._ret_kalender(kalender.id)

    def _ny_kalender(self) -> None:
        dialog = KalenderDialog(self, self.service, brugte_farver=list(self._farver.values()))
        if dialog.exec():
            self.opdater()

    def _ret_kalender(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is not None and KalenderDialog(self, self.service, kalender).exec():
            self.opdater()

    def _slet_kalender(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is None:
            return
        ejer = "" if kalender.er_egen else f" (tilhører {kalender.ejer_navn or kalender.ejer})"
        svar = QMessageBox.question(
            self, "Slet kalender",
            f"Slet kalenderen '{kalender.navn}'{ejer} og alle dens begivenheder? Det kan ikke "
            "fortrydes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if svar == QMessageBox.StandardButton.Yes:
            self._efter(udfoer(self, self.service.slet_kalender, kalender))

    def _kalender_menu(self, pos) -> None:
        item = self.liste.itemAt(pos)
        kalender = self._kalender(item.data(ID_ROLE)) if item is not None else None
        if kalender is None or not self.service.kan_administrere(kalender):
            return
        menu = QMenu(self)
        if kalender.er_egen:
            menu.addAction("Ret navn og farve…", lambda: self._ret_kalender(kalender.id))
            menu.addSeparator()
        menu.addAction("Slet kalender…", lambda: self._slet_kalender(kalender.id))
        menu.exec(self.liste.mapToGlobal(pos))

    def _importer(self) -> None:
        dialog = ImportDialog(self, self.service, self._egne())
        if dialog.exec():
            self.opdater()
