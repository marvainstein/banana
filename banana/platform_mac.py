"""macOS integration (only imported on darwin).

* Trigger: NSEvent.pressedMouseButtons / modifierFlags give the *global* mouse and
  modifier state, with no Accessibility or Input Monitoring permission needed.
* Capture: CGWindowListCreateImage can capture "everything below window N", which keeps
  Finder's drag picture and our own windows out of the glass (live refresh like Windows'
  capture exclusion). It needs the Screen Recording permission and asking for it pops up a
  system prompt, so Banana only captures once the user has opted in (Settings → Enable
  full liquid glass). Until then the glass refracts the desktop picture, read straight
  from its file: no permission, no prompt.
* Start at login: a LaunchAgent plist.
"""
from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

try:
    import AppKit  # pyobjc-framework-Cocoa
    import Quartz  # pyobjc-framework-Quartz
    OK = True
except Exception:  # pragma: no cover
    OK = False

# NSEventModifierFlags
SHIFT, CONTROL, OPTION, COMMAND = 1 << 17, 1 << 18, 1 << 19, 1 << 20
KEY_FLAGS = {"shift": SHIFT, "ctrl": CONTROL, "alt": OPTION}


# ---------------------------------------------------------------- input state
def left_button_down() -> bool:
    return bool(OK and AppKit.NSEvent.pressedMouseButtons() & 1)


def key_down(name: str) -> bool:
    return bool(OK and AppKit.NSEvent.modifierFlags() & KEY_FLAGS.get(name, SHIFT))


def escape_down() -> bool:
    if not OK:
        return False
    try:
        return bool(Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState, 53))
    except Exception:
        return False


# ---------------------------------------------------------------- app behaviour
def become_accessory():
    """Menu-bar app: no Dock icon (the bundle also sets LSUIElement)."""
    if OK:
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)


def activate():
    """Bring our windows to the front (accessory apps aren't activated automatically)."""
    if OK:
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def window_number(widget) -> int:
    """CGWindowID of a Qt top-level widget (winId() is an NSView*)."""
    if not OK:
        return 0
    try:
        import objc
        view = objc.objc_object(c_void_p=int(widget.winId()))
        win = view.window()
        return int(win.windowNumber()) if win is not None else 0
    except Exception:
        return 0


# ---------------------------------------------------------------- screen capture
LAST_SWEEP: list[str] = []


def drag_window_ids(cursor: tuple[int, int] | None = None) -> list[int]:
    """The drag picture under the cursor: windows at the dragging level, or any small
    window of another app sitting right on the cursor above normal windows."""
    LAST_SWEEP.clear()
    if not OK:
        return []
    try:
        level = Quartz.CGWindowLevelForKey(Quartz.kCGDraggingWindowLevelKey)
        infos = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or []
        me = os.getpid()
        ids = []
        for i in infos:
            layer = int(i.get("kCGWindowLayer", 0))
            b = i.get("kCGWindowBounds", {}) or {}
            x, y, w, h = (float(b.get(k, 0)) for k in ("X", "Y", "Width", "Height"))
            near = cursor is not None and x - 40 <= cursor[0] <= x + w + 40 and y - 40 <= cursor[1] <= y + h + 40
            if near:
                LAST_SWEEP.append(f"{i.get('kCGWindowOwnerName')} layer={layer} {int(w)}x{int(h)}")
            if int(i.get("kCGWindowOwnerPID", 0)) == me:
                continue
            if layer >= level or (near and layer > 0 and w < 700 and h < 700):
                ids.append(int(i["kCGWindowNumber"]))
        return ids
    except Exception as e:
        LAST_SWEEP.append(f"error {e}")
        return []


def _to_pil(img):
    from PIL import Image
    width, height = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    bpr = Quartz.CGImageGetBytesPerRow(img)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
    return Image.frombuffer("RGBA", (width, height), bytes(data), "raw", "BGRA", bpr, 1).convert("RGB")


_WALLPAPER: dict = {}    # (file, screen w, h) -> PIL image the size of the screen, in points
_LOADING: set = set()


def _screen_wallpaper(cx: float, cy: float, wait: bool):
    """(desktop picture scaled to fill its screen, screen origin) for the screen at (cx, cy)."""
    for scr in AppKit.NSScreen.screens():
        did = int(scr.deviceDescription()["NSScreenNumber"])
        b = Quartz.CGDisplayBounds(did)          # global points, top-left origin
        bx, by, bw, bh = b.origin.x, b.origin.y, b.size.width, b.size.height
        if not (bx <= cx < bx + bw and by <= cy < by + bh):
            continue
        url = AppKit.NSWorkspace.sharedWorkspace().desktopImageURLForScreen_(scr)
        if url is None:
            return None, (bx, by)
        key = (str(url.path()), int(bw), int(bh))
        if key not in _WALLPAPER:
            if not wait:
                # decoding a big HEIC takes ~1 s: never on the UI thread; plain glass this time
                if key not in _LOADING:
                    _LOADING.add(key)
                    import threading
                    threading.Thread(target=_load_into, args=(key, url), daemon=True).start()
                return None, (bx, by)
            _load_into(key, url)
        return _WALLPAPER.get(key), (bx, by)
    return None, (0, 0)


def _load_into(key, url):
    try:
        _WALLPAPER[key] = _load_fill(url, key[1], key[2])
    except Exception:
        _WALLPAPER[key] = None
    _LOADING.discard(key)


def _load_fill(url, w: int, h: int):
    """Decode (HEIC too) at about screen size with ImageIO, then scale to fill w×h."""
    from PIL import Image
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return None
    opts = {Quartz.kCGImageSourceCreateThumbnailFromImageAlways: True,
            Quartz.kCGImageSourceCreateThumbnailWithTransform: True,
            Quartz.kCGImageSourceThumbnailMaxPixelSize: max(w, h)}   # the glass blurs it anyway
    img = Quartz.CGImageSourceCreateThumbnailAtIndex(src, 0, opts)
    if img is None:
        return None
    im = _to_pil(img)
    k = max(w / im.width, h / im.height)            # "fill screen", like the default setting
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.BILINEAR)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def wallpaper(x: int, y: int, w: int, h: int, wait: bool = False):
    """The desktop picture under a screen rect (global points) as a PIL RGB image of w×h, or
    None (not decoded yet, or e.g. an animated wallpaper). Needs no permission. Without
    `wait`, a picture not decoded yet loads in the background and this returns None."""
    if not OK:
        return None
    try:
        im, (bx, by) = _screen_wallpaper(x + w / 2, y + h / 2, wait)
    except Exception:
        return None
    if im is None:
        return None
    from PIL import Image
    out = Image.new("RGB", (w, h), (40, 40, 48))
    out.paste(im.crop((int(x - bx), int(y - by), int(x - bx) + w, int(y - by) + h)), (0, 0))
    return out


def capture(x: int, y: int, w: int, h: int, below_window: int = 0):
    """Capture a screen rect (global points, top-left origin) as a PIL RGB image.
    below_window: capture only what is beneath that window (excludes it and anything above)."""
    if not OK:
        return None
    from PIL import Image
    rect = Quartz.CGRectMake(x, y, w, h)
    if below_window:
        opt, wid = Quartz.kCGWindowListOptionOnScreenBelowWindow, below_window
    else:
        loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        drags = drag_window_ids((int(loc.x), int(loc.y)))
        if drags:
            # everything below the lowest drag window = no drag picture in the glass
            opt, wid = Quartz.kCGWindowListOptionOnScreenBelowWindow, min(drags)
        else:
            opt, wid = Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
    try:
        img = Quartz.CGWindowListCreateImage(rect, opt, wid, Quartz.kCGWindowImageBestResolution)
    except Exception:
        return None
    if img is None:
        return None
    return _to_pil(img).resize((w, h), Image.LANCZOS)


def has_screen_recording() -> bool:
    """Already granted? (CGPreflight… only checks; it never shows the system prompt.)"""
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def request_screen_recording() -> bool:
    try:
        return bool(Quartz.CGRequestScreenCaptureAccess())
    except Exception:
        return False


# ---------------------------------------------------------------- start at login
AGENT = Path.home() / "Library" / "LaunchAgents" / "com.marvainstein.banana.plist"


def _program() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--quiet"]
    return [sys.executable, "-m", "banana", "--quiet"]


def autostart_enabled() -> bool:
    return AGENT.exists()


def set_autostart(on: bool):
    if on:
        AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(AGENT, "wb") as f:
            plistlib.dump({"Label": "com.marvainstein.banana", "ProgramArguments": _program(),
                           "RunAtLoad": True, "ProcessType": "Interactive"}, f)
    elif AGENT.exists():
        AGENT.unlink()
