"""Ensartet fejlhåndtering, når brugerfladen kalder en service.

    resultat = udfoer(self, self.t.offboarding.arkiver, sag)

- ValideringsFejl  -> informationsboks med regelbeskeden
- KonfliktFejl     -> advarsel (data er ændret af en anden); kald opdater
- OfflineFejl      -> advarsel om manglende forbindelse/offline-tilstand
- DataFejl/OSError -> fejlboks + logning (intet slugges tavst)
Returnerer funktionens resultat, eller markøren FEJL ved fejl:

    if resultat is FEJL: return
"""
import logging

from PySide6.QtWidgets import QMessageBox

from app.repositories.fejl import DataFejl, KonfliktFejl, OfflineFejl, ValideringsFejl

log = logging.getLogger(__name__)


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
    except (DataFejl, OSError) as fejl:
        log.exception("Datafejl under %s", getattr(funktion, "__name__", funktion))
        QMessageBox.critical(parent, "Datafejl", f"Handlingen mislykkedes:\n{fejl}")
    return FEJL
