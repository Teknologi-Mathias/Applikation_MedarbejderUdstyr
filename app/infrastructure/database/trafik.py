"""Måling af datatrafikken fra Supabase (egress er det, Free-planen begrænser).

Tælleren lægges på PostgREST-forbindelsen (connection.py) og summerer de
modtagne bytes pr. endpoint. En gang i timen skrives en opsummering til
logfilen, fx "Datatrafik sidste time: rpc/inbase_case_signature 60 kald 31 KB".
"""
import logging
import threading
import time
from collections import defaultdict

log = logging.getLogger(__name__)

OPSUMMERING = 3600      # sekunder mellem opsummeringerne i logfilen


def endpoint(sti: str) -> str:
    """/rest/v1/rpc/inbase_tick -> rpc/inbase_tick; /rest/v1/lifecycle_cases -> lifecycle_cases."""
    dele = [d for d in sti.split("/") if d]
    if dele[:2] == ["rest", "v1"]:
        dele = dele[2:]
    return "/".join(dele[:2]) if dele[:1] == ["rpc"] else (dele[0] if dele else "/")


class Trafiktaeller:
    def __init__(self, interval: float = OPSUMMERING, ur=time.monotonic):
        self.interval = interval
        self._ur = ur
        self._laas = threading.Lock()
        self._start = ur()
        self._kald: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # endpoint -> [kald, bytes]

    def registrer(self, sti: str, antal_bytes: int) -> None:
        with self._laas:
            post = self._kald[endpoint(sti)]
            post[0] += 1
            post[1] += antal_bytes
            if self._ur() - self._start < self.interval:
                return
            tekst = self._opsummer()
        log.info("Datatrafik sidste time: %s", tekst)

    def _opsummer(self) -> str:
        poster = sorted(self._kald.items(), key=lambda p: p[1][1], reverse=True)
        i_alt = sum(b for _, b in self._kald.values())
        tekst = ", ".join(f"{navn} {k} kald {b / 1024:.0f} KB" for navn, (k, b) in poster)
        self._kald.clear()
        self._start = self._ur()
        return f"{i_alt / 1024:.0f} KB i alt – {tekst}"

    def svar_modtaget(self, svar) -> None:
        """httpx-hook (event_hooks["response"]): læser svaret og tæller de hentede bytes."""
        try:
            svar.read()
            self.registrer(svar.request.url.path, svar.num_bytes_downloaded)
        except Exception:   # målingen må aldrig stoppe et kald
            log.debug("Datatrafik kunne ikke måles", exc_info=True)


taeller = Trafiktaeller()
