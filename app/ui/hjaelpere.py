"""Små fælles byggeklodser til brugerfladen (datoer, knapper, kort)."""
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import FARVER

UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
UGEDAGE_KORT = ["ma", "ti", "on", "to", "fr", "lø", "sø"]
MAANEDER = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


### ----- datoer --------------------------------------------------------------

def dansk_dato(dato):
    return (
        f"{UGEDAGE[dato.dayOfWeek() - 1]} den {dato.day()}. "
        f"{MAANEDER[dato.month() - 1]} {dato.year()}"
    )


def laes_dato(tekst):
    return QDate.fromString(str(tekst), "yyyy-MM-dd")


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
        effekt.setColor(QColor(15, 23, 42, 22))
        kort.setGraphicsEffect(effekt)
    return kort


def lav_sidehoved(titel, undertitel):
    boks = QVBoxLayout()
    boks.setSpacing(2)
    titel_label = QLabel(titel)
    titel_label.setObjectName("pageTitle")
    under_label = QLabel(undertitel)
    under_label.setObjectName("pageSub")
    boks.addWidget(titel_label)
    boks.addWidget(under_label)
    return boks, under_label


def lav_raekke(titel, undertitel, badge, badge_bg, badge_tekst):
    """En række i dashboardets lister: farvet badge + titel og undertitel."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 9, 4, 9)
    layout.setSpacing(12)

    badge_label = QLabel(badge)
    badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge_label.setFixedWidth(78)
    badge_label.setStyleSheet(
        f"background: {badge_bg}; color: {badge_tekst}; border-radius: 10px;"
        "font-weight: 700; font-size: 12px; padding: 6px 0;"
    )

    tekst_layout = QVBoxLayout()
    tekst_layout.setSpacing(1)
    titel_label = QLabel(titel)
    titel_label.setStyleSheet("font-weight: 600; background: transparent;")
    under_label = QLabel(undertitel)
    under_label.setStyleSheet(
        f"color: {FARVER['muted']}; font-size: 12px; background: transparent;"
    )
    tekst_layout.addWidget(titel_label)
    tekst_layout.addWidget(under_label)

    layout.addWidget(badge_label)
    layout.addLayout(tekst_layout, 1)
    return widget
