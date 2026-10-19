"""Draw the Banana app icon (banana/assets/banana.png, .ico, .icns) from banana/shape.py.

    QT_QPA_PLATFORM=offscreen python packaging/make_icons.py

Same pattern as the old round icon: yellow segments split by dark gaps, a dark hub with
the Shift arrow, now in the curve of a banana."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen, QPolygonF, QRadialGradient)

from banana import glass, shape  # noqa: E402

GAP = "#2a2438"              # the dark spokes / hub of the old icon
SEGMENTS = ["#fff1a6", "#ffe45c", "#ffd23f", "#ffc72c", "#f2a516"]


def draw(s: int) -> QImage:
    img = QImage(s, s, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    body, stem = shape.body(s), shape.stem(s)

    # soft drop shadow
    p.save()
    p.translate(0, 0.025 * s)
    p.fillPath(body.united(stem), QColor(0, 0, 0, 55))
    p.restore()

    # segments: the body cut into wedges, light to golden
    cuts = shape.segment_cuts(s, len(SEGMENTS))
    c = cuts[0][0]
    ends = [shape.tips(s)[0]] + [b for _, b in cuts] + [shape.tips(s)[1]]
    far = s * 3
    for i, col in enumerate(SEGMENTS):
        a, b = ends[i], ends[i + 1]
        wedge = QPainterPath(c)
        for q in (a, b):
            d = q - c
            k = far / max(1e-6, (d.x() ** 2 + d.y() ** 2) ** 0.5)
            wedge.lineTo(c + d * k)
        wedge.closeSubpath()
        p.fillPath(body.intersected(wedge), QColor(col))

    # glossy light along the back, darker belly
    r = body.boundingRect()
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, QColor(255, 255, 255, 0))
    g.setColorAt(0.55, QColor(255, 255, 255, 70))
    g.setColorAt(1.0, QColor(120, 70, 0, 60))
    p.fillPath(body, g)

    # brown tips
    for tip, rad in ((shape.tips(s)[0], 0.10), (shape.tips(s)[1], 0.11)):
        tg = QRadialGradient(tip, rad * s)
        tg.setColorAt(0.0, QColor(95, 60, 20, 255))
        tg.setColorAt(0.45, QColor(120, 80, 20, 150))
        tg.setColorAt(1.0, QColor(120, 80, 20, 0))
        p.fillPath(body, tg)
    cap = QPainterPath()
    cap.addEllipse(shape.tips(s)[1], 0.045 * s, 0.045 * s)
    p.fillPath(body.intersected(cap), QColor("#5c3d14"))       # the dark end of a banana
    p.fillPath(stem, QColor("#6e5520"))

    # gaps between segments, like the spokes of the round icon
    p.save()
    p.setClipPath(body)
    p.setPen(QPen(QColor(GAP), 0.026 * s, Qt.SolidLine, Qt.FlatCap))
    for a, b in cuts:
        p.drawLine(a, b)
    p.restore()
    p.setPen(QPen(QColor(GAP), 0.014 * s))
    p.setBrush(Qt.NoBrush)
    p.drawPath(body.united(stem))

    # hub with the Shift arrow
    hc, hr = shape.hub_center(s), shape.hub_radius(s)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(GAP))
    p.drawEllipse(hc, hr, hr)
    p.setPen(glass.iridescent_pen(hc, 0.012 * s, 200))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(hc, hr * 0.97, hr * 0.97)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(hc, hr * 0.62, hr * 0.62)
    u = hr * 0.42
    arrow = QPolygonF([QPointF(0, -u), QPointF(u * 0.95, -u * 0.02), QPointF(u * 0.42, -u * 0.02),
                       QPointF(u * 0.42, u * 0.85), QPointF(-u * 0.42, u * 0.85),
                       QPointF(-u * 0.42, -u * 0.02), QPointF(-u * 0.95, -u * 0.02)])
    p.setBrush(QColor(glass.ACCENT_C))
    p.drawPolygon(arrow.translated(hc))
    p.end()
    return img


def to_pil(img: QImage) -> Image.Image:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombytes("RGBA", (img.width(), img.height()), bytes(img.constBits()))


def main():
    QGuiApplication([])
    out = ROOT / "banana" / "assets"
    big = to_pil(draw(1024))
    big.save(out / "banana.png")
    big.save(out / "banana.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(out / "banana.icns")
    print("wrote", ", ".join(f"banana.{e}" for e in ("png", "ico", "icns")))


if __name__ == "__main__":
    main()
