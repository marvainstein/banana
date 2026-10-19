"""Interface language: every string the code translates has a Spanish entry with the same
placeholders, and switching to Spanish reaches menus, summaries and output file names."""
import ast
import re
import string
from pathlib import Path

import pytest
from PIL import Image

from banana import app, i18n, imaging, report, settings, tools

PKG = Path(app.__file__).parent


@pytest.fixture
def spanish():
    i18n.set_language("es")
    try:
        yield
    finally:
        i18n.set_language("en")


def keys_in_code() -> set[str]:
    """String literals passed to tr() / trn() / file_label() anywhere in the package."""
    keys = set()
    for path in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            args = {"tr": node.args[:1], "trn": node.args[1:3], "file_label": node.args[:1]}.get(node.func.id, [])
            for a in args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.add(("file:" if node.func.id == "file_label" else "") + a.value)
    return keys


def keys_from_tables() -> set[str]:
    """Strings that reach tr() through a variable."""
    keys = set(app.GLYPHS) | set(app.HINTS.values()) | set(app.FORMAT_HINTS.values())
    keys |= {n for n, _ in tools.PRESETS} | {n for n, _ in tools.CropWindow.RATIOS}
    keys |= set(tools.RedactWindow.MODES) | set(tools.AddBgWindow.ASPECTS)
    keys |= {n for _, n in tools.VideoCompressWindow.QUALITIES}
    keys |= {"Brightness", "Contrast", "Saturation", "Warmth", "Sharpness"}
    keys |= {"brightness", "contrast", "saturation", "warmth", "sharpness", "strong", "okay", "weak"}
    keys |= {"⇋ Flip", "⇵ Flip", "Original", "Compressed", "Recycle Bin", "Trash"}
    keys |= {"Cropped", "Resized", "Edited", "Cropped {n} images", "Resized {n} images", "Edited {n} images"}
    keys |= {"Compressing…", "Splitting…", "Rotating…", "Extracting images…"}
    keys |= {"Size", "Camera", "Taken", "Software", "Exposure", "Aperture", "Location",
             "title", "author", "creator", "producer", "Pages"}
    keys |= {label for _, label in settings.OUTPUTS + settings.DPIS + settings.MENU_SHAPES}
    keys |= {"{n} arrow", "{n} arrows", "{n} box", "{n} boxes", "{n} circle", "{n} circles",
             "{n} stroke", "{n} strokes", "{n} highlight", "{n} highlights", "{n} label", "{n} labels",
             "{n} step", "{n} steps", "{n} area blacked out", "{n} areas blacked out",
             "{n} area pixelated", "{n} areas pixelated", "{n} area blurred", "{n} areas blurred"}
    keys.add(i18n.LANGUAGES[0][1])
    return keys


def test_every_string_has_a_spanish_translation():
    keys = keys_in_code() | keys_from_tables()
    assert len(keys) > 150
    missing = sorted(k for k in keys if k not in i18n.ES and re.search("[A-Za-z]", k))   # "16:9" stays
    assert not missing, f"missing in i18n.ES: {missing}"


def test_translations_keep_placeholders():
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    bad = [k for k, v in i18n.ES.items() if fields(k.removeprefix("file:")) != fields(v)]
    assert not bad, f"placeholders differ: {bad}"
    assert not [k for k in i18n.ES if re.search(r"\s$", i18n.ES[k]) and not k.endswith(" ")]


def test_language_choice():
    i18n.set_language("auto")
    assert i18n.language() in ("en", "es")
    i18n.set_language("xx")
    assert i18n.language() == "en"
    assert i18n.tr("{n} files", n=2) == "2 files"
    assert i18n.trn(1, "{n} page", "{n} pages") == "1 page"


def test_spanish_menu_summary_and_file_names(tmp_path, spanish):
    src = tmp_path / "Foto.png"
    Image.effect_noise((300, 200), 60).convert("RGB").save(src)   # noise: JPG is smaller than PNG
    rings = app.BananaApp.build_rings(None, [str(src)])
    assert list(rings) == ["Convertir", "Herramientas"]
    assert "Comprimir" in [i.label for i in rings["Herramientas"]]
    assert {i.key for i in rings["Herramientas"]} >= {"tool:Compress", "tool:Crop"}   # keys stay English
    out = imaging.compress_to(src, 70, None, "JPG")
    assert out.name == "Foto comprimido.jpg"
    r = report.summarize("tool:Compress", [src], [out])
    assert r.title == "Comprimido" and "más chico" in r.good
    assert report.summarize("convert:JPG", [src], [out]).title == "PNG → JPG"
