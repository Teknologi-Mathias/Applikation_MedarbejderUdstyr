"""Genbrugelig Action Center-liste (dashboard, arbejdskøer og modulernes oversigt).

Klik åbner sagen direkte på den relevante opgave. Højreklik giver hurtige
handlinger: markér opgave udført, ændr frist, tildel ansvarlig og vis historik
(og arkivér, for lister med sager, der er klar til afslutning).
Handlingerne udføres af controlleren (via signalet handling) – ikke her.
"""
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMenu

from app.services.action_center import MODUL_NAVN
from app.ui.hjaelpere import SAG_ROLE, fyld_liste, lav_liste_kort, lav_raekke, vis_dato
from app.ui.theme import ALARM_STIL, OPGAVE_STIL

AABN = "aabn"
UDFOERT = "udfoert"
FRIST = "frist"
ANSVARLIG = "ansvarlig"
HISTORIK = "historik"
I_GANG = "i_gang"
AFVENTER = "afventer"
ARKIVER = "arkiver"


class ActionListe(QObject):
    """Ejer et listekort. Signaler: (proces, sag_id, opgave_id)."""
    aabn_sag = Signal(str, str, str)
    handling = Signal(str, str, str, str)      # (handling, proces, sag_id, opgave_id)

    def __init__(self, titel, undertitel, vis_modul=True, parent=None, ikon=None,
                 kan_arkivere=False):
        super().__init__(parent)
        self.vis_modul = vis_modul
        self.kan_arkivere = kan_arkivere
        self.kort, self.liste, self.antal = lav_liste_kort(titel, undertitel, ikon=ikon)
        self.liste.itemClicked.connect(self._klikket)
        self.liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu)

    def _data(self, item):
        data = item.data(SAG_ROLE) if item else None
        return tuple(data) if data else None

    def _klikket(self, item):
        data = self._data(item)
        if data:
            self.aabn_sag.emit(*data)

    def _menu(self, pos):
        data = self._data(self.liste.itemAt(pos))
        if not data:
            return
        proces, sag_id, opgave_id = data
        menu = QMenu(self.liste)
        menu.addAction("Åbn sag", lambda: self.aabn_sag.emit(proces, sag_id, opgave_id))
        if opgave_id:
            menu.addSeparator()
            for navn, tekst in ((UDFOERT, "Markér opgaven som udført"),
                                (FRIST, "Ændr frist…"),
                                (ANSVARLIG, "Tildel ansvarlig…")):
                menu.addAction(tekst, lambda n=navn: self.handling.emit(n, proces, sag_id, opgave_id))
        else:
            if self.kan_arkivere:
                menu.addAction("Kontrollér og arkivér…",
                               lambda: self.handling.emit(ARKIVER, proces, sag_id, ""))
            menu.addAction("Tildel ansvarlig for sagen…",
                           lambda: self.handling.emit(ANSVARLIG, proces, sag_id, ""))
        menu.addSeparator()
        menu.addAction("Vis historik", lambda: self.handling.emit(HISTORIK, proces, sag_id, ""))
        menu.exec(self.liste.viewport().mapToGlobal(pos))

    def vis_alarmer(self, alarmer, tom_tekst="Intet kræver handling lige nu."):
        raekker = []
        for a in alarmer:
            under = (f"{MODUL_NAVN.get(a.modul, a.modul)} · " if self.vis_modul else "") + a.undertitel
            raekker.append((lav_raekke(a.titel, under, a.badge, ALARM_STIL[a.niveau]),
                            (a.modul, a.sag_id, a.opgave_id or "")))
        fyld_liste(self.liste, raekker, tom_tekst)
        self.antal.setText(str(len(alarmer)))

    def vis_opgaver(self, par, tom_tekst="Ingen opgaver har frist i dag."):
        """par: [(sag, opgave)] – fx dagsoversigten."""
        raekker = []
        for sag, o in par:
            modul = f"{MODUL_NAVN.get(sag.PROCES, '')} · " if self.vis_modul else ""
            raekker.append((
                lav_raekke(o.navn, f"{modul}{sag.navn} · Ansvarlig: "
                           f"{o.ansvarlig or 'ingen angivet'} · Frist {vis_dato(o.frist)}",
                           o.status, OPGAVE_STIL[o.status]),
                (sag.PROCES, sag.id, o.id),
            ))
        fyld_liste(self.liste, raekker, tom_tekst)
        self.antal.setText(str(len(par)))
