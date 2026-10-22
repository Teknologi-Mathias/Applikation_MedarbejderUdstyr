"""Laver assets/IN-BASE.ico (Windows-ikon til .exe, proceslinje og Jobliste).

Ikonet renderes fra assets/IN-BASE-ikon.svg i flere størrelser og pakkes i
én .ico-fil (PNG-baserede billeder, understøttet siden Windows Vista).
Kør igen, hvis logoet ændres:

    python tools/lav_ikon.py
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROD = Path(__file__).resolve().parents[1]
KILDE = ROD / "assets" / "IN-BASE-ikon.svg"
MAAL = ROD / "assets" / "IN-BASE.ico"
STOERRELSER = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _png(renderer: QSvgRenderer, stoerrelse: int) -> bytes:
    billede = QImage(stoerrelse, stoerrelse, QImage.Format.Format_ARGB32)
    billede.fill(Qt.GlobalColor.transparent)
    maler = QPainter(billede)
    maler.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(maler)
    maler.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    billede.save(buffer, "PNG")
    return bytes(data)


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(KILDE))
    if not renderer.isValid():
        print(f"Kan ikke læse {KILDE}")
        return 1
    billeder = [(s, _png(renderer, s)) for s in STOERRELSER]
    # ICO: header (6 byte) + katalog (16 byte pr. billede) + PNG-data.
    hoved = struct.pack("<HHH", 0, 1, len(billeder))
    offset = 6 + 16 * len(billeder)
    katalog, data = b"", b""
    for stoerrelse, png in billeder:
        side = 0 if stoerrelse >= 256 else stoerrelse   # 0 betyder 256
        katalog += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        data += png
    MAAL.write_bytes(hoved + katalog + data)
    print(f"Skrev {MAAL.name} ({', '.join(str(s) for s in STOERRELSER)} px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
