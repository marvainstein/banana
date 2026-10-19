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
    c = radial.SIZE / 2
    for i in range(n):
        a0, a1, r0, r1 = radial.petal(n, i)
        a, r = math.radians((a0 + a1) / 2), (r0 + r1) / 2
        assert m.hit(QPointF(c + r * math.cos(a), c - r * math.sin(a))) == i
    assert m.hit(QPointF(c, c)) == -2                      # the hub
    assert m.hit(QPointF(c, c - (radial.R_OUT + 60))) == -1  # far above


def test_banana_is_open_at_the_top_and_thin_at_the_tips():
    CONFIG["menu_shape"] = "banana"
    try:
        m = menu_with(8)
        c = radial.SIZE / 2
        assert m.hit(QPointF(c, c - 110)) == -1            # the gap above the hub
        tip, middle = radial.petal(8, 0), radial.petal(8, 3)
        assert tip[3] < middle[3]
    finally:
        CONFIG["menu_shape"] = "banana"
