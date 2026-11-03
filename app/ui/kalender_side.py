"""Siden Kalender: dag- og ugevisning af brugerens egne og delte kalendere.

Venstre: kalenderlisten i grupper – Mine kalendere, Delt med mig og (kun for
administratorer, skjult som standard) Andre kalendere – med vis/skjul, farve,
deling, ret/slet, ny kalender og import. Højre: KalenderVisning.

Data hentes, når siden åbnes, ved skift af periode og efter en handling – og fra
hovedvinduet, når minut-tjekket ser en ændring. Skjulte kalendere og egne farver
på delte kalendere huskes pr. bruger på pc'en (KalenderService.visningsvalg).
Begivenheder, brugeren kun må se som ledig/optaget, kan ikke åbnes; kalendere
delt til læsning åbnes skrivebeskyttet.
"""
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
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
    DelingDialog,
    ImportDialog,
    KalenderDialog,
    farve_ikon,
    spoerg_omfang,
)
from app.ui.kalender_visning import KalenderVisning, dage_i, tidsrum

DAG, UGE = "dag", "uge"
ID_ROLE = Qt.ItemDataRole.UserRole
_NIVEAU_TEKST = dict(kl.NIVEAUER)


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


def delt_tekst(kalender) -> str:
    """Notifikationen, når en kalender er delt med brugeren."""
    return (f"{kalender.ejer_navn or kalender.ejer} har delt kalenderen '{kalender.navn}' med dig "
            f"({_NIVEAU_TEKST.get(kalender.adgang, '').lower()}).")


class KalenderSide(QWidget):
    def __init__(self, service, hent_brugere=lambda: [], parent=None):
        super().__init__(parent)
        self.service = service
        self.hent_brugere = hent_brugere
        self._dag = date.today()
        self._visning = UGE
        self._kalendre = []
        self._forekomster = []
        self._valg = None               # visningsvalg (hentes ved første opdatering)
        self._rullet = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        hoved, _ = lav_sidehoved("Kalender", "Dine og dine kollegers delte kalendere. Klik eller "
                                 "træk i kalenderen for at oprette en begivenhed.")
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
        hjaelp = QLabel("Højreklik på en kalender for at dele den.")
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
        if self._valg is None:
            self._valg = self.service.visningsvalg()
        self._kalendre, self._forekomster = kalendre, forekomster
        self._vis_kalendre()
        self._vis()

    def ryd(self) -> None:
        self._kalendre, self._forekomster, self._valg = [], [], None
        self.liste.clear()
        self.visning.vis(self._dage(), [], {})

    def showEvent(self, event):
        super().showEvent(event)
        if not self._rullet:
            self._rullet = True
            self.visning.rul_til_morgen()

    def _valgt(self) -> dict:
        return self._valg or {"skjulte": [], "viste": [], "farver": {}}

    def _skjult(self, kalender) -> bool:
        valg = self._valgt()
        if kalender.adgang == kl.ADMIN_ADGANG:      # andres kalendere: skjult som standard
            return kalender.id not in valg["viste"]
        return kalender.id in valg["skjulte"]

    def _farve(self, kalender) -> str:
        return self._valgt()["farver"].get(kalender.id, kalender.farve) if not kalender.er_egen \
            else kalender.farve

    def _vis(self) -> None:
        skjulte = {k.id for k in self._kalendre if self._skjult(k)}
        synlige = [f for f in self._forekomster if f.begivenhed.kalender_id not in skjulte]
        self.visning.vis(self._dage(), synlige, {k.id: self._farve(k) for k in self._kalendre})
        self._vis_periode()

    def _vis_periode(self) -> None:
        self.periode.setText(periodetekst(self._visning, self._dage()))

    def _vis_kalendre(self) -> None:
        grupper = (
            ("Mine kalendere", [k for k in self._kalendre if k.er_egen]),
            ("Delt med mig", [k for k in self._kalendre if k.er_delt_med_mig]),
            ("Andre kalendere (administrator)",
             [k for k in self._kalendre if k.adgang == kl.ADMIN_ADGANG]),
        )
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
                tekst = k.navn if k.er_egen else f"{k.navn} · {k.ejer_navn or k.ejer}"
                item = QListWidgetItem(farve_ikon(self._farve(k)), tekst)
                item.setData(ID_ROLE, k.id)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                              | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked if self._skjult(k)
                                   else Qt.CheckState.Checked)
                if k.er_delt_med_mig:
                    item.setToolTip(f"Delt af {k.ejer_navn or k.ejer}: "
                                    f"{_NIVEAU_TEKST.get(k.adgang, '').lower()}")
                elif k.delinger:
                    item.setToolTip("Delt med " + ", ".join(d.navn or d.brugernavn
                                                            for d in k.delinger))
                self.liste.addItem(item)
        self.liste.blockSignals(False)

    def _gem_valg(self) -> None:
        udfoer(self, self.service.gem_visningsvalg, self._valgt())

    def _kalender_vist(self, item: QListWidgetItem) -> None:
        kalender = self._kalender(item.data(ID_ROLE))
        if kalender is None:
            return
        valg = self._valg = self._valgt()
        vist = item.checkState() == Qt.CheckState.Checked
        liste, tilfoej = (valg["viste"], vist) if kalender.adgang == kl.ADMIN_ADGANG \
            else (valg["skjulte"], not vist)
        if tilfoej and kalender.id not in liste:
            liste.append(kalender.id)
        elif not tilfoej and kalender.id in liste:
            liste.remove(kalender.id)
        self._gem_valg()
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

    def _skrivbare(self) -> list:
        """Kalendere, brugeren kan oprette begivenheder i (egne og delt til redigering)."""
        return [k for k in self._kalendre if k.kan_skrive]

    def _ny_nu(self) -> None:
        start = kl.dagens_start(self._dag) + timedelta(hours=9)
        self._ny(start, start + timedelta(hours=1), False)

    def _ny(self, start, slut, heldag: bool) -> None:
        kalendre = self._skrivbare()
        if not kalendre:
            return
        synlig = next((k for k in kalendre if k.er_egen and not self._skjult(k)), kalendre[0])
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
            QToolTip.showText(QCursor.pos(), "Optaget – detaljerne er ikke delt med dig.", self)
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

        kan_slette = kalender.kan_skrive or self.service.kan_administrere(kalender)
        if kalender.kan_skrive:
            dialog = BegivenhedDialog(self, self._skrivbare(), udgangspunkt, gem, slet,
                                      privat_mulig=kalender.er_egen)
        else:       # delt til læsning – administratorer kan slette (moderation)
            dialog = BegivenhedDialog(self, [kalender], udgangspunkt, None,
                                      slet if kan_slette else None)
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
        dialog = KalenderDialog(self, self.service, brugte_farver=[k.farve for k in self._kalendre])
        if dialog.exec():
            self.opdater()

    def _ret_kalender(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is not None and KalenderDialog(self, self.service, kalender).exec():
            self.opdater()

    def _del_kalender(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is None:
            return
        brugere = udfoer(self, self.hent_brugere)
        if brugere is FEJL:
            return
        DelingDialog(self, self.service, kalender, brugere).exec()
        self.opdater()

    def _egen_farve(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is None:
            return
        farve = QColorDialog.getColor(Qt.GlobalColor.white, self, "Farve (kun hos dig)")
        if farve.isValid():
            self._valg = self._valgt()
            self._valg["farver"][kalender.id] = farve.name()
            self._gem_valg()
            self._vis_kalendre()
            self._vis()

    def _forlad(self, kalender_id: str) -> None:
        kalender = self._kalender(kalender_id)
        if kalender is None:
            return
        svar = QMessageBox.question(
            self, "Fjern fra min liste",
            f"Fjern '{kalender.navn}' fra din liste? {kalender.ejer_navn or kalender.ejer} kan dele "
            "den med dig igen.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if svar == QMessageBox.StandardButton.Yes:
            self._efter(udfoer(self, self.service.forlad, kalender))

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
        if kalender is None:
            return
        menu = QMenu(self)
        if self.service.kan_administrere(kalender):
            menu.addAction("Del…", lambda: self._del_kalender(kalender.id))
        if kalender.er_egen:
            menu.addAction("Ret navn og farve…", lambda: self._ret_kalender(kalender.id))
        else:
            menu.addAction("Skift farve (kun hos mig)…", lambda: self._egen_farve(kalender.id))
        if kalender.er_delt_med_mig:
            menu.addAction("Fjern fra min liste…", lambda: self._forlad(kalender.id))
        if self.service.kan_administrere(kalender):
            menu.addSeparator()
            menu.addAction("Slet kalender…", lambda: self._slet_kalender(kalender.id))
        menu.exec(self.liste.mapToGlobal(pos))

    def _importer(self) -> None:
        dialog = ImportDialog(self, self.service, self._skrivbare())
        if dialog.exec():
            self.opdater()
