"""Opsætning af logning til fil (Lokal/Logs/in-base.log) og konsol.

Brug altid `log = logging.getLogger(__name__)` i modulerne – aldrig print()
eller tavst slugte undtagelser.
"""
import logging
from logging.handlers import RotatingFileHandler

from app.infrastructure.stier import LOG_MAPPE

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def opsaet_logning(niveau: int = logging.INFO) -> None:
    rod = logging.getLogger()
    if any(getattr(h, "_inbase", False) for h in rod.handlers):
        return  # allerede sat op
    rod.setLevel(niveau)
    try:
        LOG_MAPPE.mkdir(parents=True, exist_ok=True)
        fil = RotatingFileHandler(
            LOG_MAPPE / "in-base.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        fil.setFormatter(logging.Formatter(_FORMAT))
        fil._inbase = True
        rod.addHandler(fil)
    except OSError as fejl:  # programmet skal kunne køre uden logfil
        logging.basicConfig(level=niveau, format=_FORMAT)
        logging.getLogger(__name__).warning("Logfil kunne ikke oprettes: %s", fejl)
