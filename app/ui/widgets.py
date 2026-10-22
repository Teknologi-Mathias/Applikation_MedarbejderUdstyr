"""Hjælpeklasser til medarbejdertabellerne."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
)

from app.ui.theme import FARVER

ID_ROLE = Qt.ItemDataRole.UserRole              # sagens id på hver celle i rækken
SORT_ROLE = Qt.ItemDataRole.UserRole + 1        # nøgle til korrekt sortering
STIL_ROLE = Qt.ItemDataRole.UserRole + 2        # {"bg", "tekst"} til PilleDelegate


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


class PilleDelegate(QStyledItemDelegate):
    """Tegner cellens tekst som en farvet pille (bruges til Status og Udstyr).

    Farverne hentes fra cellens STIL_ROLE; uden stil tegnes almindelig tekst.
    """

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

        stil = index.data(STIL_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)

        # Pillen må aldrig tegne ud over sin egen celle.
        painter.setClipRect(opt.rect)
        bredde = min(
            painter.fontMetrics().horizontalAdvance(tekst) + 26,
            max(0, opt.rect.width() - 20),
        )
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
        return QSize(max(hint.width(), 150), hint.height())
