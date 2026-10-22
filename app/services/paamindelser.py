"""Påmindelser som Windows-notifikationer, ud fra påmindelsesskabelonerne.

Adskilt fra Action Center: slår brugeren Windows-notifikationer fra, vises
de samme ting stadig i Action Center.

Gentagelse styres pr. skabelon med "gentag_dage" (0 = kun én gang pr. sag/
opgave, 1 = højst én gang om dagen osv.). Hvornår en påmindelse sidst blev
vist, gemmes i Lokal/notifikationslog.json, så en genstart ikke giver
gentagelser.
"""
from dataclasses import dataclass
from datetime import date

from app.domain import skabelon as sk
from app.domain.offboarding import Medarbejder
from app.domain.opgave import laes_iso_dato
from app.domain.sag import Sag
from app.repositories.json.opsaetning_repository import JsonLokalFil


@dataclass
class Paamindelse:
    titel: str
    tekst: str
    sag_id: str
    modul: str


def _regel_fund(regel: str, dage: int, sag: Sag, i_dag: date):
    """Giver (nøgle, værdier) for hver ting i sagen, som reglen rammer."""
    if regel in ("opgave_forsinket", "frist_i_dag"):
        for o in sag.aabne_opgaver():
            over = o.dage_over_frist(i_dag)
            if over is None:
                continue
            if (regel == "opgave_forsinket" and over > 0) or (regel == "frist_i_dag" and over == 0):
                yield o.id, {"opgave": o.navn, "ansvarlig": o.ansvarlig or "ingen angivet",
                             "frist": o.frist, "dage": str(over)}

    elif regel == "sag_stillestaaende":
        tid = sag.sidste_aktivitet()
        if tid is not None and (i_dag - tid.date()).days >= dage:
            yield sag.id, {"dage": str((i_dag - tid.date()).days)}

    elif isinstance(sag, Medarbejder):
        if regel == "fratraedelse_naermer_sig":
            fratraedelse = laes_iso_dato(sag.fratraedelsesdato)
            if fratraedelse is not None and (fratraedelse - i_dag).days == dage:
                yield sag.id, {"dage": str(dage), "frist": sag.fratraedelsesdato}
        elif regel == "rykker_ikke_sendt":
            for r in sag.usendte_rykkere():
                siden = r.dage_siden("oprettet", i_dag)
                if siden is not None and siden >= dage:
                    yield r.id, {"dage": str(siden), "frist": r.frist}
        elif regel == "intet_svar_efter_rykker":
            sendte = [r for r in sag.rykkere if r.sendt]
            if sendte and sag.manglende_udstyr() and not sag.usendte_rykkere():
                seneste = max(sendte, key=lambda r: r.sendt)
                siden = seneste.dage_siden("sendt", i_dag)
                if siden is not None and siden >= dage:
                    yield seneste.id, {"dage": str(siden), "frist": seneste.frist}


def find_paamindelser(skabeloner: list[dict], sager: list[Sag], i_dag: date) -> list:
    """[(skabelon, nøgle, værdier)] for alle aktive sager."""
    resultat = []
    for skabelon in skabeloner:
        regel, dage = skabelon.get("regel"), int(skabelon.get("dage") or 0)
        for sag in sager:
            if sag.arkiveret or sag.er_afsluttet():
                continue
            basis = {"navn": sag.navn}
            if isinstance(sag, Medarbejder):
                basis["manglende_udstyr"] = ", ".join(sag.manglende_udstyr()) or "intet"
            for noegle, ekstra in _regel_fund(regel, dage, sag, i_dag):
                resultat.append((skabelon, f"{skabelon['id']}:{noegle}",
                                 {**basis, **ekstra, "_sag_id": sag.id, "_modul": sag.PROCES}))
    return resultat


class PaamindelsesService:
    def __init__(self, log_fil: JsonLokalFil):
        self.log = log_fil

    def skal_vises(self, noegle: str, gentag_dage: int, i_dag: date, log: dict) -> bool:
        sidst = laes_iso_dato(log.get(noegle, ""))
        if sidst is None:
            return True
        if gentag_dage <= 0:
            return False
        return (i_dag - sidst).days >= gentag_dage

    def nye_paamindelser(self, skabeloner, sager, i_dag: date) -> list[Paamindelse]:
        """Påmindelser der skal vises nu. Registrerer dem som vist.

        Rammer en skabelon mere end 3 ting på én gang, samles de i én besked.
        """
        log = self.log.hent()
        grupper: dict = {}
        for skabelon, noegle, vaerdier in find_paamindelser(skabeloner, sager, i_dag):
            if not self.skal_vises(noegle, int(skabelon.get("gentag_dage", 1)), i_dag, log):
                continue
            log[noegle] = i_dag.isoformat()
            grupper.setdefault(skabelon["id"], (skabelon, []))[1].append(vaerdier)
        self.log.gem(log)

        resultat = []
        for skabelon, alle in grupper.values():
            # Manglende værdier vises som "–" i stedet for at blokere påmindelsen.
            vaerdier = {k: "–" for k in sk.PAAMINDELSE_VARIABLER} | alle[0]
            titel, _ = sk.flet(skabelon["titel"], vaerdier, sk.PAAMINDELSE_VARIABLER)
            tekst, _ = sk.flet(skabelon["tekst"], vaerdier, sk.PAAMINDELSE_VARIABLER)
            if len(alle) > 3:
                titel = f"{skabelon['navn']}: {len(alle)} sager"
                tekst = ", ".join(v["navn"] for v in alle[:5]) + (" m.fl." if len(alle) > 5 else "")
            elif len(alle) > 1:
                tekst += f"\n(+ {len(alle) - 1} mere)"
            resultat.append(Paamindelse(titel, tekst, alle[0]["_sag_id"], alle[0]["_modul"]))
        return resultat
