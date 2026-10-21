"""Farver, stylesheet og palette for hele programmet."""
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from app.medarbejder import Medarbejder
from app.stier import ASSETS_MAPPE

CHEVRON = (ASSETS_MAPPE / "chevron.svg").as_posix()

FARVER = {
    "bg": "#F4F6FA",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "text": "#0F172A",
    "muted": "#64748B",
    "primary": "#4F46E5",
    "primary_hover": "#4338CA",
    "primary_soft": "#EEF2FF",
    "sidebar": "#0F172A",
    "roed": "#EF4444",
    "gul": "#F59E0B",
    "groen": "#10B981",
}

# Farver pr. status: "farve" til diagrammer, "bg"/"tekst" til piller.
STATUS_STIL = {
    Medarbejder.STATUS_AFVENTER: {
        "farve": "#EF4444", "bg": "#FEE2E2", "tekst": "#B91C1C",
    },
    Medarbejder.STATUS_DELVIST: {
        "farve": "#F59E0B", "bg": "#FEF3C7", "tekst": "#B45309",
    },
    Medarbejder.STATUS_AFVIKLET: {
        "farve": "#10B981", "bg": "#D1FAE5", "tekst": "#047857",
    },
}

INTET_STIL = {"farve": "#94A3B8", "bg": "#F1F5F9", "tekst": "#64748B"}


def udstyr_stil(afleveret, total):
    """Farve til udstyrs-pillen: rød = intet afleveret, gul = noget, grøn = alt."""
    if total == 0:
        return INTET_STIL
    if afleveret == 0:
        return STATUS_STIL[Medarbejder.STATUS_AFVENTER]
    if afleveret < total:
        return STATUS_STIL[Medarbejder.STATUS_DELVIST]
    return STATUS_STIL[Medarbejder.STATUS_AFVIKLET]

_QSS = """
QWidget { color: @TEXT; font-size: 13px; }
QMainWindow, QDialog, QMessageBox { background: @BG; }
QWidget#scrollInner, QWidget#pageRoot { background: @BG; }
QScrollArea { background: transparent; border: none; }

QToolTip {
    background: @SIDEBAR; color: white; border: none;
    padding: 6px 8px; border-radius: 6px;
}

/* ---------- Sidebar ---------- */
#sidebar { background: @SIDEBAR; }
#sidebar QLabel { background: transparent; }
#appTitle { color: white; font-size: 17px; font-weight: 700; }
#appSub { color: #94A3B8; font-size: 12px; }
#sidebarFod { color: #64748B; font-size: 11px; }
QPushButton[nav="true"] {
    text-align: left; padding: 11px 16px; border: none;
    border-radius: 10px; color: #CBD5E1; background: transparent;
    font-weight: 600; font-size: 14px;
}
QPushButton[nav="true"]:hover { background: #1E293B; color: white; }
QPushButton[nav="true"]:checked { background: @PRIMARY; color: white; }

/* ---------- Sidehoveder og kort ---------- */
#pageTitle { font-size: 26px; font-weight: 700; color: @TEXT; background: transparent; }
#pageSub { color: @MUTED; font-size: 13px; background: transparent; }
#card { background: @SURFACE; border: 1px solid @BORDER; border-radius: 14px; }
#card QLabel { background: transparent; }
#cardTitle { font-size: 15px; font-weight: 700; }
#cardSub { color: @MUTED; font-size: 12px; }
#statTitle { color: @MUTED; font-size: 12px; font-weight: 600; }
#statValue { font-size: 32px; font-weight: 700; }
#statSub { color: @MUTED; font-size: 12px; }
#feltFejl { color: #B91C1C; font-size: 12px; }
#sektionTitel { font-size: 14px; font-weight: 700; padding-top: 6px; }
#hjaelpTekst { color: @MUTED; font-size: 12px; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox:disabled { color: #94A3B8; }

/* ---------- Knapper ---------- */
QPushButton {
    background: @SURFACE; border: 1px solid @BORDER; border-radius: 9px;
    padding: 8px 16px; font-weight: 600; color: @TEXT;
}
QPushButton:hover { background: #F8FAFC; border-color: #CBD5E1; }
QPushButton:pressed { background: #EEF2F7; }
QPushButton[variant="primary"] {
    background: @PRIMARY; color: white; border: 1px solid @PRIMARY;
}
QPushButton[variant="primary"]:hover {
    background: @PRIMARY_HOVER; border-color: @PRIMARY_HOVER;
}
QPushButton[variant="danger"] {
    background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA;
}
QPushButton[variant="danger"]:hover { background: #FEE2E2; }

/* ---------- Felter ---------- */
QLineEdit, QDateEdit, QComboBox {
    background: @SURFACE; border: 1px solid @BORDER; border-radius: 9px;
    padding: 8px 10px; selection-background-color: @PRIMARY;
    selection-color: white;
}
QLineEdit:disabled { background: #F8FAFC; color: #94A3B8; }
QLineEdit:focus, QDateEdit:focus, QComboBox:focus {
    border: 1px solid @PRIMARY;
}
QComboBox::drop-down, QDateEdit::drop-down {
    border: none; background: transparent; width: 28px;
}
QComboBox::down-arrow, QDateEdit::down-arrow {
    image: url(@CHEVRON); width: 12px; height: 8px;
}
QComboBox QAbstractItemView {
    background: @SURFACE; border: 1px solid @BORDER; outline: 0;
    selection-background-color: @PRIMARY_SOFT; selection-color: @TEXT;
}
QCalendarWidget QWidget { background: @SURFACE; }

/* ---------- Tabeller og lister ---------- */
QTableWidget {
    background: @SURFACE; border: none; gridline-color: transparent;
    alternate-background-color: #F8FAFC;
    selection-background-color: @PRIMARY_SOFT; selection-color: @TEXT;
    outline: 0;
}
QTableWidget::item { padding: 4px 10px; border: none; }
QHeaderView::section {
    background: @SURFACE; color: @MUTED; border: none;
    border-bottom: 1px solid @BORDER; padding: 10px; font-weight: 700;
    font-size: 12px;
}
QTableCornerButton::section { background: @SURFACE; border: none; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { border-bottom: 1px solid #F1F5F9; }
QListWidget::item:hover, QListWidget::item:selected { background: transparent; }

/* ---------- Scrollbars ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #CBD5E1; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #CBD5E1; border-radius: 4px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #94A3B8; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def byg_stylesheet():
    tokens = {f"@{navn.upper()}": vaerdi for navn, vaerdi in FARVER.items()}
    tokens["@CHEVRON"] = CHEVRON
    # Længste nøgler først, så @PRIMARY_HOVER ikke rammes af @PRIMARY.
    stylesheet = _QSS
    for token in sorted(tokens, key=len, reverse=True):
        stylesheet = stylesheet.replace(token, tokens[token])
    return stylesheet


def anvend_tema(app: QApplication):
    """Fusion-stilen + lys palette, så udseendet er ens uanset systemtema."""
    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(FARVER["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(FARVER["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.Text, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(FARVER["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(FARVER["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
    app.setPalette(palette)

    app.setStyleSheet(byg_stylesheet())
