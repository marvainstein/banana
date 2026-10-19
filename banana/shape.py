"""The banana silhouette, shared by the app icon (packaging/make_icons.py) and the menu-bar
icon (app.make_tray_icon), so both follow the pattern of the old round icons: a shape cut
into segments by thin gaps, with a hub where the cursor would be.

Geometry is in a unit square (y down) and scaled by the caller: a crescent made of two circles
(the banana's back and belly), tilted a little, with a stem on one tip. The whole drawing is
then scaled and centred to fill the square inside MARGIN."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QTransform

# back (outer) and belly (inner) circles: the crescent is outer minus inner. A belly circle
# larger than the back one makes the tips meet inside the square and keeps the curve gentle
# (equal circles would give a deep half-moon).
OUTER = (0.50, 0.30, 0.48)     # cx, cy, r
INNER = (0.50, -0.07, 0.62)
TILT = -14.0                   # degrees
HUB = (0.50, 0.33, 0.14)       # cx, cy, r: in the curve, like the menu's hub under the cursor
MARGIN = 0.06                  # empty border around the drawing, as a fraction of the size


def _circle(cx, cy, r) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _tips_unit(t: QTransform) -> tuple[QPointF, QPointF]:
    """Where the two circles cross (left, right), mapped by `t`."""
    (x0, y0, r0), (_, y1, r1) = OUTER, INNER
    d = abs(y1 - y0)
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)       # along the line between centres
    h = math.sqrt(max(0.0, r0 * r0 - a * a))
    y = y0 + a * (1 if y1 > y0 else -1)
    return t.map(QPointF(x0 - h, y)), t.map(QPointF(x0 + h, y))


def _stem_unit(t: QTransform, k: float) -> QPainterPath:
    """A short stalk on the left tip; `k` = how much `t` scales."""
    w, l = 0.06 * k, 0.10 * k
    p = QPainterPath()
    p.addRoundedRect(QRectF(-w / 2, -l, w, l + w * 0.6), w * 0.4, w * 0.4)
    return QTransform().rotate(-52 + TILT).map(p).translated(_tips_unit(t)[0])


def _fit() -> tuple[QTransform, float]:
    """Unit-square transform (tilt, then scale and centre) and its scale factor."""
    rot = QTransform().translate(0.5, 0.5).rotate(TILT).translate(-0.5, -0.5)
    big = QTransform.fromScale(1000, 1000)      # boolean ops flatten curves in absolute units
    art = (rot * big).map(_circle(*OUTER)).subtracted((rot * big).map(_circle(*INNER)))
    art = art.united(big.map(_stem_unit(rot, 1.0))).united((rot * big).map(_circle(*HUB)))
    r = art.boundingRect()
    r = QRectF(r.x() / 1000, r.y() / 1000, r.width() / 1000, r.height() / 1000)
    k = (1 - 2 * MARGIN) / max(r.width(), r.height())
    return rot * QTransform().translate(0.5, 0.5).scale(k, k).translate(-r.center().x(), -r.center().y()), k


FIT, SCALE = _fit()


def _t(s: float) -> QTransform:
    return FIT * QTransform.fromScale(s, s)


def body(s: float) -> QPainterPath:
    """The banana (without stem), `s` px wide."""
    t = _t(s)        # map first, then subtract: boolean ops flatten curves in absolute units
    return t.map(_circle(*OUTER)).subtracted(t.map(_circle(*INNER)))


def stem(s: float) -> QPainterPath:
    return QTransform.fromScale(s, s).map(_stem_unit(FIT, SCALE))


def tips(s: float) -> tuple[QPointF, QPointF]:
    return _tips_unit(_t(s))


def hub_center(s: float) -> QPointF:
    return _t(s).map(QPointF(HUB[0], HUB[1]))


def hub_radius(s: float) -> float:
    return HUB[2] * SCALE * s


def segment_cuts(s: float, n: int = 5) -> list[tuple[QPointF, QPointF]]:
    """Gap lines that cut the body into n segments, radiating from the back circle's centre."""
    c = _t(s).map(QPointF(OUTER[0], OUTER[1]))
    left, right = tips(s)
    a0 = math.atan2(left.y() - c.y(), left.x() - c.x())
    a1 = math.atan2(right.y() - c.y(), right.x() - c.x())
    if a0 < a1:
        a0 += 2 * math.pi            # sweep along the banana's underside
    r = OUTER[2] * SCALE * s * 1.2
    cuts = []
    for i in range(1, n):
        a = a0 + (a1 - a0) * i / n
        cuts.append((c, QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))))
    return cuts
