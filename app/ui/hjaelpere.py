"""Små fælles byggeklodser til brugerfladen (datoer, knapper, kort)."""
from PySide6.QtCore import QDate, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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


def vis_dato(tekst):
    """"2026-11-30" -> "30-11-2026" (ugyldige datoer vises som de er)."""
    dato = laes_dato(tekst)
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
        effekt.setColor(QColor(0, 0, 0, 110))
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
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 9, 4, 9)
    layout.setSpacing(12)

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

    layout.addWidget(lav_pille(badge, stil, bredde=86))
    layout.addLayout(tekst_layout, 1)
    return widget


def lav_app_ikon():
    """Programmets ikon (vindue og proceslinje), tegnet i kode."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(FARVER["primary"]))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    font = QFont()
    font.setPixelSize(36)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(2, 2, 60, 60), Qt.AlignmentFlag.AlignCenter, "M")
    p.end()
    return QIcon(pixmap)
