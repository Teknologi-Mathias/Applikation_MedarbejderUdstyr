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

from PySide6.QtWidgets import QMessageBox

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


def udfoer(parent, funktion, *args, efter_konflikt=None, **kwargs):
    try:
        return funktion(*args, **kwargs)
    except ValideringsFejl as fejl:
        QMessageBox.information(parent, "Kan ikke gennemføres", str(fejl))
    except KonfliktFejl as fejl:
        QMessageBox.warning(parent, "Ændret af en anden", str(fejl))
        if efter_konflikt:
            efter_konflikt()
    except OfflineFejl as fejl:
        QMessageBox.warning(parent, "Ingen forbindelse", str(fejl))
    except SessionUdloebetFejl as fejl:
        log.warning("Session udløbet/adgang lukket under %s",
                    getattr(funktion, "__name__", funktion))
        if _session_haandtering:
            _session_haandtering(fejl)
        else:
            QMessageBox.warning(parent, "Log på igen", str(fejl))
    except (DataFejl, OSError) as fejl:
        log.exception("Datafejl under %s", getattr(funktion, "__name__", funktion))
        QMessageBox.critical(parent, "Datafejl", f"Handlingen mislykkedes:\n{fejl}")
    return FEJL
