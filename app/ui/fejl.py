"""Ensartet fejlhåndtering, når brugerfladen kalder en service.

    resultat = udfoer(self, self.t.offboarding.arkiver, sag)

- ValideringsFejl     -> informationsboks med regelbeskeden
- KonfliktFejl        -> advarsel (data er ændret af en anden); kald opdater
- OfflineFejl         -> advarsel om manglende forbindelse/offline-tilstand
- SessionUdloebetFejl -> overlades til hovedvinduet, som logger brugeren ud
                         (saet_session_haandtering)
- DataFejl/OSError    -> fejlboks + logning (intet slugges tavst)
Returnerer funktionens resultat, eller markøren FEJL ved fejl:

    if resultat is FEJL: return
"""
import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.repositories.fejl import (
    DataFejl,
    KonfliktFejl,
    OfflineFejl,
    SessionUdloebetFejl,
    ValideringsFejl,
)

log = logging.getLogger(__name__)

# Sættes af hovedvinduet: kaldes med fejlen, når sessionen er udløbet eller
# adgangen lukket – så alle sider håndterer det ens (log ud, vis log på).
_session_haandtering: Optional[Callable[[SessionUdloebetFejl], None]] = None


def saet_session_haandtering(funktion: Optional[Callable[[SessionUdloebetFejl], None]]) -> None:
    global _session_haandtering
    _session_haandtering = funktion


class Fejl:
    """Markør for en mislykket handling (adskiller sig fra resultatet None)."""


FEJL = Fejl()


def _vent(funktion, args, kwargs):
    """Ventecursor, mens kaldet kører (netværk kan tage tid) – fjernes før en fejlboks."""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        return funktion(*args, **kwargs)
    finally:
        QApplication.restoreOverrideCursor()


def udfoer(parent, funktion, *args, efter_konflikt=None, **kwargs):
    try:
        return _vent(funktion, args, kwargs)
    except (ValideringsFejl, DataFejl, OSError) as fejl:
        vis_fejl(parent, fejl, getattr(funktion, "__name__", funktion), efter_konflikt)
    return FEJL


def vis_fejl(parent, fejl: Exception, hvad="handlingen", efter_konflikt=None) -> None:
    """Viser en fejl som udfoer() – også for fejl fra en baggrundsopgave
    (app/ui/baggrund.py, ved_fejl). Ukendte fejl logges og vises som datafejl."""
    if isinstance(fejl, ValideringsFejl):
        QMessageBox.information(parent, "Kan ikke gennemføres", str(fejl))
    elif isinstance(fejl, KonfliktFejl):
        QMessageBox.warning(parent, "Ændret af en anden", str(fejl))
        if efter_konflikt:
            efter_konflikt()
    elif isinstance(fejl, OfflineFejl):
        QMessageBox.warning(parent, "Ingen forbindelse", str(fejl))
    elif isinstance(fejl, SessionUdloebetFejl):
        log.warning("Session udløbet/adgang lukket under %s", hvad)
        if _session_haandtering:
            _session_haandtering(fejl)
        else:
            QMessageBox.warning(parent, "Log på igen", str(fejl))
    else:
        log.error("Fejl under %s", hvad, exc_info=fejl)
        QMessageBox.critical(parent, "Datafejl", f"Handlingen mislykkedes:\n{fejl}")
