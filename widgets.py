from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QWidget,
)

from theme import FARVER, STATUS_STIL

LOENNR_ROLE = Qt.ItemDataRole.UserRole          # lønnr. på hver celle i rækken
SORT_ROLE = Qt.ItemDataRole.UserRole + 1        # nøgle til korrekt sortering


class SortItem(QTableWidgetItem):

    def __lt__(self, other):
        a = self.data(SORT_ROLE)
        b = other.data(SORT_ROLE)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return super().__lt__(other)


class StatusDelegate(QStyledItemDelegate):

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        tekst = opt.text
        opt.text = ""

        widget = opt.widget
        stil_objekt = widget.style() if widget else QApplication.style()
        # Tegner baggrund og markering, men uden tekst.
        stil_objekt.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
        )

        stil = STATUS_STIL.get(tekst)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)

        bredde = painter.fontMetrics().horizontalAdvance(tekst) + 26
        hoejde = 24
        rect = QRectF(
            opt.rect.left() + 10,
            opt.rect.center().y() - hoejde / 2 + 0.5,
            bredde,
            hoejde,
        )

        if stil:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(stil["bg"]))
            painter.drawRoundedRect(rect, hoejde / 2, hoejde / 2)
            painter.setPen(QColor(stil["tekst"]))
        else:
            painter.setPen(QColor(FARVER["text"]))

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, tekst)
        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(max(hint.width(), 190), hint.height())


class DonutChart(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._centrum_tal = "0"
        self._centrum_tekst = ""
        self.setMinimumSize(210, 210)

    def saet_data(self, data, centrum_tal, centrum_tekst):
        """data: liste af (navn, antal, farve)."""
        self._data = data
        self._centrum_tal = str(centrum_tal)
        self._centrum_tekst = centrum_tekst
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 16
        if side <= 40:
            return
        tykkelse = max(16.0, side * 0.15)
        rect = QRectF(
            (self.width() - side) / 2 + tykkelse / 2,
            (self.height() - side) / 2 + tykkelse / 2,
            side - tykkelse,
            side - tykkelse,
        )

        pen = QPen(QColor("#EEF2F7"), tykkelse)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        total = sum(antal for _, antal, _ in self._data)
        if total > 0:
            start = 90 * 16
            for _, antal, farve in self._data:
                if antal <= 0:
                    continue
                span = -round(antal / total * 360 * 16)
                pen = QPen(QColor(farve), tykkelse)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawArc(rect, start, span)
                start += span

        h = side * 0.2
        font = QFont(self.font())
        font.setPixelSize(max(20, int(side * 0.2)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(FARVER["text"]))
        p.drawText(
            QRectF(rect.x(), rect.center().y() - h, rect.width(), h),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            self._centrum_tal,
        )

        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(QColor(FARVER["muted"]))
        p.drawText(
            QRectF(rect.x(), rect.center().y() + 2, rect.width(), h),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._centrum_tekst,
        )


class BarChart(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(220)

    def saet_data(self, data):
        """data: liste af (dagnummer, ugedag, antal, er_i_dag, er_weekend)."""
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        venstre, hoejre, top, bund = 6, 6, 24, 46
        plot_h = h - top - bund
        plot_w = w - venstre - hoejre
        if plot_h <= 10 or plot_w <= 10:
            return

        n = len(self._data)
        slot = plot_w / n
        bar_w = min(34.0, slot * 0.62)
        maks = max(1, max(antal for _, _, antal, _, _ in self._data))
        basis = top + plot_h

        p.setPen(QPen(QColor(FARVER["border"]), 1))
        p.drawLine(venstre, int(basis), w - hoejre, int(basis))

        for i, (dag, ugedag, antal, er_i_dag, er_weekend) in enumerate(self._data):
            x = venstre + slot * i + (slot - bar_w) / 2

            if antal > 0:
                bar_h = plot_h * 0.88 * antal / maks
                rect = QRectF(x, basis - bar_h, bar_w, bar_h)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(FARVER["primary"] if er_i_dag else "#A5B4FC"))
                p.drawRoundedRect(rect, 6, 6)

                font = QFont(self.font())
                font.setPixelSize(12)
                font.setBold(True)
                p.setFont(font)
                p.setPen(QColor(FARVER["text"]))
                p.drawText(
                    QRectF(x - 10, rect.top() - 19, bar_w + 20, 17),
                    Qt.AlignmentFlag.AlignCenter,
                    str(antal),
                )
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#E2E8F0"))
                p.drawRoundedRect(QRectF(x, basis - 3, bar_w, 3), 1.5, 1.5)

            # Dagnummer og ugedag under søjlen.
            farve = FARVER["primary"] if er_i_dag else (
                "#94A3B8" if er_weekend else FARVER["text"]
            )
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setBold(er_i_dag)
            p.setFont(font)
            p.setPen(QColor(farve))
            p.drawText(
                QRectF(x - 10, basis + 6, bar_w + 20, 16),
                Qt.AlignmentFlag.AlignCenter,
                str(dag),
            )
            font.setPixelSize(11)
            font.setBold(False)
            p.setFont(font)
            p.setPen(QColor("#94A3B8"))
            p.drawText(
                QRectF(x - 10, basis + 22, bar_w + 20, 16),
                Qt.AlignmentFlag.AlignCenter,
                ugedag,
            )
