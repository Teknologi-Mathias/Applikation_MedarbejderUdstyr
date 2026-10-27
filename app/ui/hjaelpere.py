"""Små fælles byggeklodser til brugerfladen (datoer, knapper, kort, lister).

Farver kommer altid fra temaet (objectName + stylesheet eller FARVER), så
temaskift virker overalt.
"""
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.stier import ASSETS_MAPPE
from app.ui.theme import FARVER

UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
UGEDAGE_KORT = ["ma", "ti", "on", "to", "fr", "lø", "sø"]
MAANEDER = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]

# Data på klikbare listerækker: (proces, sag_id, opgave_id eller "").
SAG_ROLE = Qt.ItemDataRole.UserRole


### ----- datoer --------------------------------------------------------------

def dansk_dato(dato):
    return (
        f"{UGEDAGE[dato.dayOfWeek() - 1]} den {dato.day()}. "
        f"{MAANEDER[dato.month() - 1]} {dato.year()}"
    )


def laes_dato(tekst):
    return QDate.fromString(str(tekst), "yyyy-MM-dd")


def vis_dato(tekst):
    """"2026-11-30" -> "30-11-2026" (ugyldige datoer vises som de er)."""
    dato = laes_dato(str(tekst)[:10])
    return dato.toString("dd-MM-yyyy") if dato.isValid() else str(tekst)


### ----- widgets -------------------------------------------------------------

def lav_knap(tekst, variant=None, tooltip=None):
    knap = QPushButton(tekst)
    if variant:
        knap.setProperty("variant", variant)
    knap.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        knap.setToolTip(tooltip)
    return knap


def lav_kort(skygge=True):
    kort = QFrame()
    kort.setObjectName("card")
    if skygge:
        effekt = QGraphicsDropShadowEffect(kort)
        effekt.setBlurRadius(24)
        effekt.setOffset(0, 4)
        effekt.setColor(QColor(FARVER["skygge"]))
        kort.setGraphicsEffect(effekt)
    return kort


def lav_sidehoved(titel, undertitel):
    boks = QVBoxLayout()
    boks.setSpacing(2)
    titel_label = QLabel(titel)
    titel_label.setObjectName("pageTitle")
    under_label = QLabel(undertitel)
    under_label.setObjectName("pageSub")
    under_label.setWordWrap(True)
    boks.addWidget(titel_label)
    boks.addWidget(under_label)
    return boks, under_label


def scroll_side(side: QWidget) -> QVBoxLayout:
    """Gør siden scrollbar og returnerer layoutet til indholdet."""
    ydre = QVBoxLayout(side)
    ydre.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    ydre.addWidget(scroll)
    indre = QWidget()
    indre.setObjectName("scrollInner")
    scroll.setWidget(indre)
    layout = QVBoxLayout(indre)
    layout.setContentsMargins(32, 28, 32, 28)
    layout.setSpacing(18)
    return layout


def pille_css(stil):
    """Stylesheet til en pille-label; stil er en dict med "bg" og "tekst"."""
    return (
        f"background: {stil['bg']}; color: {stil['tekst']}; border-radius: 10px;"
        "font-weight: 700; font-size: 12px; padding: 5px 10px;"
    )


def lav_pille(tekst, stil, bredde=None):
    label = QLabel(tekst)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if bredde:
        label.setFixedWidth(bredde)
    label.setStyleSheet(pille_css(stil))
    return label


def lav_raekke(titel, undertitel, badge, stil):
    """En række i dashboardets lister: farvet badge + titel og undertitel."""
    widget = QWidget()
    widget.setToolTip(f"{titel}\n{undertitel}")      # hele teksten, også i smalle kort
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 9, 4, 9)
    layout.setSpacing(12)

    tekst_layout = QVBoxLayout()
    tekst_layout.setSpacing(1)
    titel_label = QLabel(titel)
    titel_label.setObjectName("raekkeTitel")
    under_label = QLabel(undertitel)
    under_label.setObjectName("raekkeUnder")
    tekst_layout.addWidget(titel_label)
    tekst_layout.addWidget(under_label)

    layout.addWidget(lav_pille(badge, stil, bredde=96))
    layout.addLayout(tekst_layout, 1)
    return widget


def lav_liste_kort(titel, undertitel, klikbar=True, ikon=None):
    """Kort med titel, antal-badge og en liste. Returnerer (kort, liste, antal_label).

    ikon: valgfri QPixmap foran titlen (app/ui/ikoner.py)."""
    kort = lav_kort()
    layout = QVBoxLayout(kort)
    layout.setContentsMargins(20, 18, 20, 12)
    layout.setSpacing(6)

    top = QHBoxLayout()
    if ikon is not None:
        ikon_label = QLabel()
        ikon_label.setPixmap(ikon)
        kort.ikon_label = ikon_label
        top.addWidget(ikon_label)
    titel_label = QLabel(titel)
    titel_label.setObjectName("cardTitle")
    titel_label.setWordWrap(True)          # kortene må gerne blive smalle
    antal_label = QLabel("0")
    antal_label.setObjectName("antalBadge")
    antal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    antal_label.setMinimumWidth(28)
    top.addWidget(titel_label)
    top.addStretch()
    top.addWidget(antal_label)

    under_label = QLabel(undertitel)
    under_label.setObjectName("cardSub")
    under_label.setWordWrap(True)

    liste = QListWidget()
    liste.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    liste.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    liste.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    liste.setMinimumHeight(300)
    if klikbar:
        liste.setProperty("klikbar", True)
        liste.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    layout.addLayout(top)
    layout.addWidget(under_label)
    layout.addWidget(liste, 1)
    return kort, liste, antal_label


def fyld_liste(liste, raekker, tom_tekst):
    """raekker: [(widget, data)] – data lægges på SAG_ROLE."""
    liste.clear()
    if not raekker:
        item = QListWidgetItem()
        label = QLabel(tom_tekst)
        label.setObjectName("tomTekst")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setSizeHint(label.sizeHint())
        liste.addItem(item)
        liste.setItemWidget(item, label)
        return
    for widget, data in raekker:
        item = QListWidgetItem()
        item.setData(SAG_ROLE, data)
        item.setSizeHint(widget.sizeHint())
        liste.addItem(item)
        liste.setItemWidget(item, widget)


def lav_app_ikon() -> QIcon:
    """IN-BASE-logoet som ikon (vinduer, proceslinje, ikon ved uret, notifikationer).

    IN-BASE.ico indeholder færdige størrelser fra 16 til 256 px (lavet med
    tools/lav_ikon.py ud fra IN-BASE-ikon.svg).
    """
    ico = ASSETS_MAPPE / "IN-BASE.ico"
    return QIcon(str(ico if ico.exists() else ASSETS_MAPPE / "IN-BASE-ikon.svg"))


def lav_logo(stoerrelse: int) -> QLabel:
    """Logoet som et billede i den givne størrelse (px)."""
    label = QLabel()
    label.setPixmap(lav_app_ikon().pixmap(stoerrelse, stoerrelse))
    label.setFixedSize(stoerrelse, stoerrelse)
    return label
