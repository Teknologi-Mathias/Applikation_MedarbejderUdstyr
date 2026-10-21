"""Skabeloner til afviklingssager.

Skabelonerne ligger i Data/skabeloner.json, så I selv kan tilpasse opgaver,
ansvarlige og frister uden at ændre koden. Findes filen ikke, oprettes den med
standardskabelonerne nedenfor.

Format:
    [
        {
            "navn": "Standard",
            "opgaver": [
                {"navn": "Modtag telefon og SIM-kort", "ansvarlig": "IT",
                 "frist_dage": 7, "obligatorisk": true},
                ...
            ]
        }
    ]

"frist_dage" er antal dage efter fratrædelsesdatoen (0 = samme dag,
negativ = før).
"""
from app.data_manager import DataFejl, gem_json, hent_json
from app.medarbejder import frist_fra_dage
from app.opgave import Opgave
from app.stier import SKABELON_FIL

STANDARD_SKABELONER = [
    {
        "navn": "Standard",
        "opgaver": [
            {"navn": "Luk systemadgange", "ansvarlig": "IT",
             "frist_dage": 0, "obligatorisk": True},
            {"navn": "Modtag og spær tankkort", "ansvarlig": "Administration",
             "frist_dage": 0, "obligatorisk": True},
            {"navn": "Modtag telefon og SIM-kort", "ansvarlig": "IT",
             "frist_dage": 7, "obligatorisk": True},
            {"navn": "Modtag tøj", "ansvarlig": "Administration",
             "frist_dage": 14, "obligatorisk": True},
            {"navn": "Afslut og dokumentér afviklingen", "ansvarlig": "Ansvarlig leder",
             "frist_dage": 21, "obligatorisk": True},
        ],
    },
    {
        "navn": "Tom sag (tilføj opgaver selv)",
        "opgaver": [],
    },
]


def hent_skabeloner():
    """Returnerer listen af skabeloner. Kaster DataFejl ved ugyldig fil."""
    if not SKABELON_FIL.exists():
        gem_json(STANDARD_SKABELONER, SKABELON_FIL)
        return STANDARD_SKABELONER

    skabeloner = hent_json(SKABELON_FIL)
    for skabelon in skabeloner:
        if (
            not isinstance(skabelon, dict)
            or not skabelon.get("navn")
            or not isinstance(skabelon.get("opgaver", []), list)
        ):
            raise DataFejl(
                f"{SKABELON_FIL.name} har en ugyldig skabelon: {skabelon!r}.\n\n"
                "Hver skabelon skal have et \"navn\" og en liste \"opgaver\". "
                "Slet filen for at få standardskabelonerne tilbage."
            )
    return skabeloner or STANDARD_SKABELONER


def opret_opgaver(skabelon, fratraedelsesdato):
    """Laver nye opgaver ud fra en skabelon, med frister regnet fra fratrædelsen."""
    opgaver = []
    for post in skabelon.get("opgaver", []):
        if not isinstance(post, dict) or not post.get("navn"):
            continue
        opgaver.append(Opgave(
            post["navn"],
            post.get("ansvarlig", ""),
            frist_fra_dage(fratraedelsesdato, post.get("frist_dage", 0)),
            obligatorisk=post.get("obligatorisk", True),
        ))
    return opgaver


def kendte_ansvarlige(skabeloner, medarbejdere=()):
    """Alle ansvarlige nævnt i skabeloner og eksisterende opgaver (til forslag)."""
    navne = {
        str(post.get("ansvarlig", "")).strip()
        for skabelon in skabeloner
        for post in skabelon.get("opgaver", [])
        if isinstance(post, dict)
    }
    navne.update(o.ansvarlig for m in medarbejdere for o in m.opgaver)
    return sorted(n for n in navne if n)
