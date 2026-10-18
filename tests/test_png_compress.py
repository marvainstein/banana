"""Lossy PNG compression: photos get a dithered median-cut palette, graphics stay crisp,
transparency survives."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from dragshift import imaging


def photo_like(size=(800, 500)) -> Image.Image:
    """Smooth gradients + sensor-like noise: where a palette bands."""
    rng = np.random.default_rng(0)
    w, h = size
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    rgb = np.stack([0.3 + 0.5 * x + 0 * y, 0.2 * x + 0.5 * y, 0.8 - 0.4 * y + 0 * x], 2)
    rgb += rng.normal(0, 0.03, rgb.shape)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype("uint8"))


def screenshot_like(size=(800, 500)) -> Image.Image:
    im = Image.new("RGB", size, (246, 246, 248))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, size[0], 40), fill=(230, 230, 235))
    for i in range(15):
        d.text((20, 60 + i * 26), f"Settings item {i}: lorem ipsum dolor sit amet", fill=(30, 30, 30))
    d.rounded_rectangle((500, 80, 760, 200), 16, fill=(0, 122, 255))
    return im


def blurred_error(a: Image.Image, b: Image.Image) -> float:
    """RMS difference as seen from a normal distance (dither noise averages out)."""
    fa = np.asarray(a.convert("RGB").filter(ImageFilter.GaussianBlur(1.2)), float)
    fb = np.asarray(b.convert("RGB").filter(ImageFilter.GaussianBlur(1.2)), float)
    return float(np.sqrt(((fa - fb) ** 2).mean()))


def test_looks_like_photo():
    assert imaging.looks_like_photo(photo_like())
    assert not imaging.looks_like_photo(screenshot_like())


def test_photo_png_is_dithered_and_beats_octree():
    im = photo_like()
    q = imaging.quantize_png(im, 72)
    assert q.mode == "P"
    octree = im.convert("RGBA").quantize(184, method=Image.Quantize.FASTOCTREE)  # the old method
    assert blurred_error(im, q) < 0.7 * blurred_error(im, octree)


def test_graphic_png_stays_exact():
    im = screenshot_like()   # far fewer than 256 colours: nothing to lose, no dither noise
    q = imaging.quantize_png(im, 72)
    assert np.array_equal(np.asarray(q.convert("RGB")), np.asarray(im))


def test_png_keeps_transparency(tmp_path):
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((50, 20, 250, 180), fill=(255, 90, 60, 255))
    src = tmp_path / "logo.png"
    im.save(src)
    out = imaging.compress_to(src, 60, None, "PNG")
    back = Image.open(out).convert("RGBA")
    assert back.getpixel((5, 5))[3] == 0 and back.getpixel((150, 100))[3] == 255


def test_photo_png_compresses_and_preview_palette(tmp_path):
    im = photo_like()
    src = tmp_path / "photo.png"
    im.save(src)
    out = imaging.compress_to(src, 72, None, "PNG")
    assert out.suffix == ".png" and out.stat().st_size < src.stat().st_size
    small = im.copy()
    small.thumbnail((240, 240))
    crop = imaging.quantize_png(im.crop((0, 0, 270, 170)), 72, True, palette_from=small)
    assert crop.mode == "P" and crop.size == (270, 170)
