"""Radial menu geometry: every petal is hit where it's drawn, in both menu shapes."""
import math

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from banana import radial
from banana.util import CONFIG


@pytest.fixture(params=["banana", "round"])
def shape(request):
    old = CONFIG.get("menu_shape")
    CONFIG["menu_shape"] = request.param
    yield request.param
    CONFIG["menu_shape"] = old


def menu_with(n: int) -> radial.RadialMenu:
    QApplication.instance() or QApplication([])
    m = radial.RadialMenu(lambda p: {"Convert": [radial.Item(f"F{i}") for i in range(n)]}, lambda p: "")
    m._load(["x.png"])
    return m


@pytest.mark.parametrize("n", [2, 3, 6, 8, 10])
def test_each_petal_is_hit_at_its_centre(shape, n):
    m = menu_with(n)
    w, h, hub = radial.frame()
    assert m.width() == w and m.height() == h
    for i in range(n):
        c, a0, a1, r0, r1 = radial.petal(n, i)
        a, r = math.radians((a0 + a1) / 2), (r0 + r1) / 2
        p = QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))
        assert 0 <= p.x() <= w and 0 <= p.y() <= h       # drawn inside the window
        assert m.hit(p) == i
    assert m.hit(hub) == -2
    # outside: above the banana's open top, or beyond the ring
    up = 70 if shape == "banana" else radial.R_OUT + 60
    assert m.hit(QPointF(hub.x(), hub.y() - up)) == -1


def test_banana_is_open_at_the_top_and_thin_at_the_tips():
    CONFIG["menu_shape"] = "banana"
    try:
        menu_with(8)
        tip, middle = radial.petal(8, 0), radial.petal(8, 3)
        assert tip[4] - tip[3] < middle[4] - middle[3]     # thinner at the tips
        w, h, hub = radial.frame()
        assert w > 1.8 * h                                  # long, not round
        c, a0, _, r0, _ = tip
        assert c.y() - r0 * math.sin(math.radians(a0)) < hub.y()   # the tips curl up past the hub
        # a tilted tip leaves a horizontal label less room than the flat middle
        assert radial.label_room(*tip[1:]) < radial.label_room(*middle[1:])
    finally:
        CONFIG["menu_shape"] = "banana"
