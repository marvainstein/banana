"""PDF → EPUB (and MOBI/AZW3 through Calibre): the book is valid, running heads and page numbers
are gone, split words and paragraphs are joined, chapters come from bookmarks or headings."""
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree

import pytest
from PIL import Image

from banana import convert, ebook
from banana.util import UserError

TITLE = "Banana Book"
LINES = [  # one paragraph per chapter, set line by line so the hyphen and the page break are exact
    "Aquella mañana Tomás salió temprano hacia el mercado, convencido de que",
    "encontraría las bananas más amarillas de toda la ciudad. Las calles estaban",
    "húmedas por la lluvia de la noche anterior y el aire olía a pan recién hor-",
    "neado. En la esquina, un viejo vendedor acomodaba sus cajones con una",
]


def write_book(path, bookmarks=True, chapters=3):
    doc = convert.fitz.open()
    pic = io.BytesIO()
    Image.new("RGB", (300, 200), (240, 200, 40)).save(pic, "PNG")
    toc = []
    for c in range(1, chapters + 1):
        page = doc.new_page(width=420, height=595)
        toc.append([1, f"Capítulo {c}", doc.page_count])
        page.insert_text((50, 110), f"Capítulo {c}", fontsize=22)
        y = 160
        for _ in range(5):
            for ln in LINES:
                page.insert_text((50, y), ln, fontsize=10)
                y += 13
            y += 8
        if c == 2:
            page.insert_image(convert.fitz.Rect(100, y, 300, y + 130), stream=pic.getvalue())
        # the last paragraph of the chapter breaks over to the next page mid-sentence
        page.insert_text((50, 520), "Y entonces, cuando nadie lo esperaba, el vendedor se dio vuelta", fontsize=10)
        nxt = doc.new_page(width=420, height=595)
        nxt.insert_text((50, 80), "y le regaló la banana más grande del cajón.", fontsize=10)
        y = 110
        for _ in range(4):
            for ln in LINES:
                nxt.insert_text((50, y), ln, fontsize=10)
                y += 13
            y += 8
    for pno, page in enumerate(doc):   # running head (small, top) and folio (bottom) on every page
        page.insert_text((50, 30), TITLE, fontsize=8)
        page.insert_text((205, 575), str(pno + 1), fontsize=8)
    if bookmarks:
        doc.set_toc(toc)
    doc.set_metadata({"title": TITLE, "author": "Jimmy"})
    doc.save(path)
    return path


def contents(epub):
    with zipfile.ZipFile(epub) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        files = {n: z.read(n) for n in z.namelist()}
    for n, data in files.items():
        if n.endswith((".xhtml", ".opf", ".xml")):
            ElementTree.fromstring(data)   # well-formed XML, or readers refuse the book
    text = "".join(files[n].decode() for n in sorted(files) if "/text/" in n)
    return files, text


def test_epub_from_a_book_with_bookmarks(tmp_path):
    epub = convert.convert(write_book(tmp_path / "Libro.pdf"), "pdf", "EPUB")[0]
    assert epub.name == "Libro.epub"
    files, text = contents(epub)
    opf = files["OEBPS/content.opf"].decode()
    assert f"<dc:title>{TITLE}</dc:title>" in opf and "<dc:creator>Jimmy</dc:creator>" in opf
    assert "<dc:language>es</dc:language>" in opf and 'properties="cover-image"' in opf
    nav = files["OEBPS/nav.xhtml"].decode()
    assert re.findall(r">(Capítulo \d)</a>", nav) == ["Capítulo 1", "Capítulo 2", "Capítulo 3"]
    assert len([n for n in files if "/text/" in n]) == 3          # one file per chapter
    assert TITLE not in text                                       # running head dropped
    assert not re.search(r"<p>\d+</p>", text)                      # folios dropped
    assert "recién horneado" in text and "hor-" not in text        # hyphenated word joined
    assert "se dio vuelta y le regaló la banana" in text           # paragraph joined over the page
    assert text.count("<h") >= 3 and "<h1>Capítulo 1</h1>" in text
    assert any(n.startswith("OEBPS/images/img") for n in files)    # the picture in chapter 2


def test_epub_chapters_from_headings(tmp_path):
    epub = convert.convert(write_book(tmp_path / "b.pdf", bookmarks=False), "pdf", "EPUB")[0]
    files, _ = contents(epub)
    nav = files["OEBPS/nav.xhtml"].decode()
    assert re.findall(r">(Capítulo \d)</a>", nav) == ["Capítulo 1", "Capítulo 2", "Capítulo 3"]


def test_scanned_pdf_is_refused(tmp_path):
    doc = convert.fitz.open()
    for _ in range(3):
        page = doc.new_page()
        pic = io.BytesIO()
        Image.new("RGB", (600, 800), (250, 250, 245)).save(pic, "JPEG")
        page.insert_image(page.rect, stream=pic.getvalue())
    doc.save(tmp_path / "scan.pdf")
    with pytest.raises(UserError, match="OCR"):
        convert.convert(tmp_path / "scan.pdf", "pdf", "EPUB")
    assert not list(tmp_path.glob("*.epub"))


def test_hyphen_joining():
    segs = [("una palabra cor-", 0)]
    ebook._append_line(segs, [("tada al final", 0)])
    assert "".join(t for t, _ in segs) == "una palabra cortada al final"
    segs = [("estándar IEEE-", 0)]
    ebook._append_line(segs, [("754 de", 0)])
    assert "".join(t for t, _ in segs) == "estándar IEEE-754 de"
    segs = [("fin de línea", 0)]
    ebook._append_line(segs, [("siguiente", 0)])
    assert "".join(t for t, _ in segs) == "fin de línea siguiente"


def test_kindle_formats_need_calibre(tmp_path, monkeypatch):
    pdf = write_book(tmp_path / "k.pdf", chapters=1)
    monkeypatch.setattr(ebook, "calibre_cmd", lambda: None)
    targets = convert.targets_for("pdf", ".pdf")
    assert "EPUB" in targets and "MOBI" in targets and "AZW3" not in targets
    with pytest.raises(UserError, match="Calibre"):
        convert.convert(pdf, "pdf", "MOBI")

    fake = tmp_path / "fake_ebook_convert.py"   # stands in for Calibre: checks the EPUB, copies it
    fake.write_text("import sys, shutil, zipfile\nzipfile.ZipFile(sys.argv[1]).testzip()\n"
                    "shutil.copy(sys.argv[1], sys.argv[2])\n")
    monkeypatch.setattr(ebook, "calibre_cmd", lambda: [sys.executable, str(fake)])
    assert "AZW3" in convert.targets_for("pdf", ".pdf")
    for fmt in ("MOBI", "AZW3"):
        out = convert.convert(pdf, "pdf", fmt)[0]
        assert out.suffix == "." + fmt.lower() and zipfile.is_zipfile(out)


def _epubcheck():
    jar = os.environ.get("EPUBCHECK_JAR")
    if jar and os.path.exists(jar) and shutil.which("java"):
        return ["java", "-jar", jar]
    return [shutil.which("epubcheck")] if shutil.which("epubcheck") else None


@pytest.mark.skipif(not _epubcheck(), reason="epubcheck not installed (set EPUBCHECK_JAR)")
def test_epubcheck_accepts_the_book(tmp_path):
    epub = convert.convert(write_book(tmp_path / "v.pdf"), "pdf", "EPUB")[0]
    r = subprocess.run([*_epubcheck(), str(epub)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not re.search(r"^(ERROR|WARNING)", r.stdout + r.stderr, re.M), r.stdout + r.stderr


def test_drop_cap_joins_its_paragraph_but_a_lone_letter_stays_a_heading(tmp_path):
    doc = convert.fitz.open()
    page = doc.new_page(width=420, height=595)
    page.insert_text((50, 90), "I", fontsize=30)                    # "Part I" style heading
    page.insert_text((50, 160), "A", fontsize=30)                   # drop cap beside its paragraph
    page.insert_text((75, 140), "quella mañana Tomás salió temprano hacia el mercado.", fontsize=10)
    for k in range(6):
        page.insert_text((50, 200 + 13 * k), "Las calles estaban húmedas por la lluvia de anoche.", fontsize=10)
    doc.save(tmp_path / "d.pdf")
    _, text = contents(convert.convert(tmp_path / "d.pdf", "pdf", "EPUB")[0])
    assert ">I</h" in text and "Aquella mañana" in text
