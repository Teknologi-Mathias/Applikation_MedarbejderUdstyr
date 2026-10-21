"""Farver, stylesheet og palette for hele programmet.

Mørkt, blødt lilla tema bygget op om #341539. Alle farver er samlet i FARVER
og bruges som @TOKENS i stylesheetet – ret dem her, ikke rundt om i koden.
"""
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from app import alarmer
from app.medarbejder import Medarbejder
from app.opgave import Opgave
from app.stier import ASSETS_MAPPE

CHEVRON = (ASSETS_MAPPE / "chevron_lys.svg").as_posix()
CHEVRON_OP = (ASSETS_MAPPE / "chevron_op_lys.svg").as_posix()

FARVER = {
    "bg": "#1E0D22",            # baggrund bag kort
    "sidebar": "#160A19",
    "sidebar_hover": "#2A1430",
    "sidebar_tekst": "#D8C6DD",
    "surface": "#341539",       # kort, tabeller, dialoger
    "surface_2": "#3D1B43",     # felter og skiftende tabelrækker
    "hover": "#4A2652",
    "border": "#52305A",
    "border_strong": "#6B4373",
    "text": "#F4EAF6",
    "muted": "#BBA4C1",
    "dim": "#8C7592",           # deaktiveret tekst, weekender
    "primary": "#9B4FB3",
    "primary_hover": "#AE62C6",
    "primary_soft": "#4F2659",  # markering og infobokse
    "primary_tekst": "#E9D5F0",
    "danger_bg": "#4D1F2E",
    "danger_hover": "#5C2537",
    "danger_border": "#6E2A3E",
    "danger_tekst": "#FFB3BE",
    "groen": "#5FD4A4",
    "soejle": "#7B5A8A",        # søjler i diagrammet (i dag = primary)
}

# Farver pr. status: "farve" til diagrammer, "bg"/"tekst" til piller.
STATUS_STIL = {
    Medarbejder.STATUS_AFVENTER: {
        "farve": "#F07A8A", "bg": "#4D1F2E", "tekst": "#FFB3BE",
    },
    Medarbejder.STATUS_DELVIST: {
        "farve": "#F2B85B", "bg": "#4A3420", "tekst": "#FFD89A",
    },
    Medarbejder.STATUS_AFVIKLET: {
        "farve": "#5FD4A4", "bg": "#1D4237", "tekst": "#9DEBC8",
    },
}

INTET_STIL = {"farve": "#9C8AA3", "bg": "#46304D", "tekst": "#D4C4D9"}
_ROED = STATUS_STIL[Medarbejder.STATUS_AFVENTER]
_GUL = STATUS_STIL[Medarbejder.STATUS_DELVIST]
_GROEN = STATUS_STIL[Medarbejder.STATUS_AFVIKLET]
_BLAA = {"farve": "#9B8CF5", "bg": "#352D63", "tekst": "#C9C0FF"}

OPGAVE_STIL = {
    Opgave.IKKE_STARTET: INTET_STIL,
    Opgave.I_GANG: _BLAA,
    Opgave.AFVENTER: _GUL,
    Opgave.UDFOERT: _GROEN,
    Opgave.UNDTAGET: {"farve": "#7E6E86", "bg": "#3B2C42", "tekst": "#B9A9C0"},
}

ALARM_STIL = {
    alarmer.KRITISK: _ROED,
    alarmer.ADVARSEL: _GUL,
    alarmer.PLANLAGT: _BLAA,
}


def opgaver_stil(afsluttede, total, forsinket):
    """Farve til opgave-pillen i tabellen: rød = forsinket, grøn = alt klaret."""
    if total == 0:
        return INTET_STIL
    if forsinket:
        return _ROED
    if afsluttede == total:
        return _GROEN
    return _GUL


_QSS = """
QWidget { color: @TEXT; font-size: 13px; }
QMainWindow, QDialog, QMessageBox, QInputDialog { background: @BG; }
QWidget#scrollInner, QWidget#pageRoot { background: @BG; }
QScrollArea { background: transparent; border: none; }
QLabel { background: transparent; }

QToolTip {
    background: @SIDEBAR; color: @TEXT; border: 1px solid @BORDER_STRONG;
    padding: 6px 8px; border-radius: 6px;
}

/* ---------- Sidebar ---------- */
#sidebar { background: @SIDEBAR; border-right: 1px solid @SIDEBAR_HOVER; }
#appTitle { color: white; font-size: 24px; font-weight: 800; letter-spacing: 1px; }
#appSlogan { color: @MUTED; font-size: 12px; }
#sidebarFod { color: @DIM; font-size: 11px; }
#sidebarBruger { color: @SIDEBAR_TEKST; font-size: 12px; font-weight: 600; }
#navSektion {
    color: @DIM; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; padding: 14px 6px 4px 6px;
}
QPushButton[nav="true"] {
    text-align: left; padding: 11px 16px; border: none;
    border-radius: 10px; color: @SIDEBAR_TEKST; background: transparent;
    font-weight: 600; font-size: 14px;
}
QPushButton[nav="true"]:hover { background: @SIDEBAR_HOVER; color: white; }
QPushButton[nav="true"]:checked { background: @PRIMARY; color: white; }

/* ---------- Sidehoveder og kort ---------- */
#pageTitle { font-size: 26px; font-weight: 700; color: @TEXT; }
#pageSub { color: @MUTED; font-size: 13px; }
#card { background: @SURFACE; border: 1px solid @BORDER; border-radius: 14px; }
#cardTitle { font-size: 15px; font-weight: 700; }
#cardSub { color: @MUTED; font-size: 12px; }
#statTitle { color: @MUTED; font-size: 12px; font-weight: 600; }
#statValue { font-size: 32px; font-weight: 700; }
#statSub { color: @MUTED; font-size: 12px; }
#feltFejl { color: @DANGER_TEKST; font-size: 12px; }
#sektionTitel { font-size: 14px; font-weight: 700; padding-top: 6px; }
#hjaelpTekst { color: @MUTED; font-size: 12px; }
#sagTitel { font-size: 20px; font-weight: 700; }
#opgaveRaekke { background: @SURFACE; border: 1px solid @BORDER; border-radius: 10px; }
#opgaveRaekke[fokus="true"] { border: 2px solid @PRIMARY_HOVER; background: @PRIMARY_SOFT; }
#opgaveNavn { font-weight: 600; }
#opgaveMeta { color: @MUTED; font-size: 12px; }
#opgaveForsinket { color: @DANGER_TEKST; font-size: 12px; font-weight: 600; }
QProgressBar#fremdrift { background: @BORDER; border: none; border-radius: 3px; }
QProgressBar#fremdrift::chunk { background: @GROEN; border-radius: 3px; }
#advarsel {
    background: @DANGER_BG; color: @DANGER_TEKST; border: 1px solid @DANGER_BORDER;
    border-radius: 9px; padding: 8px 10px; font-size: 12px;
}
#info {
    background: @PRIMARY_SOFT; color: @PRIMARY_TEKST; border-radius: 9px;
    padding: 8px 10px; font-size: 12px;
}
#forhaandsvisning { background: @SURFACE; border: 1px solid @BORDER; border-radius: 9px; }
#streg { background: @BORDER; max-height: 1px; border: none; }
#loginKort { background: @SURFACE; border: 1px solid @BORDER; border-radius: 18px; }
#beta {
    background: @DANGER_BG; color: @DANGER_TEKST; border: 1px solid @DANGER_BORDER;
    border-radius: 9px; padding: 10px 12px; font-size: 12px; font-weight: 600;
}

/* ---------- Faner: tydelige knapper med ramme og hover ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabWidget::tab-bar { left: 0; }
QTabBar::tab {
    background: @SURFACE; color: @MUTED; padding: 9px 18px; margin: 0 8px 6px 0;
    border: 1px solid @BORDER; border-radius: 10px; font-weight: 600;
}
QTabBar::tab:hover {
    background: @HOVER; color: @TEXT; border: 1px solid @PRIMARY_HOVER;
}
QTabBar::tab:selected {
    background: @PRIMARY; color: white; border: 1px solid @PRIMARY_HOVER;
}

/* ---------- Knapper ---------- */
QPushButton {
    background: @SURFACE_2; border: 1px solid @BORDER; border-radius: 9px;
    padding: 8px 16px; font-weight: 600; color: @TEXT;
}
QPushButton:hover { background: @HOVER; border-color: @BORDER_STRONG; }
QPushButton:pressed { background: @PRIMARY_SOFT; }
QPushButton:disabled { color: @DIM; background: @SURFACE; border-color: @BORDER; }
QPushButton[variant="primary"] {
    background: @PRIMARY; color: white; border: 1px solid @PRIMARY;
}
QPushButton[variant="primary"]:hover {
    background: @PRIMARY_HOVER; border-color: @PRIMARY_HOVER;
}
QPushButton[variant="primary"]:disabled {
    background: @PRIMARY_SOFT; color: @DIM; border-color: @PRIMARY_SOFT;
}
QPushButton[variant="danger"] {
    background: @DANGER_BG; color: @DANGER_TEKST; border: 1px solid @DANGER_BORDER;
}
QPushButton[variant="danger"]:hover { background: @DANGER_HOVER; }
QToolButton[variant="menu"] {
    background: @SURFACE_2; border: 1px solid @BORDER; border-radius: 9px;
    padding: 8px 28px 8px 16px; font-weight: 600; color: @TEXT;
}
QToolButton[variant="menu"]:hover { background: @HOVER; border-color: @BORDER_STRONG; }
QToolButton[variant="menu"]::menu-indicator {
    image: url(@CHEVRON); width: 10px; height: 7px;
    subcontrol-position: right center; right: 10px;
}
QMenu {
    background: @SURFACE; border: 1px solid @BORDER_STRONG; border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 8px 22px 8px 14px; border-radius: 6px; }
QMenu::item:selected { background: @PRIMARY_SOFT; color: white; }
QMenu::item:disabled { color: @DIM; }
QMenu::separator { height: 1px; background: @BORDER; margin: 4px 8px; }

/* ---------- Felter ---------- */
QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {
    background: @SURFACE_2; border: 1px solid @BORDER; border-radius: 9px;
    padding: 8px 10px; selection-background-color: @PRIMARY;
    selection-color: white; color: @TEXT;
}
QPlainTextEdit, QTextEdit { padding: 6px 8px; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {
    background: @SURFACE; color: @DIM;
}
QLineEdit:read-only, QPlainTextEdit:read-only, QTextEdit:read-only { background: @SURFACE; }
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus,
QTextEdit:focus, QSpinBox:focus {
    border: 1px solid @PRIMARY_HOVER;
}
QComboBox::drop-down, QDateEdit::drop-down {
    border: none; background: transparent; width: 28px;
}
QComboBox::down-arrow, QDateEdit::down-arrow {
    image: url(@CHEVRON); width: 12px; height: 8px;
}
QSpinBox { padding-right: 22px; }
QSpinBox::up-button, QSpinBox::down-button {
    background: transparent; border: none; width: 18px;
}
QSpinBox::up-arrow { image: url(@CHEVRON_OP); width: 10px; height: 7px; }
QSpinBox::down-arrow { image: url(@CHEVRON); width: 10px; height: 7px; }
QComboBox QAbstractItemView {
    background: @SURFACE; border: 1px solid @BORDER_STRONG; outline: 0;
    selection-background-color: @PRIMARY_SOFT; selection-color: white; color: @TEXT;
}
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox:disabled { color: @DIM; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid @BORDER_STRONG; background: @SURFACE_2;
}
QCheckBox::indicator:hover { border-color: @PRIMARY_HOVER; }
QCheckBox::indicator:checked { background: @PRIMARY; border-color: @PRIMARY_HOVER; }
QCheckBox::indicator:disabled { background: @SURFACE; border-color: @BORDER; }
QCalendarWidget QWidget { background: @SURFACE; color: @TEXT; }
QCalendarWidget QAbstractItemView:enabled {
    background: @SURFACE; color: @TEXT;
    selection-background-color: @PRIMARY; selection-color: white;
}
QCalendarWidget QToolButton { background: transparent; color: @TEXT; border: none; }

/* ---------- Tabeller og lister ---------- */
QTableWidget {
    background: @SURFACE; border: none; gridline-color: transparent;
    alternate-background-color: @SURFACE_2;
    selection-background-color: @PRIMARY_SOFT; selection-color: white;
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
QListWidget::item { border-bottom: 1px solid @BORDER; }
QListWidget::item:hover, QListWidget::item:selected { background: transparent; }
QListWidget[klikbar="true"]::item:hover { background: @HOVER; border-radius: 8px; }

/* ---------- Scrollbars ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: @BORDER_STRONG; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: @DIM; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: @BORDER_STRONG; border-radius: 4px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: @DIM; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def byg_stylesheet():
    tokens = {f"@{navn.upper()}": vaerdi for navn, vaerdi in FARVER.items()}
    tokens["@CHEVRON"] = CHEVRON
    tokens["@CHEVRON_OP"] = CHEVRON_OP
    # Længste nøgler først, så fx @PRIMARY_HOVER ikke rammes af @PRIMARY.
    stylesheet = _QSS
    for token in sorted(tokens, key=len, reverse=True):
        stylesheet = stylesheet.replace(token, tokens[token])
    return stylesheet


def anvend_tema(app: QApplication):
    """Fusion-stilen + mørk palette, så udseendet er ens uanset systemtema."""
    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(FARVER["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(FARVER["surface_2"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(FARVER["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(FARVER["surface_2"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(FARVER["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(FARVER["dim"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(FARVER["sidebar"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(FARVER["text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(FARVER["primary_hover"]))
    for rolle in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                  QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, rolle, QColor(FARVER["dim"]))
    app.setPalette(palette)

    app.setStyleSheet(byg_stylesheet())
