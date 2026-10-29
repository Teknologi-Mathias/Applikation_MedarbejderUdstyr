"""Enkle streg-ikoner til menu, kort og køer – ét fælles sæt, farvet efter temaet.

Ikonerne understøtter teksten; de erstatter den aldrig. Alle er tegnet på et
24×24-gitter med samme stregtykkelse, så de ser ens ud. Farven sættes, når
ikonet laves (FARVER fra temaet), så ikoner skal laves igen ved temaskift.

Nyt ikon: tilføj SVG-elementer under et navn i _FORMER.
"""
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap

_FORMER = {
    "overblik": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" '
                'height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/>'
                '<rect x="3" y="16" width="7" height="5" rx="1"/>',
    "onboarding": '<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6 7-6s7 2 7 6"/>'
                  '<path d="M19 8v6M16 11h6"/>',
    "offboarding": '<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6 7-6s7 2 7 6"/>'
                   '<path d="M16 11h6"/>',
    "telefon": '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    "oensker": '<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 '
               '0 12 2z"/>',
    "indstillinger": '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7"/>'
                     '<g stroke-width="3"><path d="M19 12h3M2 12h3M12 19v3M12 2v3"/>'
                     '<path d="M16.9 16.9l2.2 2.2M4.9 4.9l2.2 2.2M16.9 7.1l2.2-2.2M4.9 19.1l2.2-2.2"/>'
                     '</g>',
    "log_ud": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 '
              '12H9"/>',
    "kontrakt": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
                '<path d="M14 2v6h6M8 13h8M8 17h6"/>',
    "udstyr": '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
    "oplaering": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"/>',
    "firmabil": '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><path d="M3 12h18M9 17h6"/>'
                '<circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>',
    "forsinket": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "kalender": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "person": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "risiko": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "afventer": '<path d="M6 2h12M6 22h12"/><path d="M7 2v3l5 7 5-7V2M7 22v-3l5-7 5 7v3"/>',
    "retur": '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    "afslut": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "haster": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
}
NAVNE = tuple(_FORMER)


def svg(navn: str, farve: str, px: int = 48) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'width="{px}" height="{px}" '
            f'fill="none" stroke="{farve}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{_FORMER[navn]}</svg>')


def pixmap(navn: str, farve: str, stoerrelse: int = 18) -> QPixmap:
    """Skarpt også på skærme med skalering (tegnes i skærmens opløsning)."""
    skala = QGuiApplication.instance().devicePixelRatio() if QGuiApplication.instance() else 1
    pix = QPixmap()
    pix.loadFromData(svg(navn, farve, round(stoerrelse * skala)).encode("utf-8"), "SVG")
    pix.setDevicePixelRatio(skala)
    return pix


def ikon(navn: str, farve: str, valgt_farve: str | None = None, stoerrelse: int = 18) -> QIcon:
    """QIcon med egen farve til valgt tilstand (fx hvid på den markerede menuknap)."""
    resultat = QIcon()
    resultat.addPixmap(pixmap(navn, farve, stoerrelse), QIcon.Mode.Normal, QIcon.State.Off)
    resultat.addPixmap(pixmap(navn, valgt_farve or farve, stoerrelse),
                       QIcon.Mode.Normal, QIcon.State.On)
    return resultat
