"""Afhængigheder mellem opgaver: entydige nøgler, kendte forudsætninger, ingen cirkler.

Samme regler gælder for skabeloner (dicts) og sager (Opgave-objekter), så en
arbejdsgang ikke kan designes eller gemmes, så en opgave aldrig kan udføres.
En undtaget opgave tæller som afsluttet, så et fravalgt behov aldrig blokerer.
"""


def _post(post) -> tuple:
    """Opgave eller skabelon-dict -> (nøgle, navn, afhænger af)."""
    if isinstance(post, dict):
        return (str(post.get("noegle") or "").strip(), post.get("navn", ""),
                [str(n).strip() for n in post.get("afhaenger_af") or () if str(n).strip()])
    return post.noegle, post.navn, list(post.afhaenger_af)


def find_fejl(poster) -> list[str]:
    """Beskeder om dublerede nøgler, ukendte forudsætninger og cirkulære afhængigheder."""
    poster = [_post(p) for p in poster]
    fejl = []
    navne, kanter = {}, {}
    for noegle, navn, afhaenger in poster:
        if noegle in navne:
            fejl.append(f"Nøglen '{noegle}' bruges af både '{navne[noegle]}' og '{navn}'.")
        elif noegle:
            navne[noegle] = navn
            kanter[noegle] = afhaenger
    for noegle, navn, afhaenger in poster:
        for n in afhaenger:
            if n not in navne:
                fejl.append(f"'{navn}' afhænger af en ukendt opgave ('{n}').")
            elif n == noegle:
                fejl.append(f"'{navn}' kan ikke afhænge af sig selv.")
    cirkel = _find_cirkel(kanter)
    if cirkel:
        fejl.append("Cirkulær afhængighed: " + " → ".join(navne[n] for n in cirkel) + ".")
    return fejl


def _find_cirkel(kanter: dict) -> list:
    """Nøglerne i en cirkel (første gentaget til sidst), eller [] hvis ingen."""
    HVID, GRAA, SORT = 0, 1, 2
    farve = dict.fromkeys(kanter, HVID)
    sti = []

    def besoeg(noegle):
        farve[noegle] = GRAA
        sti.append(noegle)
        for naeste in kanter.get(noegle, ()):
            if naeste == noegle or naeste not in farve:
                continue        # selvreference og ukendte nøgler meldes særskilt
            if farve[naeste] == GRAA:
                return sti[sti.index(naeste):] + [naeste]
            if farve[naeste] == HVID:
                fundet = besoeg(naeste)
                if fundet:
                    return fundet
        sti.pop()
        farve[noegle] = SORT
        return []

    for noegle in kanter:
        if farve[noegle] == HVID:
            fundet = besoeg(noegle)
            if fundet:
                return fundet
    return []
