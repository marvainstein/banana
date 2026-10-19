"""macOS: without the Screen Recording permission Banana must never call a screen-capture
API, because that pops up the system's permission prompt. The glass uses the wallpaper."""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


def test_no_capture_without_permission(monkeypatch):
    from PIL import Image
    from banana import glass, platform_mac

    def forbidden(*a, **k):
        raise AssertionError("captured the screen without permission (would prompt)")

    monkeypatch.setattr(platform_mac, "has_screen_recording", lambda: False)
    monkeypatch.setattr(platform_mac, "capture", forbidden)
    monkeypatch.setattr(platform_mac, "wallpaper", lambda x, y, w, h: Image.new("RGB", (w, h)))
    im = glass.grab_screen(10, 20, 300, 200)
    assert im.size == (300, 200)


def test_capture_once_allowed(monkeypatch):
    from PIL import Image
    from banana import glass, platform_mac

    monkeypatch.setattr(platform_mac, "has_screen_recording", lambda: True)
    monkeypatch.setattr(platform_mac, "capture", lambda x, y, w, h, below=0: Image.new("RGB", (w, h), "red"))
    assert glass.grab_screen(0, 0, 40, 30).getpixel((0, 0)) == (255, 0, 0)
