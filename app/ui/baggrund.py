"""Netværkskald uden at fryse brugerfladen.

    koer_i_baggrund(funktion, *args, naar_faerdig=vis, ved_fejl=fejl)

funktion kører i Qt's trådpulje; naar_faerdig(resultat) eller ved_fejl(fejl)
kaldes bagefter på UI-tråden (via et signal), så de frit kan opdatere widgets.
Funktionen må ikke røre widgets – kun services. Uden ved_fejl logges fejlen.

Bruges af hovedvinduets minut-tjek og af den centrale opdatering.
"""
import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)

# Opgaver, hvis signal endnu ikke er leveret (ellers kan Python rydde dem op for tidligt).
_igangvaerende: set = set()


class _Signaler(QObject):
    faerdig = Signal(object)
    fejl = Signal(object)


class _Opgave(QRunnable):
    def __init__(self, funktion, args, kwargs):
        super().__init__()
        self.funktion, self.args, self.kwargs = funktion, args, kwargs
        self.signaler = _Signaler()

    def run(self):
        try:
            resultat = self.funktion(*self.args, **self.kwargs)
        except Exception as fejl:       # leveres til UI-tråden – intet slugges tavst
            self.signaler.fejl.emit(fejl)
        else:
            self.signaler.faerdig.emit(resultat)


def koer_i_baggrund(funktion: Callable, *args, naar_faerdig: Optional[Callable] = None,
                    ved_fejl: Optional[Callable] = None, **kwargs) -> None:
    opgave = _Opgave(funktion, args, kwargs)
    opgave.setAutoDelete(False)
    _igangvaerende.add(opgave)

    def faerdig(resultat):
        _igangvaerende.discard(opgave)
        if naar_faerdig:
            naar_faerdig(resultat)

    def fejl(fejl_):
        _igangvaerende.discard(opgave)
        if ved_fejl:
            ved_fejl(fejl_)
        else:
            log.error("Baggrundsopgave %s fejlede", getattr(funktion, "__name__", funktion),
                      exc_info=fejl_)

    opgave.signaler.faerdig.connect(faerdig)
    opgave.signaler.fejl.connect(fejl)
    QThreadPool.globalInstance().start(opgave)
