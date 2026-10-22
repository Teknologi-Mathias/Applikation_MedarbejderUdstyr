"""Farver, stylesheet og palette for hele programmet – det centrale temasystem.

To temaer: "lilla" (standard, mørkt blødt lilla bygget op om #341539) og
"lys". Alle farver ligger i TEMAER og bruges som @TOKENS i stylesheetet.
Statusfarver er semantiske toner (rød/gul/grøn/blå/intet/grå), så nye
statusser kun skal have en tone – ikke en farve pr. tema.

Nyt tema: tilføj en palette i TEMAER med de samme nøgler. Widgets må ikke
hardcode farver; brug FARVER, tonerne eller objectName + stylesheet.

FARVER, STATUS_STIL, OPGAVE_STIL og ALARM_STIL ændres på stedet ved
temaskift, så diagrammer og tabeller følger med uden genstart.
"""
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb as OB
from app.domain.opgave import Opgave
from app.infrastructure.stier import ASSETS_MAPPE
from app.services import action_center

TEMAER = {
    "lilla": {
        "farver": {
            "bg": "#1E0D22", "sidebar": "#160A19", "sidebar_hover": "#2A1430",
            "sidebar_tekst": "#D8C6DD", "sidebar_tekst_staerk": "#FFFFFF",
            "surface": "#341539", "surface_2": "#3D1B43", "hover": "#4A2652",
            "border": "#52305A", "border_strong": "#6B4373",
            "text": "#F4EAF6", "muted": "#BBA4C1", "dim": "#8C7592",
            "primary": "#9B4FB3", "primary_hover": "#AE62C6",
            "primary_soft": "#4F2659", "primary_tekst": "#E9D5F0",
            "danger_bg": "#4D1F2E", "danger_hover": "#5C2537",
            "danger_border": "#6E2A3E", "danger_tekst": "#FFB3BE",
            "groen": "#5FD4A4", "groen_bg": "#1D4237", "groen_tekst": "#9DEBC8",
            "soejle": "#7B5A8A", "skygge": "#6E000000",
        },
        "toner": {
            "roed": {"farve": "#F07A8A", "bg": "#4D1F2E", "tekst": "#FFB3BE"},
            "gul": {"farve": "#F2B85B", "bg": "#4A3420", "tekst": "#FFD89A"},
            "groen": {"farve": "#5FD4A4", "bg": "#1D4237", "tekst": "#9DEBC8"},
            "blaa": {"farve": "#9B8CF5", "bg": "#352D63", "tekst": "#C9C0FF"},
            "intet": {"farve": "#9C8AA3", "bg": "#46304D", "tekst": "#D4C4D9"},
            "graa": {"farve": "#7E6E86", "bg": "#3B2C42", "tekst": "#B9A9C0"},
        },
        "chevron": "chevron_lys.svg", "chevron_op": "chevron_op_lys.svg",
    },
    "lys": {
        "farver": {
            "bg": "#F4F6FA", "sidebar": "#0F172A", "sidebar_hover": "#1E293B",
            "sidebar_tekst": "#CBD5E1", "sidebar_tekst_staerk": "#FFFFFF",
            "surface": "#FFFFFF", "surface_2": "#F8FAFC", "hover": "#EEF2F7",
            "border": "#E2E8F0", "border_strong": "#CBD5E1",
            "text": "#0F172A", "muted": "#64748B", "dim": "#94A3B8",
            "primary": "#4F46E5", "primary_hover": "#4338CA",
            "primary_soft": "#EEF2FF", "primary_tekst": "#3730A3",
            "danger_bg": "#FEF2F2", "danger_hover": "#FEE2E2",
            "danger_border": "#FECACA", "danger_tekst": "#B91C1C",
            "groen": "#10B981", "groen_bg": "#D1FAE5", "groen_tekst": "#047857",
            "soejle": "#A5B4FC", "skygge": "#160F172A",
        },
        "toner": {
            "roed": {"farve": "#EF4444", "bg": "#FEE2E2", "tekst": "#B91C1C"},
            "gul": {"farve": "#F59E0B", "bg": "#FEF3C7", "tekst": "#B45309"},
            "groen": {"farve": "#10B981", "bg": "#D1FAE5", "tekst": "#047857"},
            "blaa": {"farve": "#6366F1", "bg": "#E0E7FF", "tekst": "#4338CA"},
            "intet": {"farve": "#94A3B8", "bg": "#F1F5F9", "tekst": "#64748B"},
            "graa": {"farve": "#64748B", "bg": "#E2E8F0", "tekst": "#475569"},
        },
        "chevron": "chevron.svg", "chevron_op": "chevron_op.svg",
    },
}
STANDARD_TEMA = "lys"

# Status -> tone. Nye statusser tilføjes her.
_STATUS_TONE = {
    Medarbejder.STATUS_AFVENTER: "roed",
    Medarbejder.STATUS_DELVIST: "gul",
    Medarbejder.STATUS_AFVIKLET: "groen",
    OB.STATUS_KANDIDAT: "blaa",
    OB.STATUS_KONTRAKT: "gul",
    OB.STATUS_OPLAERING: "gul",
    OB.STATUS_JOBS: "blaa",
    OB.STATUS_AKTIV: "groen",
    OB.STATUS_ANNULLERET: "graa",
}
_OPGAVE_TONE = {
    Opgave.IKKE_STARTET: "intet", Opgave.I_GANG: "blaa", Opgave.AFVENTER: "gul",
    Opgave.UDFOERT: "groen", Opgave.UNDTAGET: "graa",
}
_ALARM_TONE = {
    action_center.KRITISK: "roed", action_center.ADVARSEL: "gul",
    action_center.PLANLAGT: "blaa",
}

# Aktive værdier (ændres på stedet ved temaskift).
FARVER: dict = {}
TONER: dict = {}
STATUS_STIL: dict = {}
OPGAVE_STIL: dict = {}
ALARM_STIL: dict = {}
INTET_STIL: dict = {}
aktivt_tema = STANDARD_TEMA


def _saet_palette(navn: str) -> None:
    global aktivt_tema
    tema = TEMAER.get(navn, TEMAER[STANDARD_TEMA])
    aktivt_tema = navn if navn in TEMAER else STANDARD_TEMA
    FARVER.clear()
    FARVER.update(tema["farver"])
    FARVER["chevron"] = (ASSETS_MAPPE / tema["chevron"]).as_posix()
    FARVER["chevron_op"] = (ASSETS_MAPPE / tema["chevron_op"]).as_posix()
    TONER.clear()
    TONER.update(tema["toner"])
    for maal, kilde in ((STATUS_STIL, _STATUS_TONE), (OPGAVE_STIL, _OPGAVE_TONE),
                        (ALARM_STIL, _ALARM_TONE)):
        maal.clear()
        maal.update({noegle: TONER[tone] for noegle, tone in kilde.items()})
    INTET_STIL.clear()
    INTET_STIL.update(TONER["intet"])


_saet_palette(STANDARD_TEMA)


def status_stil(status: str) -> dict:
    return STATUS_STIL.get(status, INTET_STIL)


def opgaver_stil(afsluttede, total, forsinket):
    """Farve til opgave-pillen i tabellen: rød = forsinket, grøn = alt klaret."""
    if total == 0:
        return INTET_STIL
    if forsinket:
        return TONER["roed"]
    if afsluttede == total:
        return TONER["groen"]
    return TONER["gul"]


_QSS = """
QWidget { color: @TEXT; font-size: 13px; }
QMainWindow, QDialog, QMessageBox, QInputDialog { background: @BG; }
QWidget#scrollInner, QWidget#pageRoot { background: @BG; }
QScrollArea { background: transparent; border: none; }
QLabel { background: transparent; }

QToolTip {
    background: @SIDEBAR; color: @SIDEBAR_TEKST_STAERK; border: 1px solid @BORDER_STRONG;
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

/* ---------- Navigation med undersider ---------- */
QPushButton[navSektion="true"] {
    text-align: left; padding: 9px 12px; border: none; border-radius: 8px;
    color: @DIM; background: transparent; font-size: 11px; font-weight: 800;
    letter-spacing: 1px;
}
QPushButton[navSektion="true"]:hover { color: @SIDEBAR_TEKST; background: @SIDEBAR_HOVER; }
QPushButton[navUnder="true"] {
    text-align: left; padding: 7px 14px 7px 26px; border: none;
    border-radius: 8px; color: @SIDEBAR_TEKST; background: transparent;
    font-weight: 500; font-size: 13px;
}
QPushButton[navUnder="true"]:hover { background: @SIDEBAR_HOVER; color: @SIDEBAR_TEKST_STAERK; }
QPushButton[navUnder="true"]:checked { background: @PRIMARY; color: white; font-weight: 600; }
#antalBadge {
    background: @PRIMARY_SOFT; color: @PRIMARY_TEKST; border-radius: 10px;
    font-weight: 700; font-size: 12px; padding: 3px 8px;
}
#lagringOnline {
    background: @GROEN_BG; color: @GROEN_TEKST; border-radius: 8px;
    padding: 4px 8px; font-size: 11px; font-weight: 700;
}
#lagringOffline {
    background: @DANGER_BG; color: @DANGER_TEKST; border-radius: 8px;
    padding: 4px 8px; font-size: 11px; font-weight: 700;
}
#tomTekst { color: @MUTED; padding: 44px 0; }
#loginTitel { color: @TEXT; font-size: 30px; font-weight: 800; letter-spacing: 1px; }
#raekkeTitel { font-weight: 600; }
#raekkeUnder { color: @MUTED; font-size: 12px; }
#laastOpgave { color: @DIM; font-size: 12px; font-style: italic; }
#milepaelTitel { color: @MUTED; font-size: 12px; font-weight: 800; letter-spacing: 1px; padding-top: 6px; }
"""


def byg_stylesheet():
    tokens = {f"@{navn.upper()}": vaerdi for navn, vaerdi in FARVER.items()}
    # Længste nøgler først, så fx @PRIMARY_HOVER ikke rammes af @PRIMARY.
    stylesheet = _QSS
    for token in sorted(tokens, key=len, reverse=True):
        stylesheet = stylesheet.replace(token, tokens[token])
    return stylesheet


def anvend_tema(app: QApplication, navn: str = STANDARD_TEMA) -> None:
    """Fusion-stilen + valgt palette, så udseendet er ens uanset systemtema."""
    _saet_palette(navn)
    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)

    palette = QPalette()
    roller = {
        QPalette.ColorRole.Window: "bg", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface_2", QPalette.ColorRole.AlternateBase: "surface",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "surface_2",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.PlaceholderText: "dim", QPalette.ColorRole.ToolTipBase: "sidebar",
        QPalette.ColorRole.ToolTipText: "sidebar_tekst_staerk",
        QPalette.ColorRole.Link: "primary_hover",
    }
    for rolle, noegle in roller.items():
        palette.setColor(rolle, QColor(FARVER[noegle]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    for rolle in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                  QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, rolle, QColor(FARVER["dim"]))
    app.setPalette(palette)
    app.setStyleSheet(byg_stylesheet())
