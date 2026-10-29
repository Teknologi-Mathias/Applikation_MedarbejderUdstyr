"""Hovedvinduet: sætter siderne sammen, holder data friske og styrer log på,
roller, tema og baggrundsdrift.

Hovedvinduet indeholder ingen forretningsregler. Handlinger på sager går
til modulernes controllere (app/ui/modul_controller.py), som kalder
services. Data hentes fra services og deles ud til siderne.

Session: hvert minut kontrolleres det, at sessionen stadig er gyldig, og at
brugeren stadig er aktiv med samme rolle. Er den udløbet, eller er adgangen
lukket, logges brugeren ud på en kontrolleret måde (åbne dialoger lukkes,
data fjernes fra siderne, log på-skærmen vises).
"""
import logging
import time
from dataclasses import replace
from datetime import date

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAVN, session
from app.domain import adgang
from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.repositories.fejl import DataFejl, KompatibilitetsFejl, SessionUdloebetFejl
from app.services import action_center
from app.services import kontrolrum
from app.ui import fejl as ui_fejl
from app.ui.action_liste import ANSVARLIG
from app.ui.arbejdsbakke_side import ArbejdsbakkeSide
from app.ui.baggrund import koer_i_baggrund
from app.ui.dashboard_side import DashboardSide
from app.ui.fejl import FEJL, udfoer
from app.ui.hjaelpere import lav_app_ikon, lav_knap, lav_sidehoved
from app.ui.indmelding_side import IndmeldingSide
from app.ui.indstillinger_side import IndstillingerSide
from app.ui.login_dialog import LoginDialog
from app.ui.mdm_side import MdmArkivSide, MdmSide
from app.ui.modul_controller import OffboardingController, OnboardingController
from app.ui.modul_oversigt import ModulOversigtSide, alarmer_for
from app.ui.moduler import offboarding_modul, onboarding_modul
from app.ui.notifikationer import Notifikationer
from app.ui.opdatering_dialog import OpdateringDialog
from app.ui.opgave_oversigt_side import OpgaveOversigtSide
from app.ui.sag_liste_side import SagListeSide
from app.ui.sidebar import FORBINDER, INDSTILLINGER, MISTET, ONLINE, Sidebar
from app.ui.skabelon_side import SkabelonSide
from app.ui.teamoverblik_side import TeamoverblikSide
from app.ui.theme import anvend_tema

log = logging.getLogger(__name__)

ON, OFF = OnboardingForloeb.PROCES, Medarbejder.PROCES
MODUL_FOR_PROCES = {ON: adgang.ONBOARDING, OFF: adgang.OFFBOARDING}
LAAS = "  🔒"

# Venstremenuen viser hovedområderne; et områdes undersider vises som faner øverst
# i arbejdsområdet (et område med én side har ingen faner). Indstillinger er
# tandhjulet ved brugerområdet. Sidenøglerne styrer adgangen (adgang.modul_for_side):
# alle områder ses af alle; moduler uden adgang vises med 🔒 og LaastSide.
# (nøgle, menutekst, ikon, [(side, fanetekst), ...])
OMRAADER = [
    ("overblik", "Arbejdsoverblik", "overblik", [("dashboard", "Arbejdsoverblik")]),
    ("arbejdsbakke", "Arbejdsbakke", "bakke", [("arbejdsbakke", "Arbejdsbakke")]),
    ("onboarding", "Onboarding - MERCH", "onboarding", [
        ("on_team", "Teamoverblik"),
        ("on_oversigt", "Oversigt"),
        ("on_aktive", "Aktive forløb"),
        ("on_opgaver", "Opgaver og milepæle"),
        ("on_skabeloner", "Skabeloner"),
        ("on_arkiv", "Arkiv og annullerede"),
    ]),
    ("offboarding", "Offboarding - HAFRA", "offboarding", [
        ("off_oversigt", "Oversigt"),
        ("off_aktive", "Aktive forløb"),
        ("off_opgaver", "Opgaver og udstyr"),
        ("off_skabeloner", "Skabeloner og mails"),
        ("off_arkiv", "Arkiv"),
    ]),
    ("telefoner", "Telefoner (MDM)", "telefon", [
        ("telefoner", "Telefoner"),
        ("telefoner_arkiv", "Arkiv"),
    ]),
    ("oensker", "Ønsker & Udvikling", "oensker", [("oensker", "Ønsker & Udvikling")]),
]
# Side -> område (Indstillinger hører ikke til et område).
OMRAADE_FOR_SIDE = {side: noegle for noegle, _, _, sider in OMRAADER for side, _ in sider}
ALLE_SIDER = [side for _, _, _, sider in OMRAADER for side, _ in sider] + [INDSTILLINGER]


class LaastSide(QWidget):
    """Vises i stedet for et modul, brugeren ikke har adgang til."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        hoved, _ = lav_sidehoved("Ingen adgang", "")
        layout.addLayout(hoved)
        self.tekst = QLabel("")
        self.tekst.setObjectName("advarsel")
        self.tekst.setWordWrap(True)
        layout.addWidget(self.tekst)
        layout.addStretch()

    def vis(self, modul: str) -> None:
        navn = adgang.MODULER.get(modul, modul)
        self.tekst.setText(f"🔒  Du har ikke adgang til {navn}. Kontakt en administrator, hvis "
                           "du skal have adgang.")


class MainWindow(QMainWindow):
    OPDATERINGS_INTERVAL = 60_000  # 60 sekunder, angivet i millisekunder
    VERSIONS_TJEK = 4 * 3600       # sekunder mellem tjek for en ny version af IN-BASE

    def __init__(self, tjenester):
        super().__init__()
        self.t = tjenester
        self.setWindowTitle(APP_NAVN)
        self.setWindowIcon(lav_app_ikon())
        self.resize(1360, 880)
        self.setMinimumSize(1100, 720)

        self.notifikationer = Notifikationer(lav_app_ikon(), self)
        self.notifikationer.vis_vindue.connect(self.vis_fra_baggrund)
        self.notifikationer.afslut.connect(self.afslut)
        self.notifikationer.aabn_sag.connect(self.aabn_sag)
        self._afslutter = False
        self._baggrund_forklaret = False
        self._backup_fejl_vist = False
        self._logger_ud = False
        # Central opdatering (app/services/opdatering_service.py).
        self.instans = None              # EnkeltInstans (main.py) – frigives før en opdatering
        self._opdatering = None          # seneste Status fra find()
        self._opdatering_fil = None      # hentet og kontrolleret installer
        self._opdatering_tjekker = False
        self._opdatering_tjekket = None  # time.monotonic() for seneste tjek
        self._opdatering_meldt = None    # version, der er vist en notifikation for
        ui_fejl.saet_session_haandtering(self._session_udloebet)
        # Med ikon ved uret lukkes programmet kun via "Afslut".
        QApplication.instance().setQuitOnLastWindowClosed(not self.notifikationer.tilgaengelig)

        self.ctrl = {
            ON: OnboardingController(self, tjenester, tjenester.onboarding),
            OFF: OffboardingController(self, tjenester, tjenester.offboarding),
        }
        self.data = {ON: ([], []), OFF: ([], [])}   # proces -> (aktive, arkiverede)
        self._signatur = {}             # proces -> (aktive, arkiv) fra seneste hentning
        self._indstillinger = {}        # fælles indstillinger fra seneste hentning
        self._generation = 0            # tælles op ved hver lokal ændring/hentning
        self._tikker = False            # et minut-tjek kører i baggrunden

        self._opbyg_gui()
        self._daglig_backup()

        self.timer = QTimer(self)
        self.timer.setInterval(self.OPDATERINGS_INTERVAL)
        self.timer.timeout.connect(self._minut_tik)
        self.timer.start()

    ### ----- opbygning ------------------------------------------------------

    def _opbyg_gui(self):
        central = QWidget()
        central.setObjectName("pageRoot")
        self.setCentralWidget(central)
        rod = QHBoxLayout(central)
        rod.setContentsMargins(0, 0, 0, 0)
        rod.setSpacing(0)

        self.sidebar = Sidebar(OMRAADER)
        self.sidebar.omraade_valgt.connect(self.vis_omraade)
        self.sidebar.log_ud.connect(self.log_ud)
        self.sidebar.opdatering_valgt.connect(self.vis_opdatering)
        self.stak = QStackedWidget()
        # Kontekstuel topmenu: det aktive områdes undersider.
        self._omraade = None
        self._sidste_side = {}          # område -> senest viste underside
        self.faner = QTabBar()
        self.faner.setExpanding(False)
        self.faner.setDrawBase(False)
        self.faner.setCursor(Qt.CursorShape.PointingHandCursor)
        self.faner.currentChanged.connect(self._fane_valgt)
        self.fane_ramme = QWidget()
        self.fane_ramme.setObjectName("omraadeFaner")
        fane_lag = QHBoxLayout(self.fane_ramme)
        fane_lag.setContentsMargins(32, 18, 32, 0)
        fane_lag.addWidget(self.faner)
        fane_lag.addStretch()
        arbejdsomraade = QVBoxLayout()
        arbejdsomraade.setContentsMargins(0, 0, 0, 0)
        arbejdsomraade.setSpacing(0)
        arbejdsomraade.addWidget(self.fane_ramme)
        arbejdsomraade.addWidget(self.stak, 1)
        rod.addWidget(self.sidebar)
        rod.addLayout(arbejdsomraade, 1)

        self.sider = {}
        self.dashboard = DashboardSide(self.t.rapporter)
        self._forbind_action(*self.dashboard.handlingslister())
        self.dashboard.vis_liste.connect(self._vis_filtreret)
        self._tilfoej("dashboard", self.dashboard)
        self.arbejdsbakke = ArbejdsbakkeSide()
        self._forbind_action(self.arbejdsbakke)
        self._tilfoej("arbejdsbakke", self.arbejdsbakke)
        self.teamoverblik = TeamoverblikSide()
        self.teamoverblik.aabn_sag.connect(self.aabn_sag)
        self._tilfoej("on_team", self.teamoverblik)
        self._opbyg_onboarding()
        self._opbyg_offboarding()
        self.oensker = IndmeldingSide(self.t.indmeldinger, self._aktive_brugernavne)
        self._tilfoej("oensker", self.oensker)
        self.telefoner = MdmSide(self.t.mdm)
        self._tilfoej("telefoner", self.telefoner)
        self.telefoner_arkiv = MdmArkivSide(self.t.mdm)
        self._tilfoej("telefoner_arkiv", self.telefoner_arkiv)
        self.indstillinger = IndstillingerSide(
            self.t, self._alle_arkiverede, self._alle_aktive, self.notifikationer.vis_besked,
        )
        self.indstillinger.generelt.tema_valgt.connect(self.skift_tema)
        self.indstillinger.generelt.notifikationer_valgt.connect(self._saet_notifikationer)
        self.indstillinger.generelt.lagring_skiftet.connect(self._lagring_skiftet)
        self.indstillinger.data.data_aendret.connect(self.opdater_alle)
        self._tilfoej("indstillinger", self.indstillinger)
        self.laast_side = LaastSide()
        self.stak.addWidget(self.laast_side)
        self.vis_side("dashboard")

    def _tilfoej(self, noegle, side):
        self.sider[noegle] = side
        self.stak.addWidget(side)

    def _forbind_action(self, *lister):
        for liste in lister:
            liste.aabn_sag.connect(self.aabn_sag)
            liste.handling.connect(
                lambda handling, proces, sag_id, opgave_id:
                self.ctrl[proces].action_handling(handling, sag_id, opgave_id)
            )

    def _paa_valgt(self, side, funktion):
        sag_id = side.valgt_id()
        if sag_id is None:
            QMessageBox.information(self, "Ingen valgt", "Vælg en sag i listen først.")
            return
        funktion(sag_id)

    def _handlingsmenu(self, side, punkter):
        menu = QMenu(self)
        for tekst, funktion in punkter:
            if tekst is None:
                menu.addSeparator()
            elif funktion is None:
                menu.addAction(tekst).setEnabled(False)       # fx under udvikling
            else:
                menu.addAction(tekst, lambda f=funktion: self._paa_valgt(side, f))
        knap = QToolButton()
        knap.setText("Handling")
        knap.setProperty("variant", "menu")
        knap.setCursor(Qt.CursorShape.PointingHandCursor)
        knap.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        knap.setMenu(menu)
        knap.setToolTip("Handlinger på den valgte sag")
        return knap

    def _modul_sider(self, prefix, modul, ctrl, opgave_titel, ekstra, knapper, handlinger,
                     skabelon_slags, arkiv_titel):
        """Bygger et moduls fem undersider ud fra samme fælles komponenter."""
        oversigt = ModulOversigtSide(modul)
        self._forbind_action(oversigt.action, oversigt.dag)

        aktive = SagListeSide(f"{modul.navn} – aktive forløb",
                              f"Aktive {modul.flertal}. Status beregnes ud fra opgaver og milepæle.",
                              modul.kolonner, filtre=modul.filtre)
        opret = lav_knap(modul.opret_tekst, "primary")
        opret.clicked.connect(ctrl.opret)
        aktive.tilfoej_knap(opret)
        for tekst, funktion, variant in knapper:
            knap = lav_knap(tekst, variant)
            knap.clicked.connect(lambda _=False, f=funktion: self._paa_valgt(aktive, f))
            aktive.tilfoej_knap(knap)
        aktive.tilfoej_handling(self._handlingsmenu(aktive, handlinger))
        aktive.tabel.doubleClicked.connect(lambda _i: self._paa_valgt(aktive, ctrl.aabn_sag))
        aktive.celle_klik.connect(ctrl.hurtig_status)

        opgaver = OpgaveOversigtSide(f"{modul.navn} – {opgave_titel.lower()}",
                                     f"Åbne opgaver på tværs af alle aktive {modul.flertal}. "
                                     "Dobbeltklik for at åbne sagen.", ekstra)
        opgaver.aabn_sag.connect(self.aabn_sag)

        skabeloner = SkabelonSide(self.t.skabeloner, skabelon_slags, proces=modul.proces,
                                  titel=f"{modul.navn} – skabeloner",
                                  hent_sager=lambda p=modul.proces: self.data[p][0])

        # Arkivet er kun til visning: statusprikkerne kan ikke klikkes der.
        arkiv = SagListeSide(arkiv_titel, "Afsluttede forløb. Dobbeltklik for at se sagen.",
                             [replace(k, klik="") for k in modul.kolonner], filtre=modul.filtre)
        arkiv.tabel.doubleClicked.connect(lambda _i: self._paa_valgt(arkiv, ctrl.aabn_sag))
        slet = lav_knap("Slet permanent", "danger")
        for knap, funktion in ((lav_knap("Vis sag"), ctrl.aabn_sag),
                               (lav_knap("Gør aktiv igen"), ctrl.aktiver), (slet, ctrl.slet)):
            knap.clicked.connect(lambda _=False, f=funktion: self._paa_valgt(arkiv, f))
            arkiv.tilfoej_knap(knap)

        for navn, side in (("oversigt", oversigt), ("aktive", aktive), ("opgaver", opgaver),
                           ("skabeloner", skabeloner), ("arkiv", arkiv)):
            self._tilfoej(f"{prefix}_{navn}", side)
        return slet

    def _opbyg_onboarding(self):
        modul = onboarding_modul(self._omraader, self._ansvarlige)
        ctrl = self.ctrl[ON]
        self.on_slet = self._modul_sider(
            "on", modul, ctrl, "Opgaver og milepæle", "milepael",
            [("Åbn forløb", ctrl.aabn_sag, None), ("Rediger / status", ctrl.rediger, None),
             ("Arkivér", ctrl.arkiver, "danger")],
            [("Tildel ansvarlig…", lambda sag_id: ctrl.action_handling(ANSVARLIG, sag_id, "")),
             ("Tilføj notat til tidslinjen…", ctrl.tilfoej_notat), (None, None),
             ("Vis tidslinje", ctrl.vis_historik)],
            [sk.SAG], "Onboarding – arkiv og annullerede",
        )

    def _opbyg_offboarding(self):
        modul = offboarding_modul()
        ctrl = self.ctrl[OFF]
        self.off_slet = self._modul_sider(
            "off", modul, ctrl, "Opgaver og udstyr", "udstyr",
            [("Åbn sag", ctrl.aabn_sag, None), ("Rediger", ctrl.rediger, None),
             ("Arkivér", ctrl.arkiver, "danger")],
            [("Opret rykker…", ctrl.opret_rykker),
             ("Marker rykker som sendt…", ctrl.marker_rykker_sendt),
             ("Registrér returlabel som sendt (under udvikling)", None),
             ("Tilføj notat til tidslinjen…", ctrl.tilfoej_notat), (None, None),
             ("Vis tidslinje", ctrl.vis_historik)],
            [sk.SAG, sk.MAIL], "Offboarding – arkiv",
        )

    ### ----- data -----------------------------------------------------------

    def _alle_aktive(self):
        return self.data[ON][0] + self.data[OFF][0]

    def _alle_arkiverede(self):
        return self.data[ON][1] + self.data[OFF][1]

    def _omraader(self):
        ind = udfoer(self, self.t.indstillinger.hent)
        return [] if ind is FEJL else ind["omraader"]

    def _ansvarlige(self):
        return sorted({s.ansvarlig for s in self.data[ON][0] + self.data[ON][1] if s.ansvarlig})

    def _aktive_brugernavne(self):
        brugere = udfoer(self, self.t.auth.brugere)
        return [] if brugere is FEJL else sorted(
            b["brugernavn"] for b in brugere if b.get("aktiv", True))

    def _hent(self, tving: bool, kendte: dict) -> dict:
        """Netværksdelen af en opdatering – kan køre i baggrunden (rører ingen widgets).

        Signaturen har en halvdel for aktive og en for arkiverede sager; kun de
        lister, hvis halvdel er ændret siden sidst, hentes (tving=True: alle). Moduler
        uden adgang hentes ikke (vises heller ikke på dashboardet). Resultatet lægges
        ind af _anvend() på UI-tråden.
        """
        start = time.monotonic()
        resultat = {"signaturer": {}, "data": {}, "indstillinger": self.t.indstillinger.hent()}
        for proces, service in ((ON, self.t.onboarding), (OFF, self.t.offboarding)):
            if not session.har_adgang(MODUL_FOR_PROCES[proces]):
                resultat["signaturer"][proces] = None
                resultat["data"][proces] = ([], [])
                continue
            signatur = service.signatur()
            kendt = None if tving else kendte.get(proces)
            resultat["signaturer"][proces] = signatur
            resultat["data"][proces] = (
                service.hent_aktive() if kendt is None or signatur[0] != kendt[0] else None,
                service.hent_arkiverede() if kendt is None or signatur[1] != kendt[1] else None,
            )
        hentet = [f"{proces} {navn} {len(liste)}" for proces, lister in resultat["data"].items()
                  for navn, liste in zip(("aktive", "arkiv"), lister) if liste]
        if hentet:
            log.info("Data hentet på %.2f s: %s", time.monotonic() - start, ", ".join(hentet))
        return resultat

    def _anvend(self, resultat: dict) -> None:
        """Lægger de hentede lister ind (None = uændret) og husker signaturerne."""
        for proces, (aktive, arkiv) in resultat["data"].items():
            gamle = self.data[proces]
            self.data[proces] = (gamle[0] if aktive is None else aktive,
                                 gamle[1] if arkiv is None else arkiv)
        self._signatur = dict(resultat["signaturer"])
        self._indstillinger = resultat["indstillinger"]

    def sag_gemt(self, sag) -> None:
        """En sag er netop gemt her: læg den ind i listerne og vis – uden at hente alt
        igen. Signaturen røres ikke, så næste minut-tjek henter den ændrede liste én gang
        (og et minut-tjek, der var i gang, kasseres – det er ældre end denne ændring)."""
        self._generation += 1
        aktive, arkiv = (list(liste) for liste in self.data[sag.PROCES])
        maal, anden = (arkiv, aktive) if sag.arkiveret else (aktive, arkiv)
        anden[:] = [s for s in anden if s.id != sag.id]
        index = next((i for i, s in enumerate(maal) if s.id == sag.id), None)
        if index is None:
            maal.append(sag)
        else:
            maal[index] = sag
        self.data[sag.PROCES] = (aktive, arkiv)
        self.vis_data()

    def _saet_forbindelse(self, tilstand):
        """Kun relevant uden for JSON-offline-tilstanden (som har sin egen visning)."""
        if self.t.lagring.offline:
            return
        if tilstand == ONLINE:
            self._sidst_ok = QTime.currentTime().toString("HH:mm")
        self.sidebar.saet_forbindelse(tilstand, getattr(self, "_sidst_ok", ""))

    def opdater_alle(self, tving=True):
        """Henter data i forgrunden (tving: alle lister; ellers kun de ændrede) og
        opdaterer siderne. Minut-tjekket bruger i stedet _opdater_i_baggrund()."""
        self._generation += 1
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            resultat = self._hent(tving, self._signatur)
        except SessionUdloebetFejl as fejl:
            QApplication.restoreOverrideCursor()
            self._session_udloebet(fejl)
            return
        except DataFejl as fejl:
            QApplication.restoreOverrideCursor()
            log.exception("Data kunne ikke indlæses")
            self._saet_forbindelse(MISTET)
            QMessageBox.critical(self, "Datafejl", str(fejl))
            return
        QApplication.restoreOverrideCursor()
        self._anvend(resultat)
        self.vis_data()
        self._opdater_aktuel_side()

    def _opdater_aktuel_side(self):
        """Sider med egne data (skabeloner, indstillinger, ønsker) hentes, når de vises."""
        aktuel = self.stak.currentWidget()
        if isinstance(aktuel, (SkabelonSide, IndstillingerSide, IndmeldingSide)):
            aktuel.opdater()

    def vis_data(self):
        """Opdaterer alle sider ud fra de data, vinduet har – uden netværk. Kaldes også
        uden nye data, fordi frister og alarmer følger datoen."""
        regler = action_center.Regler.fra_indstillinger(self._indstillinger)
        i_dag = date.today()
        aktive = self._alle_aktive()
        alarmer = action_center.action_center(aktive, i_dag, regler)
        dagens = action_center.dagsoversigt(aktive, i_dag)

        self.dashboard.opdater({ON: self.data[ON][0] + self.data[ON][1],
                                OFF: self.data[OFF][0] + self.data[OFF][1]}, alarmer, dagens,
                               regler)
        self.arbejdsbakke.opdater(aktive)
        self.teamoverblik.opdater(self.data[ON][0], regler.naermer_sig_dage)
        for proces, prefix in ((ON, "on"), (OFF, "off")):
            aktive_sager, arkiv = self.data[proces]
            self.sider[f"{prefix}_oversigt"].opdater(
                aktive_sager, arkiv, alarmer_for(proces, alarmer),
                [(s, o) for s, o in dagens if s.PROCES == proces],
            )
            self.sider[f"{prefix}_aktive"].vis(aktive_sager)
            self.sider[f"{prefix}_opgaver"].opdater(aktive_sager)
            self.sider[f"{prefix}_arkiv"].vis(arkiv)
        self.sidebar.saet_lagring(self.t.lagring.offline,
                                  len(self.t.lagring.ventende_aendringer()),
                                  self.t.lagring.kilde)
        self._saet_forbindelse(ONLINE)
        self.sidebar.opdateret_label.setText(
            f"Sidst opdateret {QTime.currentTime().toString('HH:mm')}")

    def _minut_tik(self):
        if session.bruger() is None:
            return
        self._daglig_backup()   # programmet kan køre i flere døgn i baggrunden
        self._opdater_i_baggrund()
        if self._opdatering_tjekket is None \
                or time.monotonic() - self._opdatering_tjekket >= self.VERSIONS_TJEK:
            self._tjek_opdatering()

    def _tik(self, kendte: dict, med_paamindelser: bool) -> dict:
        """Baggrundstråd: sessionstjek, de ændrede lister og påmindelsesskabelonerne.
        En udløbet session eller lukket adgang kaster SessionUdloebetFejl (log ud)."""
        self.t.auth.kontroller_session()
        resultat = self._hent(False, kendte)
        resultat["paamindelser"] = (self.t.skabeloner.aktive(sk.PAAMINDELSE)
                                    if med_paamindelser else None)
        return resultat

    def _opdater_i_baggrund(self):
        """Minut-tjekket uden at fryse vinduet. Kun ét ad gangen."""
        if self._tikker:
            return
        self._tikker = True
        generation = self._generation
        koer_i_baggrund(self._tik, dict(self._signatur), self.notifikationer.slaaet_til,
                        naar_faerdig=lambda resultat: self._tik_faerdig(resultat, generation),
                        ved_fejl=self._tik_fejl)

    def _tik_faerdig(self, resultat: dict, generation: int):
        self._tikker = False
        if session.bruger() is None or generation != self._generation:
            return   # logget ud, eller der er gemt/hentet imens – næste tik henter igen
        self._anvend(resultat)
        self.vis_data()
        self._opdater_aktuel_side()
        if resultat["paamindelser"] is not None:
            self._vis_paamindelser_fra(resultat["paamindelser"])

    def _tik_fejl(self, fejl: Exception):
        self._tikker = False
        if isinstance(fejl, SessionUdloebetFejl):
            self._session_udloebet(fejl)
        elif isinstance(fejl, DataFejl):     # fx ingen forbindelse – kun indikatoren i menuen
            log.warning("Minut-tjekket mislykkedes: %s", fejl)
            self._saet_forbindelse(MISTET)
        else:
            log.error("Minut-tjekket fejlede", exc_info=fejl)

    def _vis_paamindelser(self):
        """Windows-notifikationer – kun hvis brugeren har dem slået til."""
        if not self.notifikationer.slaaet_til or session.bruger() is None:
            return
        skabeloner = udfoer(self, self.t.skabeloner.aktive, sk.PAAMINDELSE)
        if skabeloner is not FEJL:
            self._vis_paamindelser_fra(skabeloner)

    def _vis_paamindelser_fra(self, skabeloner):
        if not self.notifikationer.slaaet_til or session.bruger() is None:
            return
        self.notifikationer.vis_paamindelser(
            self.t.paamindelser.nye_paamindelser(skabeloner, self._alle_aktive(), date.today())
        )

    def _daglig_backup(self):
        """Tager dagens backup (én gang pr. dag). Fejl vises én gang pr. kørsel.

        Kun JSON-tilstanden – i Supabase-tilstand tager Supabase backup af databasen.
        """
        if self.t.backup is None:
            return
        try:
            self.t.backup.daglig_backup()
        except (DataFejl, OSError) as fejl:
            log.exception("Daglig backup mislykkedes")
            if not self._backup_fejl_vist:
                self._backup_fejl_vist = True
                QMessageBox.warning(self, "Sikkerhedskopi",
                                    f"Dagens automatiske backup kunne ikke tages:\n{fejl}\n\n"
                                    "Se Indstillinger → Data & sikkerhed.")

    ### ----- navigation -----------------------------------------------------

    def vis_omraade(self, omraade):
        """Menuknap: områdets senest viste underside (ellers den første)."""
        if omraade == INDSTILLINGER:
            return self.vis_side(INDSTILLINGER)
        sider = self._sider_i(omraade)
        self.vis_side(self._sidste_side.get(omraade, sider[0][0]))

    @staticmethod
    def _sider_i(omraade):
        return next((s for n, _, _, s in OMRAADER if n == omraade), [])

    def _vis_faner(self, omraade, noegle):
        """Topmenuen: områdets undersider som faner (skjult ved én side)."""
        sider = self._sider_i(omraade)
        self.faner.blockSignals(True)
        if omraade != self._omraade:
            while self.faner.count():
                self.faner.removeTab(0)
            for _, tekst in sider:
                self.faner.addTab(tekst.replace("&", "&&"))
            self._omraade = omraade
        index = next((i for i, (side, _) in enumerate(sider) if side == noegle), -1)
        if index >= 0:
            self.faner.setCurrentIndex(index)
        self.faner.blockSignals(False)
        self.fane_ramme.setVisible(len(sider) > 1)

    def _fane_valgt(self, index):
        sider = self._sider_i(self._omraade)
        if 0 <= index < len(sider):
            self.vis_side(sider[index][0])

    def _vis_filtreret(self, maal, filter_):
        """Et overblikskort på dashboardet: åbn den liste, tallet er talt ud fra."""
        if maal == kontrolrum.ARBEJDSBAKKE:
            self.arbejdsbakke.vaelg(filter_)
            self.vis_side("arbejdsbakke")
        else:
            self.teamoverblik.vaelg_filter(filter_)
            self.vis_side("on_team")

    def vis_side(self, noegle):
        side = self.sider[noegle]
        omraade = OMRAADE_FOR_SIDE.get(noegle)
        self.sidebar.marker(omraade or INDSTILLINGER)
        self._vis_faner(omraade, noegle)
        if omraade:
            self._sidste_side[omraade] = noegle
        modul = adgang.modul_for_side(noegle)
        if not session.har_adgang(modul):
            self.laast_side.vis(modul)
            self.stak.setCurrentWidget(self.laast_side)
            return
        self.stak.setCurrentWidget(side)
        # Telefoner og Arkiv hentes kun, når siden åbnes (ikke hvert minut) – sparer Supabase-trafik.
        if isinstance(side, (SkabelonSide, IndstillingerSide, IndmeldingSide, MdmSide,
                             MdmArkivSide)):
            side.opdater()

    def vis_oprettet(self, sag):
        """Efter oprettelse: modulets aktive forløb med den nye sag markeret og en
        bekræftelse. Opgaver og tidslinje åbnes bevidst herfra (dobbeltklik)."""
        noegle = f"{'on' if sag.PROCES == ON else 'off'}_aktive"
        self.vis_side(noegle)
        side = self.sider[noegle]
        side.vaelg(sag.id)
        side.vis_besked(f"✓ {sag.navn} er oprettet og gemt (status: {sag.status}). "
                        "Dobbeltklik eller vælg 'Åbn forløb' for at se opgaver og tidslinje.")

    def aabn_sag(self, proces, sag_id, opgave_id=""):
        self.ctrl[proces].aabn_sag(sag_id, opgave_id)

    ### ----- log på, roller, tema -------------------------------------------

    def efter_log_paa(self):
        bruger = session.bruger() or {}
        praef = self.t.indstillinger.praeference(bruger.get("brugernavn", ""))
        anvend_tema(QApplication.instance(), praef["tema"])
        self.sidebar.opdater_ikoner()
        self.notifikationer.slaaet_til = bool(praef["windows_notifikationer"])
        self.sidebar.saet_bruger(bruger)
        self.anvend_rolle()
        self.vis_side("dashboard")
        self._saet_forbindelse(FORBINDER)
        self.opdater_alle()
        self._vis_paamindelser()
        if self.t.opdatering is not None:
            koer_i_baggrund(self.t.opdatering.rapporter)
        self._tjek_opdatering()

    ### ----- central opdatering ---------------------------------------------

    def _find_og_hent(self, bruger):
        """Baggrundstråd: findes der en ny version? En frivillig opdatering hentes
        med det samme, så den er klar, når brugeren vælger at genstarte."""
        status = self.t.opdatering.find(bruger)
        fil = None
        if status.maal and not status.tvungen and self.t.opdatering.kan_installere:
            fil = self.t.opdatering.hent(status.maal)
        return status, fil

    def _tjek_opdatering(self):
        if self.t.opdatering is None or session.bruger() is None or self._opdatering_tjekker:
            return
        self._opdatering_tjekker = True
        self._opdatering_tjekket = time.monotonic()
        koer_i_baggrund(self._find_og_hent, dict(session.bruger()),
                        naar_faerdig=self._opdatering_fundet, ved_fejl=self._opdatering_fejl)

    def _opdatering_fundet(self, resultat):
        self._opdatering_tjekker = False
        if session.bruger() is None:
            return
        self._opdatering, self._opdatering_fil = resultat
        maal = self._opdatering.maal
        self.sidebar.saet_opdatering(maal.version if maal else None)
        if self._opdatering.tvungen:
            self.vis_opdatering()
        elif maal and self._opdatering_fil and self._opdatering_meldt != maal.version:
            self._opdatering_meldt = maal.version
            self.notifikationer.vis_besked(f"IN-BASE {maal.version} er klar",
                                           "Klik på knappen i menuen for at opdatere.")

    def _opdatering_fejl(self, fejl):
        self._opdatering_tjekker = False
        if isinstance(fejl, KompatibilitetsFejl):
            QMessageBox.critical(self, "Databasen skal opdateres", str(fejl))
            self.afslut()
        elif isinstance(fejl, SessionUdloebetFejl):
            self._session_udloebet(fejl)
        else:   # ingen forbindelse o.l. – der prøves igen ved næste tjek
            log.warning("Tjek for ny version mislykkedes: %s", fejl)

    def vis_opdatering(self):
        status = self._opdatering
        if status is None or self.t.opdatering is None:
            return
        dialog = OpdateringDialog(self, self.t.opdatering, status, self._opdatering_fil)
        if dialog.exec() and dialog.installer_sti:
            if self.instans is not None:
                self.instans.frigiv()      # installeren må ikke se IN-BASE som kørende
            if udfoer(self, self.t.opdatering.installer, dialog.installer_sti) is not FEJL:
                self.afslut()
            elif self.instans is not None:
                self.instans.start()       # installeren kom ikke i gang – kør videre
        elif status.tvungen:
            self.afslut()

    def anvend_rolle(self):
        admin = session.er_admin()
        # Skabeloner må alle ændre (ikke offline); kun det kritiske er for administratorer.
        redigerbar = not self.t.lagring.offline
        for noegle in ("on_skabeloner", "off_skabeloner"):
            self.sider[noegle].saet_redigerbar(redigerbar)
        for knap in (self.on_slet, self.off_slet):
            knap.setVisible(admin)
        self.oensker.anvend_rolle(admin)
        # Et område er låst, hvis dets sider hører til et modul uden adgang
        # (fanerne fører så til LaastSide – flytningen giver ingen ny adgang).
        for noegle, tekst, _, sider in OMRAADER:
            laast = not session.har_adgang(adgang.modul_for_side(sider[0][0]))
            self.sidebar.knapper[noegle].setText(
                tekst.replace("&", "&&") + (LAAS if laast else ""))
        for side in (self.telefoner, self.telefoner_arkiv):
            side.anvend_rolle(session.har_adgang(adgang.TELEFONER))
        self.indstillinger.anvend_rolle(admin)

    def skift_tema(self, tema):
        anvend_tema(QApplication.instance(), tema)
        self.sidebar.opdater_ikoner()
        self.vis_data()                 # kun farverne skifter – intet hentes igen

    def _saet_notifikationer(self, til):
        self.notifikationer.slaaet_til = til

    def _lagring_skiftet(self):
        self.anvend_rolle()
        self.opdater_alle()

    def log_ud(self):
        """Lukker adgangen: ingen session, ingen baggrundsopdatering, ingen data på siderne."""
        log.info("Bruger %s logger ud", session.brugernavn())
        self._logger_ud = True
        self.timer.stop()
        self.t.auth.log_ud()
        session.log_ud()
        self._ryd_sider()
        self.hide()
        self._logger_ud = False
        self.log_paa()

    def _ryd_sider(self):
        self.data = {ON: ([], []), OFF: ([], [])}
        self._signatur = {}
        self._generation += 1           # et igangværende minut-tjek kasseres
        self._opdatering,self._opdatering_fil, self._opdatering_tjekket = None, None, None
        self.sidebar.saet_opdatering(None)
        for side in [self.sider[f"{p}_{n}"] for p in ("on", "off") for n in ("aktive", "arkiv")] \
                + [self.oensker, self.telefoner, self.telefoner_arkiv]:
            side.ryd()
        self.arbejdsbakke.opdater([])
        self.teamoverblik.opdater([])

    def _session_udloebet(self, fejl):
        """Sessionen er udløbet, eller adgangen er lukket: log ud på en kontrolleret måde.

        Åbne dialoger lukkes, og selve log ud sker, når den aktuelle handling er
        afsluttet (så ingen dialog fortsætter i den gamle session).
        """
        if self._logger_ud or session.bruger() is None:
            return
        self._logger_ud = True
        self.timer.stop()
        log.warning("Logger %s ud: %s", session.brugernavn(), fejl)
        QMessageBox.warning(self, "Log på igen", str(fejl))
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.reject()
        QTimer.singleShot(0, self.log_ud)

    def log_paa(self):
        """Viser log på-skærmen. Annulleres den, afsluttes programmet."""
        dialog = LoginDialog(self.t.auth)
        if not dialog.exec():
            self.afslut()
            return
        session.log_ind(dialog.bruger)
        self.efter_log_paa()
        self.timer.start()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    ### ----- baggrund og lukning --------------------------------------------

    def closeEvent(self, event):
        """Luk-knappen skjuler vinduet; programmet kører videre ved uret."""
        if self._afslutter or not self.notifikationer.tilgaengelig:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._baggrund_forklaret:
            self._baggrund_forklaret = True
            self.notifikationer.vis_besked(
                f"{APP_NAVN} kører i baggrunden",
                "Højreklik på ikonet ved uret og vælg Afslut for at lukke helt.",
            )

    def vis_fra_baggrund(self):
        if session.bruger() is None:
            return   # log på-skærmen er åben
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def afslut(self):
        self._afslutter = True
        self.notifikationer.tray.hide()
        QApplication.quit()
