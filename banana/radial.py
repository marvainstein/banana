"""The radial drop menu that pops up under the cursor while you Shift+drag a file.

Rendering: the moment the menu opens we snapshot the screen behind it; a worker thread then
refracts that snapshot through the menu's shape (see liquid.py). Until that's ready (~60 ms)
a cheap frosted version is drawn, so the menu still appears instantly."""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRectF, QRunnable, Qt,
                            QThreadPool, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import glass
from .i18n import tr
from .util import CONFIG


@dataclass
class Item:
    label: str
    glyph: str = ""
    run: Callable[[list[str]], None] | None = None
    key: str = ""
    hint: str = ""


SIZE = 400          # window size (room for shadow + hover pop)
R_OUT = 158         # outer radius of petals
R_IN = 60           # inner radius of petals
R_HUB = 50          # hub radius
GAP_DEG = 3.2
CORNER = 10


def sector_path(c: QPointF, r0: float, r1: float, a0: float, a1: float) -> QPainterPath:
    """Annular sector between angles a0..a1 (degrees, Qt convention: 0 = 3 o'clock, CCW)."""
    path = QPainterPath()
    outer = QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1)
    inner = QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0)
    path.arcMoveTo(outer, a0)
    path.arcTo(outer, a0, a1 - a0)
    path.arcTo(inner, a1, -(a1 - a0))
    path.closeSubpath()
    return path


def angles(n: int, i: int) -> tuple[float, float]:
    span = 360.0 / n
    start = 90 + span / 2 - (i + 1) * span   # first petal centred at 12 o'clock, clockwise
    return start + GAP_DEG / 2, start + span - GAP_DEG / 2


# "banana" (Settings → Menu shape): a long band under the hub that curls up around it at the
# tips, like the app icon. Its petals are sectors of a big circle whose centre sits far above
# the hub, so the band is nearly flat in the middle; it's thickest there and thins towards the
# tips. "round" is the original ring around the hub.
BANANA_W, BANANA_H = 670, 330   # window
BANANA_HUB_Y = 130              # hub centre (= the cursor), from the top
BANANA_R0 = 260                 # inner radius of the band, around the far centre
BANANA_THICK = 96               # band thickness in the middle
BANANA_TIP = 0.62               # thickness at the tips, relative to the middle
BANANA_ARC = 130.0              # degrees covered, centred at 6 o'clock
BANANA_GAP = 0.9                # degrees between petals (≈ 4 px at that radius)
BANANA_CORNER = 6


def banana() -> bool:
    return CONFIG.get("menu_shape", "banana") == "banana"


def frame() -> tuple[int, int, QPointF]:
    """Window width, height and hub centre (where the cursor is) for the current shape."""
    if banana():
        return BANANA_W, BANANA_H, QPointF(BANANA_W / 2, BANANA_HUB_Y)
    return SIZE, SIZE, QPointF(SIZE / 2, SIZE / 2)


def gap_deg() -> float:
    return BANANA_GAP if banana() else GAP_DEG


def label_room(a0: float, a1: float, r0: float, r1: float, line: float = 16, pad: float = 8) -> float:
    """Width a horizontal label of height `line` can take in the middle of a petal. A petal is
    about a box of `chord` along its curve by `r1 - r0` across, turned to its angle; a tilted
    box leaves less horizontal room than its width (the banana's tips are tilted)."""
    r = (r0 + r1) / 2
    chord = 2 * r * math.sin(math.radians(a1 - a0) / 2)
    m = math.radians((a0 + a1) / 2)
    along, across = abs(math.sin(m)), abs(math.cos(m))   # how horizontal the curve/thickness run
    fits = []
    if along > 1e-3:
        fits.append((chord - line * across) / along)
    if across > 1e-3:
        fits.append((r1 - r0 - line * along) / across)
    return max(24.0, min(fits) - pad)


def petal(n: int, i: int) -> tuple[QPointF, float, float, float, float]:
    """(centre, a0, a1, r0, r1) of petal i of n: an annular sector around `centre`, angles in
    degrees (Qt: 0 = 3 o'clock, CCW), radii in px."""
    hub = frame()[2]
    if not banana():
        a0, a1 = angles(n, i)
        return hub, a0, a1, R_IN, R_OUT
    centre = QPointF(hub.x(), hub.y() + R_HUB + 16 - BANANA_R0)   # band starts just under the hub
    span = BANANA_ARC / n
    a0 = 270 - BANANA_ARC / 2 + i * span       # left to right, under the hub
    t = (i + 0.5) / n                           # 0..1 along the banana
    thick = BANANA_THICK * (BANANA_TIP + (1 - BANANA_TIP) * math.sin(math.pi * t))
    return centre, a0 + BANANA_GAP / 2, a0 + span - BANANA_GAP / 2, BANANA_R0, BANANA_R0 + thick


# ---------------------------------------------------------------- background render
class _RenderSig(QObject):
    done = Signal(int, int, QImage, bool)   # serial, petal count, image, is_light


class _RenderJob(QRunnable):
    def __init__(self, serial: int, n: int, backdrop):
        super().__init__()
        self.serial, self.n, self.backdrop = serial, n, backdrop
        self.sig = _RenderSig()

    def run(self):
        try:
            from . import liquid
            w, h, hub = frame()
            fields = [liquid.sdf_circle(w, h, hub.x(), hub.y(), R_HUB)]
            for i in range(self.n):
                pc, a0, a1, r0, r1 = petal(self.n, i)
                fields.append(liquid.sdf_ring_sector(w, h, pc.x(), pc.y(), r0, r1, a0, a1,
                                                     BANANA_CORNER if banana() else CORNER))
            sdf = liquid.union(*fields)
            img, light = liquid.render(self.backdrop, sdf, liquid.GlassStyle())
            sh = liquid.shadow(sdf, spread=26, opacity=0.42 if light else 0.30, offset=(0, 8))
            sh.alpha_composite(img)
            try:
                self.sig.done.emit(self.serial, self.n, glass.qimage_from_pil(sh), light)
            except RuntimeError:
                pass
        except Exception:  # pragma: no cover - fall back to the painted glass
            import traceback
            traceback.print_exc()


class RadialMenu(QWidget):
    activated = Signal(object, list)     # Item, paths
    dismissed = Signal()

    def __init__(self, build_rings: Callable[[list[str]], dict[str, list[Item]]],
                 describe: Callable[[list[str]], str]):
        super().__init__(None)
        self.build_rings = build_rings
        self.describe = describe
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint |
                            Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.resize(*frame()[:2])

        self.paths: list[str] = []
        self.rings: dict[str, list[Item]] = {}
        self.ring_names: list[str] = []
        self.ring_idx = 0
        self.hover = -1          # petal index, -2 = hub, -1 = none
        self.cursor_pos = frame()[2]
        self.hub_text = ""
        self.backdrop: QPixmap | None = None     # blurred, for the instant fallback
        self._raw_backdrop = None                 # PIL image for the liquid renderer
        self.liquid: dict[int, QImage] = {}       # petal count -> rendered glass
        self.is_light = False
        self._serial = 0
        self.got_drag = False
        self.hub_armed = False
        self.click_mode = False  # opened from tray/menu instead of a drag
        self._t = 1.0            # pop-in animation 0..1
        self._swap = 1.0         # ring-swap animation 0..1
        self.spring: list[float] = []   # per-petal hover amount 0..1 (eased every frame)
        self.hub_spring = 0.0

        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=190,
                                      easingCurve=QEasingCurve.OutBack)
        self.anim.valueChanged.connect(self._set_t)
        self.swap_anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=220,
                                           easingCurve=QEasingCurve.OutCubic)
        self.swap_anim.valueChanged.connect(self._set_swap)
        self.hub_timer = QTimer(self, singleShot=True, interval=420, timeout=self.next_ring)
        self.frame = QTimer(self, interval=16, timeout=self._tick)   # 60 fps springs

    # ------------------------------------------------------------ show / hide
    def popup(self, pos: QPoint | None = None, paths: list[str] | None = None):
        pos = pos or QCursor.pos()
        w, h, hub = frame()
        self.resize(w, h)
        tl = pos - QPoint(round(hub.x()), round(hub.y()))
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        tl.setX(min(max(tl.x(), g.left()), g.right() - w))
        tl.setY(min(max(tl.y(), g.top()), g.bottom() - h))
        # snapshot what's underneath *before* we appear
        self._serial += 1
        self.liquid = {}
        try:
            if sys.platform == "darwin":
                # macOS captures "below the drag window": the drag picture never gets in
                raw = glass.grab_screen(tl.x(), tl.y(), w, h)
                if raw is None:
                    raise RuntimeError("capture failed")
                from . import platform_mac
                print("menu: mac windows at cursor:", "; ".join(platform_mac.LAST_SWEEP), flush=True)
                if self.got_drag or paths is None:
                    # belt and braces: Finder's drag picture (icon + name label) sits on the
                    # cursor; erase that area — it ends up under the hub, blurred anyway
                    cx, cy = pos.x() - tl.x(), pos.y() - tl.y()
                    raw = glass.inpaint_rects(raw, [(cx - 70, cy - 64, cx + 70, cy + 64)])
                shot = QPixmap.fromImage(glass.qimage_from_pil(raw))
            else:
                with glass.hidden_drag_images() as hid:
                    shot = scr.grabWindow(0, tl.x() - g.left(), tl.y() - g.top(), w, h)
                if hid.hwnds:
                    print(f"menu: hid {len(hid.hwnds)} drag image(s) during capture: {'; '.join(hid.info)}", flush=True)
                elif hid.info:
                    print(f"menu: drag-image sweep: {'; '.join(hid.info)}", flush=True)
                raw = glass.pil_from_qimage(
                    shot.toImage().scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                if sys.platform.startswith("linux") and paths is None:
                    # X11 drag icons (Thunar/GTK) sit on the cursor: erase that patch
                    cx, cy = pos.x() - tl.x(), pos.y() - tl.y()
                    hid.rects = [(pos.x() - 60, pos.y() - 60, pos.x() + 60, pos.y() + 60)]
                if hid.rects:
                    # belt and braces: erase where the drag picture was, in case it was captured anyway
                    k = w / max(1, shot.width())
                    local = [(int((x0 - tl.x()) * k), int((y0 - tl.y()) * k), int((x1 - tl.x()) * k), int((y1 - tl.y()) * k))
                             for (x0, y0, x1, y1) in hid.rects]
                    raw = glass.inpaint_rects(raw, local)
                    shot = QPixmap.fromImage(glass.qimage_from_pil(raw))
            self._raw_backdrop = raw
            self.backdrop = glass.blur_pixmap(shot, 24)
        except Exception:
            self.backdrop = None
            self._raw_backdrop = None
        self.move(tl)
        self.hover = -1
        self.got_drag = False
        self.hub_armed = False  # drags start on the hub; don't flip until they leave it
        self.click_mode = paths is not None
        if paths is not None:
            self._load(paths)
        else:
            self.paths, self.rings, self.ring_names = [], {}, []
            self.hub_text = tr("Drop here")
            for n in (4, 7):  # most common rings: render speculatively
                self._render(n)
        self._t = 0.0
        self._shape()
        self.show()
        self.raise_()
        self.anim.start()
        self.frame.start()
        if self.click_mode:
            # behave like a popup: a click anywhere outside dismisses it
            QTimer.singleShot(0, self.grabMouse)

    def close_menu(self):
        if self.isVisible():
            self.hide()
            self.frame.stop()
            self.hub_timer.stop()
            self.dismissed.emit()

    def hideEvent(self, e):
        self.frame.stop()
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        super().hideEvent(e)

    def _render(self, n: int):
        if n <= 0 or n in self.liquid or self._raw_backdrop is None:
            return
        self.liquid[n] = QImage()  # placeholder: in flight
        job = _RenderJob(self._serial, n, self._raw_backdrop)
        from .util import keep, release
        job.sig.done.connect(lambda *a, j=job: (release(j), self._rendered(*a)))
        QThreadPool.globalInstance().start(keep(job))

    def _rendered(self, serial: int, n: int, img: QImage, light: bool):
        if serial == self._serial:
            self.liquid[n] = img
            self.is_light = light
            self.update()

    def _load(self, paths: list[str]):
        self.paths = paths
        self.rings = {k: v for k, v in self.build_rings(paths).items() if v}
        self.ring_names = list(self.rings)
        self.ring_idx = 0
        self.hub_text = self.describe(paths)
        for items in self.rings.values():
            self._render(len(items))
        self.spring = [0.0] * len(self.items)
        self._shape()
        self.update()

    def _shape(self):
        """No compositor (XFCE etc.): cut the window to the menu's outline."""
        if not glass.no_compositor():
            return
        c = frame()[2]
        path = QPainterPath()
        path.addEllipse(c, R_HUB + 2, R_HUB + 2)
        n = len(self.items) or (7 if banana() else 0)
        if n:
            for i in range(n):
                pc, a0, a1, r0, r1 = petal(n, i)
                path = path.united(sector_path(pc, r0 - 2, r1 + 14, a0 - 1, a1 + 1))
        else:
            outer = QPainterPath()
            outer.addEllipse(c, R_OUT + 14, R_OUT + 14)
            path = path.united(outer)       # united, not added: odd-even fill would punch a hole
        glass.apply_shape(self, path)

    def next_ring(self):
        if len(self.ring_names) > 1:
            self.ring_idx = (self.ring_idx + 1) % len(self.ring_names)
            self.hover = -1
            self.spring = [0.0] * len(self.items)
            self._swap = 0.0
            self.swap_anim.start()
            self._shape()
            self.update()

    def _set_t(self, v):
        self._t = float(v)
        self.update()

    def _set_swap(self, v):
        self._swap = float(v)
        self.update()

    def _tick(self):
        moved = False
        for i in range(len(self.spring)):
            target = 1.0 if i == self.hover else 0.0
            v = self.spring[i]
            nv = v + (target - v) * 0.32
            if abs(nv - target) < 0.003:
                nv = target
            if nv != v:
                self.spring[i] = nv
                moved = True
        ht = 1.0 if self.hover == -2 else 0.0
        nh = self.hub_spring + (ht - self.hub_spring) * 0.3
        if abs(nh - ht) < 0.003:
            nh = ht
        if nh != self.hub_spring:
            self.hub_spring = nh
            moved = True
        if moved:
            self.update()

    # ------------------------------------------------------------ geometry
    @property
    def items(self) -> list[Item]:
        if not self.ring_names:
            return []
        return self.rings[self.ring_names[self.ring_idx]]

    def _angles(self, n: int, i: int) -> tuple[float, float]:
        return angles(n, i)

    def hit(self, pos: QPointF) -> int:
        c = frame()[2]
        if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= R_HUB + 4:
            return -2
        if not self.items:
            return -1
        n, gap = len(self.items), gap_deg()
        for i in range(n):
            pc, a0, a1, r0, r1 = petal(n, i)
            dx, dy = pos.x() - pc.x(), pc.y() - pos.y()
            d, ang = math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))
            lo = r0 - 20 if banana() else 0      # banana: nothing between the band and its far centre
            # half the gap on each side belongs to the petal, so there are no dead lines
            if (ang - (a0 - gap / 2)) % 360 <= (a1 - a0) + gap and lo <= d <= r1 + 30:
                return i
        return -1

    def _set_hover(self, h: int, pos: QPointF | None = None):
        if pos is not None:
            self.cursor_pos = QPointF(pos)
        if h != self.hover:
            self.hover = h
            if h >= 0:
                self.hub_armed = True  # visited a petal: hovering the hub may now flip rings
            if h == -2 and self.hub_armed and len(self.ring_names) > 1:
                self.hub_timer.start()
            else:
                self.hub_timer.stop()
        self.update()

    # ------------------------------------------------------------ drag & drop
    @staticmethod
    def _local_paths(md) -> list[str]:
        if not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, e):
        paths = self._local_paths(e.mimeData())
        if not paths:
            e.ignore()
            return
        self.got_drag = True
        if paths != self.paths:
            self._load(paths)
        e.setDropAction(Qt.CopyAction)  # never let a Shift(=move) drop delete the source
        e.accept()

    def dragMoveEvent(self, e):
        self._set_hover(self.hit(e.position()), e.position())
        e.setDropAction(Qt.CopyAction)
        e.accept()

    def dragLeaveEvent(self, e):
        self._set_hover(-1)

    def dropEvent(self, e):
        idx = self.hit(e.position())
        items = self.items
        if 0 <= idx < len(items):
            e.setDropAction(Qt.CopyAction)
            e.accept()
            item, paths = items[idx], list(self.paths)
            self.hide()
            # return to Explorer's drag loop immediately; do the work after
            QTimer.singleShot(0, lambda: self.activated.emit(item, paths))
        else:
            e.ignore()
            self.close_menu()

    # ------------------------------------------------------------ click mode
    def mouseMoveEvent(self, e):
        if self.click_mode:
            self._set_hover(self.hit(e.position()), e.position())

    def mouseReleaseEvent(self, e):
        if not self.click_mode:
            return
        if e.button() == Qt.RightButton:
            self.close_menu()
            return
        idx = self.hit(e.position())
        if idx == -2:
            self.next_ring()
        elif 0 <= idx < len(self.items):
            item, paths = self.items[idx], list(self.paths)
            self.hide()
            QTimer.singleShot(0, lambda: self.activated.emit(item, paths))
        else:
            self.close_menu()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_menu()
        elif e.key() in (Qt.Key_Tab, Qt.Key_Shift):
            self.next_ring()

    def leaveEvent(self, e):
        if self.click_mode:
            self._set_hover(-1)

    # ------------------------------------------------------------ painting
    def _text_colors(self) -> tuple[QColor, QColor, QColor]:
        if self.is_light:
            return QColor(28, 20, 44), QColor(28, 20, 44, 170), QColor(255, 255, 255, 120)
        return QColor(255, 255, 255), QColor(255, 255, 255, 190), QColor(0, 0, 0, 110)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = frame()[2]
        t = self._t
        p.setOpacity(min(1.0, max(0.0, t * 1.5)))
        p.translate(c)
        s = 0.80 + 0.20 * t
        p.scale(s, s)
        p.translate(-c)

        items = self.items
        n = len(items)
        img = self.liquid.get(n) if n else (self.liquid.get(4) or self.liquid.get(7))
        have_liquid = img is not None and not img.isNull()

        if have_liquid:
            p.drawImage(0, 0, img)
        else:
            self._paint_fallback(p, c, n)

        fg, fg_dim, shadow_col = self._text_colors()
        rot = (1 - self._swap) * (-6 if banana() else -22)
        if n and banana():
            self._paint_banana_end(p, n)
        for i, it in enumerate(items):
            pc, a0, a1, r0, r1 = petal(n, i)
            h = self.spring[i] if i < len(self.spring) else 0.0
            if h > 0.001:
                self._paint_hover(p, pc, a0, a1, r0, r1, h, img if have_liquid else None)
            r = (r0 + r1) / 2
            self._petal_label(p, pc, it, (a0 + a1) / 2 + rot, r + h * 4, h, fg, shadow_col,
                              label_room(a0, a1, r0, r1))

        self._paint_hub(p, c, fg, fg_dim, shadow_col)

    def _paint_fallback(self, p: QPainter, c: QPointF, n: int):
        hub = QPainterPath()
        hub.addEllipse(c, R_HUB, R_HUB)
        glass.paint_glass(p, hub, self.backdrop, QPointF(0, 0), tint=QColor(22, 18, 34, 80),
                          rainbow_alpha=150, highlight=1.3)
        for i in range(n):
            pc, a0, a1, r0, r1 = petal(n, i)
            glass.paint_glass(p, sector_path(pc, r0, r1, a0, a1), self.backdrop, QPointF(0, 0),
                              tint=QColor(22, 18, 34, 62), rainbow_alpha=140)

    def _paint_banana_end(self, p: QPainter, n: int):
        """The dark end of the banana, on the right tip."""
        c, _, a1, r0, r1 = petal(n, n - 1)
        a = math.radians(a1)
        r = (r0 + r1) / 2
        end = QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))
        g = QRadialGradient(end, (r1 - r0) * 0.55)
        g.setColorAt(0.0, QColor(80, 52, 18, 200))
        g.setColorAt(1.0, QColor(80, 52, 18, 0))
        p.fillPath(sector_path(c, r0, r1, a1 - 6, a1), g)

    def _paint_hover(self, p: QPainter, c: QPointF, a0: float, a1: float, r0: float, r1: float,
                     h: float, img: QImage | None):
        mid = math.radians((a0 + a1) / 2)
        r_mid = (r0 + r1) / 2
        pc = QPointF(c.x() + r_mid * math.cos(mid), c.y() - r_mid * math.sin(mid))
        k = 1 + 0.07 * h                     # elastic "pop" towards the cursor
        push = 6 * h
        off = QPointF(push * math.cos(mid), -push * math.sin(mid))
        path = sector_path(c, r0 - 1, r1 + 1, a0, a1)
        p.save()
        p.translate(pc + off)
        p.scale(k, k)
        p.translate(-pc)
        if img is not None:
            p.save()
            p.setClipPath(path)
            p.drawImage(0, 0, img)
            p.restore()
        # light blooming up from underneath the cursor
        glow_c = self.cursor_pos - off
        g = QRadialGradient(glow_c, 120)
        g.setColorAt(0.0, QColor(255, 236, 130, int(150 * h)))
        g.setColorAt(0.45, QColor(255, 190, 40, int(95 * h)))
        g.setColorAt(1.0, QColor(130, 100, 255, int(40 * h)))
        p.fillPath(path, g)
        # brighter specular rim + iridescent edge while hovered
        p.setPen(QPen(QColor(255, 255, 255, int(170 * h)), 1.3))
        p.drawPath(path)
        p.setPen(glass.iridescent_pen(c, 2.2, int(230 * h), angle=(a0 + a1) / 2))
        p.drawPath(path)
        p.restore()

    def _paint_hub(self, p: QPainter, c: QPointF, fg: QColor, fg_dim: QColor, shadow_col: QColor):
        hs = self.hub_spring
        if hs > 0.001:
            g = QRadialGradient(c, R_HUB)
            g.setColorAt(0, QColor(255, 255, 255, int(70 * hs)))
            g.setColorAt(1, QColor(255, 255, 255, int(20 * hs)))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, R_HUB, R_HUB)
        p.setPen(glass.iridescent_pen(c, 1.2, 150, angle=60))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R_HUB - 0.5, R_HUB - 0.5)

        items = self.items
        hov = items[self.hover] if 0 <= self.hover < len(items) else None
        if hov is not None:
            top, sub = hov.label if not hov.glyph else hov.label.title(), hov.hint or ""
        else:
            ring_name = self.ring_names[self.ring_idx] if self.ring_names else ""
            top = self.hub_text
            if len(self.ring_names) > 1:
                other = self.ring_names[(self.ring_idx + 1) % len(self.ring_names)]
                sub = f"⇧ {other.upper()}"
            else:
                sub = ring_name.upper()
        f = QFont("Segoe UI Variable Display", 1)
        f.setPixelSize(14)
        f.setBold(True)
        p.setFont(f)
        rect_top = QRectF(c.x() - R_HUB + 4, c.y() - 21, 2 * R_HUB - 8, 20)
        self._text(p, rect_top, top, fg, shadow_col)
        f.setPixelSize(10)
        f.setBold(False)
        p.setFont(f)
        self._text(p, QRectF(c.x() - R_HUB + 6, c.y() + 2, 2 * R_HUB - 12, 28), sub, fg_dim, None,
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap)

    @staticmethod
    def _text(p: QPainter, r: QRectF, text: str, col: QColor, shadow: QColor | None,
              flags=Qt.AlignCenter):
        if shadow is not None:
            p.setPen(shadow)
            p.drawText(r.translated(0, 1), flags, text)
        p.setPen(col)
        p.drawText(r, flags, text)

    @staticmethod
    def _fit_font(f: QFont, px: int, text: str, room: float) -> QFont:
        """Largest size up to `px` (down to 8) at which `text` fits in `room` px."""
        while px > 8:
            f.setPixelSize(px)
            if QFontMetrics(f).horizontalAdvance(text) <= room:
                break
            px -= 1
        f.setPixelSize(px)
        return f

    def _petal_label(self, p: QPainter, c: QPointF, it: Item, ang: float, r: float,
                     h: float, fg: QColor, shadow_col: QColor, room: float = 84):
        rad = math.radians(ang)
        push = 6 * h
        pt = QPointF(c.x() + (r + push) * math.cos(rad), c.y() - (r + push) * math.sin(rad))
        p.save()
        p.setOpacity(p.opacity() * (0.25 + 0.75 * self._swap))
        col = QColor(255, 255, 255) if h > 0.5 else fg   # hovered petal is warm-lit: white text
        f = QFont("Segoe UI Variable Display", 1)
        if it.glyph:
            f.setPixelSize(int(18 + 3 * h))
            p.setFont(f)
            self._text(p, QRectF(pt.x() - 30, pt.y() - 24, 60, 24), it.glyph, col, shadow_col,
                       Qt.AlignHCenter | Qt.AlignBottom)
            f.setBold(True)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.7)
            p.setFont(self._fit_font(f, 10, it.label.upper(), room))
            w = max(84.0, room)
            self._text(p, QRectF(pt.x() - w / 2, pt.y() + 1, w, 16), it.label.upper(), col, shadow_col)
        else:
            f.setBold(True)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.9)
            p.setFont(self._fit_font(f, int(14 + 2 * h), it.label, room))
            w = max(84.0, room)
            self._text(p, QRectF(pt.x() - w / 2, pt.y() - 12, w, 24), it.label, col, shadow_col)
        p.restore()
