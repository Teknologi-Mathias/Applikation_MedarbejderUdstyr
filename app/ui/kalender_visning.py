"""Kalenderens dag- og ugevisning: tegnet selv med QPainter (ingen QCalendarWidget).

KalenderVisning består af et hoved (ugedage og heldagsbjælken) og et timegitter
i et scrollområde. Begivenheder over flere døgn vises i heldagsbjælken.
Overlappende begivenheder deles om bredden (kalender.placer_i_kolonner).

Mus: klik eller træk i en tom tid -> ny_begivenhed; klik på en begivenhed ->
aabn. Farverne kommer fra temaet (FARVER/TONER) og kalenderens egen farve.
"""
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from app.domain import kalender as kl
from app.ui.hjaelpere import UGEDAGE_KORT
from app.ui.theme import FARVER, TONER

TIME_HOEJDE = 44            # pixels pr. time
VENSTRE = 56                # bredde til klokkeslættene
KVARTER = 15                # minutter, musen fanger til
RAEKKE_HOEJDE = 20          # en linje i heldagsbjælken
HOVED_HOEJDE = 40           # ugedag og dato
START_TIME = 7              # visningen åbner her


def _farve(hex_farve: str, alfa: int = 255) -> QColor:
    farve = QColor(hex_farve or kl.FARVER[0])
    farve.setAlpha(alfa)
    return farve


def er_heldagsbjaelke(f: kl.Forekomst) -> bool:
    return f.heldag or f.slut - f.start >= timedelta(hours=24)


def tidstekst(f: kl.Forekomst) -> str:
    if f.heldag:
        sidste = f.slut - timedelta(days=1)
        return "Hele dagen" if sidste.date() == f.start.date() \
            else f"{f.start:%d-%m} – {sidste:%d-%m}"
    if f.start.date() != f.slut.date():
        return f"{f.start:%d-%m %H:%M} – {f.slut:%d-%m %H:%M}"
    return f"{f.start:%H:%M}–{f.slut:%H:%M}"


class _Gitter(QWidget):
    """Timegitteret med de tidsbestemte begivenheder."""

    def __init__(self, visning: "KalenderVisning"):
        super().__init__()
        self.v = visning
        self.setMinimumHeight(24 * TIME_HOEJDE)
        self.setMouseTracking(True)
        self._traek = None          # (dag-index, anker-minut, aktuelt minut) under træk
        self._klik = None           # forekomsten, der blev trykket på

    def kolonne(self, index: int) -> QRectF:
        bredde = (self.width() - VENSTRE) / max(1, len(self.v.dage))
        return QRectF(VENSTRE + index * bredde, 0, bredde, self.height())

    def _sted(self, pos) -> tuple[int, int] | None:
        """(dag-index, minut afrundet til kvarter) under musen."""
        if pos.x() < VENSTRE or not self.v.dage:
            return None
        bredde = (self.width() - VENSTRE) / len(self.v.dage)
        index = min(len(self.v.dage) - 1, int((pos.x() - VENSTRE) // bredde))
        minut = max(0, min(24 * 60, int(pos.y() / TIME_HOEJDE * 60) // KVARTER * KVARTER))
        return index, minut

    def _ramt(self, pos):
        return next((f for rekt, f in reversed(self.v.felter) if rekt.contains(pos)), None)

    ### ----- tegning --------------------------------------------------------

    def paintEvent(self, _event):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.RenderHint.Antialiasing)
        maler.fillRect(self.rect(), QColor(FARVER["surface"]))
        streg, svag = QColor(FARVER["border"]), QColor(FARVER["border"])
        svag.setAlpha(110)
        lille = QFont(self.font())
        lille.setPointSizeF(max(7.0, lille.pointSizeF() - 1.5))
        maler.setFont(lille)
        for time_ in range(24):
            y = time_ * TIME_HOEJDE
            maler.setPen(QPen(streg, 1))
            maler.drawLine(QPointF(VENSTRE, y), QPointF(self.width(), y))
            maler.setPen(QPen(svag, 1, Qt.PenStyle.DotLine))
            maler.drawLine(QPointF(VENSTRE, y + TIME_HOEJDE / 2),
                           QPointF(self.width(), y + TIME_HOEJDE / 2))
            if time_:
                maler.setPen(QColor(FARVER["muted"]))
                maler.drawText(QRectF(0, y - 8, VENSTRE - 8, 16),
                               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                               f"{time_:02d}:00")
        i_dag = date.today()
        for index, dag in enumerate(self.v.dage):
            kol = self.kolonne(index)
            if dag == i_dag:
                fremhaev = QColor(FARVER["primary_soft"])
                fremhaev.setAlpha(90)
                maler.fillRect(kol, fremhaev)
            maler.setPen(QPen(streg, 1))
            maler.drawLine(kol.topLeft(), kol.bottomLeft())

        self.v.felter = []
        for index, dag in enumerate(self.v.dage):
            kol = self.kolonne(index)
            for segment, kolonne, antal, forekomst in self.v.dagens_segmenter(dag):
                top = _minutter(segment.start, dag) / 60 * TIME_HOEJDE
                bund = max(top + TIME_HOEJDE / 3, _minutter(segment.slut, dag) / 60 * TIME_HOEJDE)
                bredde = (kol.width() - 6) / antal
                rekt = QRectF(kol.left() + 2 + kolonne * bredde, top + 1, bredde - 2, bund - top - 2)
                self.v.tegn_felt(maler, rekt, forekomst, lille)
                self.v.felter.append((rekt, forekomst))

        if self._traek:
            index, fra, til = self._valgt_tid()
            kol = self.kolonne(index)
            valg = QColor(FARVER["primary"])
            valg.setAlpha(60)
            maler.fillRect(QRectF(kol.left() + 2, fra / 60 * TIME_HOEJDE,
                                  kol.width() - 4, (til - fra) / 60 * TIME_HOEJDE), valg)

        nu = datetime.now()
        if nu.date() in self.v.dage:
            kol = self.kolonne(self.v.dage.index(nu.date()))
            y = (nu.hour * 60 + nu.minute) / 60 * TIME_HOEJDE
            maler.setPen(QPen(QColor(TONER["roed"]["farve"]), 2))
            maler.drawLine(QPointF(kol.left(), y), QPointF(kol.right(), y))
            maler.setBrush(QColor(TONER["roed"]["farve"]))
            maler.drawEllipse(QPointF(kol.left(), y), 4, 4)
        maler.end()

    ### ----- mus ------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self._klik = self._ramt(pos)
        sted = None if self._klik else self._sted(pos)
        self._traek = (sted[0], sted[1], sted[1]) if sted else None
        self.update()

    def _valgt_tid(self) -> tuple[int, int, int]:
        """(dag-index, fra-minut, til-minut) for trækket; et klik giver en time."""
        index, anker, aktuel = self._traek
        fra, til = min(anker, aktuel), max(anker, aktuel) + KVARTER
        if til - fra <= KVARTER:
            til = fra + 60
        return index, fra, min(til, 24 * 60)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._traek:
            sted = self._sted(pos)
            if sted:
                self._traek = (self._traek[0], self._traek[1], min(sted[1], 24 * 60 - KVARTER))
                self.update()
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self._ramt(pos)
                           else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._klik is not None:
            forekomst, self._klik = self._klik, None
            if forekomst is self._ramt(event.position()):
                self.v.aabn.emit(forekomst)
            return
        if self._traek:
            index, fra, til = self._valgt_tid()
            self._traek = None
            self.update()
            dag = kl.dagens_start(self.v.dage[index])
            self.v.ny_begivenhed.emit(dag + timedelta(minutes=fra), dag + timedelta(minutes=til),
                                      False)


class _Hoved(QWidget):
    """Ugedage og heldagsbjælken over timegitteret."""

    def __init__(self, visning: "KalenderVisning"):
        super().__init__()
        self.v = visning
        self.setMouseTracking(True)
        self.felter = []

    def opdater_hoejde(self):
        self.setFixedHeight(HOVED_HOEJDE + max(1, len(self.v.baner)) * RAEKKE_HOEJDE + 8)
        self.update()

    def paintEvent(self, _event):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.RenderHint.Antialiasing)
        maler.fillRect(self.rect(), QColor(FARVER["surface"]))
        gitter = self.v.gitter
        lille = QFont(self.font())
        lille.setPointSizeF(max(7.0, lille.pointSizeF() - 1.5))
        fed = QFont(self.font())
        fed.setBold(True)
        i_dag = date.today()
        for index, dag in enumerate(self.v.dage):
            kol = gitter.kolonne(index)
            maler.setPen(QColor(FARVER["primary"] if dag == i_dag else FARVER["muted"]))
            maler.setFont(lille)
            maler.drawText(QRectF(kol.left(), 4, kol.width(), 16), Qt.AlignmentFlag.AlignCenter,
                           UGEDAGE_KORT[dag.weekday()].upper())
            maler.setFont(fed)
            maler.setPen(QColor(FARVER["primary"] if dag == i_dag else FARVER["text"]))
            maler.drawText(QRectF(kol.left(), 18, kol.width(), 20), Qt.AlignmentFlag.AlignCenter,
                           f"{dag.day}/{dag.month}")
        maler.setPen(QColor(FARVER["muted"]))
        maler.setFont(lille)
        maler.drawText(QRectF(0, HOVED_HOEJDE, VENSTRE - 8, RAEKKE_HOEJDE),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Hele dagen")
        self.felter = []
        for bane, (forekomst, fra, til) in self.v.baner_liste():
            venstre, hoejre = gitter.kolonne(fra).left(), gitter.kolonne(til).right()
            rekt = QRectF(venstre + 2, HOVED_HOEJDE + bane * RAEKKE_HOEJDE + 1,
                          hoejre - venstre - 4, RAEKKE_HOEJDE - 2)
            self.v.tegn_felt(maler, rekt, forekomst, lille, kompakt=True)
            self.felter.append((rekt, forekomst))
        maler.setPen(QPen(QColor(FARVER["border"]), 1))
        maler.drawLine(QPointF(0, self.height() - 1), QPointF(self.width(), self.height() - 1))
        maler.end()

    def _ramt(self, pos):
        return next((f for rekt, f in self.felter if rekt.contains(pos)), None)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._ramt(event.position())
                       else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        forekomst = self._ramt(pos)
        if forekomst is not None:
            self.v.aabn.emit(forekomst)
        elif pos.y() >= HOVED_HOEJDE and pos.x() >= VENSTRE and self.v.dage:
            bredde = (self.v.gitter.width() - VENSTRE) / len(self.v.dage)
            index = min(len(self.v.dage) - 1, int((pos.x() - VENSTRE) // bredde))
            start = kl.dagens_start(self.v.dage[index])
            self.v.ny_begivenhed.emit(start, start + timedelta(days=1), True)


def _minutter(tid: datetime, dag: date) -> float:
    return max(0.0, min(24 * 60.0, (tid - kl.dagens_start(dag)).total_seconds() / 60))


class KalenderVisning(QWidget):
    """Dag- eller ugevisning af forekomster. vis(dage, forekomster, farver)."""

    ny_begivenhed = Signal(object, object, bool)    # start, slut, heldag
    aabn = Signal(object)                           # Forekomst

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dage: list[date] = []
        self.forekomster: list[kl.Forekomst] = []
        self.farver: dict = {}
        self.dempede: set = set()       # kalender-id'er vist nedtonet (fx kun ledig/optaget)
        self.baner: list = []
        self.felter: list = []
        self._segmenter: dict = {}

        self.gitter = _Gitter(self)
        self.hoved = _Hoved(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.gitter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.hoved)
        layout.addWidget(self.scroll, 1)

        self._ur = QTimer(self)             # "nu"-linjen
        self._ur.setInterval(60_000)
        self._ur.timeout.connect(self.gitter.update)
        self._ur.start()
        self.hoved.opdater_hoejde()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Hovedet følger gitterets kolonner (gitteret er smallere pga. scrollbaren).
        self.hoved.setContentsMargins(0, 0, self.scroll.verticalScrollBar().sizeHint().width(), 0)

    def rul_til_morgen(self) -> None:
        self.scroll.verticalScrollBar().setValue(START_TIME * TIME_HOEJDE)

    def vis(self, dage: list[date], forekomster: list, farver: dict, dempede=()) -> None:
        self.dage = list(dage)
        self.forekomster = list(forekomster)
        self.farver = dict(farver)
        self.dempede = set(dempede)
        self._beregn()
        self.hoved.opdater_hoejde()
        self.gitter.update()

    def ryd(self) -> None:
        self.vis(self.dage, [], {})

    ### ----- placering ------------------------------------------------------

    def _beregn(self) -> None:
        if not self.dage:
            self.baner, self._segmenter = [], {}
            return
        foerste, sidste = self.dage[0], self.dage[-1]
        # Heldagsbjælken: hver forekomst får den første ledige bane i sine dage.
        baner, ledig_fra = [], []
        for f in (f for f in self.forekomster if er_heldagsbjaelke(f)):
            slut = f.slut - timedelta(microseconds=1) if f.slut > f.start else f.slut
            fra = max(f.start.date(), foerste)
            til = min(slut.date(), sidste)
            if fra > til:
                continue
            i_fra, i_til = self.dage.index(fra), self.dage.index(til)
            bane = next((i for i, ledig in enumerate(ledig_fra) if ledig <= i_fra), None)
            if bane is None:
                ledig_fra.append(0)
                bane = len(ledig_fra) - 1
            ledig_fra[bane] = i_til + 1
            baner.append((bane, (f, i_fra, i_til)))
        self.baner = baner
        # Timegitteret: forekomsten skåret til hver dag og placeret i kolonner.
        self._segmenter = {}
        for dag in self.dage:
            start, slut = kl.dagens_start(dag), kl.dagens_start(dag + timedelta(days=1))
            segmenter, original = [], {}
            for f in self.forekomster:
                if er_heldagsbjaelke(f) or not (f.start < slut and (f.slut > start or f.start >= start)):
                    continue
                segment = kl.Forekomst(f.begivenhed, max(f.start, start), min(f.slut, slut))
                segmenter.append(segment)
                original[id(segment)] = f
            self._segmenter[dag] = [(s, k, n, original[id(s)])
                                    for s, k, n in kl.placer_i_kolonner(segmenter)]

    def baner_liste(self) -> list:
        return self.baner

    def dagens_segmenter(self, dag: date) -> list:
        return self._segmenter.get(dag, [])

    ### ----- et felt --------------------------------------------------------

    def tegn_felt(self, maler: QPainter, rekt: QRectF, f: kl.Forekomst, font: QFont,
                  kompakt: bool = False) -> None:
        hex_farve = self.farver.get(f.begivenhed.kalender_id, kl.FARVER[0])
        dempet = f.begivenhed.maskeret or f.begivenhed.kalender_id in self.dempede
        maler.setPen(Qt.PenStyle.NoPen)
        maler.setBrush(_farve(hex_farve, 45 if dempet else 70))
        maler.drawRoundedRect(rekt, 4, 4)
        maler.setBrush(_farve(hex_farve, 130 if dempet else 255))
        maler.drawRoundedRect(QRectF(rekt.left(), rekt.top(), 3, rekt.height()), 1.5, 1.5)
        maler.setPen(QColor(FARVER["muted" if dempet else "text"]))
        titel = ("🔒 " if f.begivenhed.privat else "") + f.titel
        indre = rekt.adjusted(7, 2, -3, -2)
        if kompakt or rekt.height() < 34:
            if not kompakt and not f.heldag:
                titel = f"{f.start:%H:%M} {titel}"
            fed = QFont(font)
            fed.setBold(True)
            maler.setFont(fed)
            maler.drawText(indre, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           maler.fontMetrics().elidedText(titel, Qt.TextElideMode.ElideRight,
                                                          int(indre.width())))
            return
        fed = QFont(font)
        fed.setBold(True)
        maler.setFont(fed)
        linje = maler.fontMetrics().height()
        maler.drawText(QRectF(indre.left(), indre.top(), indre.width(), linje),
                       Qt.AlignmentFlag.AlignLeft,
                       maler.fontMetrics().elidedText(titel, Qt.TextElideMode.ElideRight,
                                                      int(indre.width())))
        maler.setFont(font)
        detaljer = tidstekst(f) + (f" · {f.begivenhed.sted}" if f.begivenhed.sted else "")
        maler.drawText(QRectF(indre.left(), indre.top() + linje, indre.width(),
                              indre.height() - linje),
                       Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, detaljer)


def dage_i(visning: str, dag: date) -> list[date]:
    """"dag" -> [dag]; "uge" -> ugens syv dage (mandag først)."""
    if visning == "dag":
        return [dag]
    start = kl.uge_start(dag)
    return [start + timedelta(days=i) for i in range(7)]


def tidsrum(dage: list[date]) -> tuple[datetime, datetime]:
    return (datetime.combine(dage[0], time()), datetime.combine(dage[-1] + timedelta(days=1), time()))
