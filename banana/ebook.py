"""PDF → e-book. EPUB 3 is built here from the PDF's text, with no extra dependencies; MOBI and
AZW3 are made from that EPUB by Calibre's `ebook-convert` when Calibre is installed.

A PDF has fixed pages and an EPUB reflows, so the text is rebuilt rather than copied: running
headers, footers and page numbers are dropped, paragraphs cut by a page break or by a hyphen at
the end of a line are joined again, and headings are found by font size. Chapters come from the
PDF's bookmarks, or from the largest heading size that repeats when it has none. Pages without
text (a cover, a full-page figure) go in as pictures; a PDF that is all scans is refused."""
from __future__ import annotations

import datetime
import hashlib
import html
import io
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .convert import atomic_save, fitz, open_pdf
from .i18n import tr
from .util import UserError, progress, sibling

# ligatures expanded (so "ﬁ" reads and searches as "fi"), images kept in the dict output
FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_PRESERVE_IMAGES
BOLD, ITALIC = 1, 2
MARGIN = 0.1             # top/bottom share of the page where running headers and footers live
FOLIO_MARGIN = 0.2       # a bare page number can sit a little further in
FILE_PAGES = 30          # start another XHTML file after this many pages (readers like small files)
PAGE_NUMBER = re.compile(r"^[\s\-–—·|]*(?:page|p\.|pág\.?|página)?\s*(?:\d+|[ivxlcdm]+)"
                         r"(?:\s*(?:/|of|de)\s*\d+)?[\s\-–—·|]*$", re.I)
ENDS_SENTENCE = re.compile(r"[.!?…:;»\"”’)\]]\s*$")
NOT_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
STOPWORDS = {
    "es": "de la que el en los se del las por un para con una su al lo como más",
    "en": "the and of to in is that for it with as was on be by this are from",
    "pt": "de que não uma para com os no se na do da em as por mais",
    "fr": "le la les des est et que une pour dans du en qui pas sur au",
    "de": "der die und das ist nicht mit sich des ein den zu von auf",
    "it": "di che il la per non una sono del della gli in è le con",
}


# ---------------------------------------------------------------- extraction
@dataclass
class Block:
    page: int
    y0: float
    y1: float
    lines: list = field(default_factory=list)   # per line: [(text, style)]
    size: float = 0.0                            # font size covering most of the characters
    image: bytes | None = None                   # set for picture blocks

    @property
    def text(self) -> str:
        return " ".join("".join(t for t, _ in ln) for ln in self.lines).strip()

    @property
    def all_bold(self) -> bool:
        return all(st & BOLD for ln in self.lines for t, st in ln if t.strip())


def _style(span) -> int:
    font = span.get("font", "").lower()
    st = BOLD if span["flags"] & 16 or any(w in font for w in ("bold", "black", "heavy")) else 0
    return st | (ITALIC if span["flags"] & 2 or "italic" in font or "oblique" in font else 0)


def _blocks(page, pno: int) -> list[Block]:
    out = []
    for b in page.get_text("dict", flags=FLAGS)["blocks"]:
        if b.get("type") == 1:
            x0, y0, x1, y1 = b["bbox"]
            if b.get("image") and (x1 - x0 >= 30 or y1 - y0 >= 30):   # skip bullets and rules
                out.append(Block(pno, y0, y1, image=b["image"]))
            continue
        blk = Block(pno, b["bbox"][1], b["bbox"][3])
        sizes = Counter()
        for ln in b.get("lines", []):
            segs = [(s["text"], _style(s)) for s in ln["spans"] if s["text"]]
            for s in ln["spans"]:
                sizes[round(s["size"] * 2) / 2] += len(s["text"].strip())
            if "".join(t for t, _ in segs).strip():
                blk.lines.append(segs)
        if blk.lines:
            blk.size = sizes.most_common(1)[0][0]
            out.append(blk)
    return out


def _header_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text.lower())).strip()


def _body_size(pages: list[list[Block]]) -> float:
    chars = Counter()
    for blocks in pages:
        for b in blocks:
            if b.lines:
                chars[b.size] += len(b.text)
    return chars.most_common(1)[0][0] if chars else 11.0


def _drop_running_heads(pages: list[list[Block]], heights: list[float], body: float):
    """Remove page numbers, and small text in the top/bottom margin that repeats on other pages
    (book title, chapter name, "Page 3 of 10"); also logos repeated on many pages. Big text is
    left alone, so "Chapter 2" set near the top of a page stays a heading."""
    def running(b: Block, margin: float = MARGIN) -> bool:
        h = heights[b.page]
        return (bool(b.lines) and (b.y1 <= h * margin or b.y0 >= h * (1 - margin))
                and len(b.text) <= 120 and b.size <= body * 1.15)

    seen = Counter()
    for blocks in pages:
        seen.update({_header_key(b.text) for b in blocks if running(b)})
    logos = Counter()
    for blocks in pages:
        logos.update({hashlib.sha1(b.image).digest() for b in blocks if b.image})
    for i, blocks in enumerate(pages):
        pages[i] = [b for b in blocks if not (
            (running(b) and seen[_header_key(b.text)] >= 2)
            or (running(b, FOLIO_MARGIN) and PAGE_NUMBER.match(b.text))
            or (b.image and logos[hashlib.sha1(b.image).digest()] >= 3))]


# ---------------------------------------------------------------- book model
@dataclass
class Item:
    kind: str                 # "p", "h", "img" or "page" (an anchor where a PDF page starts)
    page: int
    segs: list = field(default_factory=list)   # [(text, style)] for "p" and "h"
    size: float = 0.0
    y1: float = 0.0           # bottom of the block on its page
    image: str = ""           # file name inside the EPUB for "img"
    full_page: bool = False   # a rendered page rather than a picture from the page

    @property
    def text(self) -> str:
        return "".join(t for t, _ in self.segs).strip()


def _append_line(segs: list, line: list):
    """Add a line to a paragraph, joining a word that was hyphenated across the break."""
    line = list(line)
    if segs:
        last, st = segs[-1]
        tail = last.rstrip()
        nxt = line[0][0].lstrip()
        if tail.endswith("\u00ad"):                       # soft hyphen: always a split word
            segs[-1] = (tail[:-1], st)
        elif len(tail) >= 2 and tail[-1] in "-\u2010" and tail[-2].isalpha() and nxt[:1].islower():
            segs[-1] = (tail[:-1], st)
        elif len(tail) >= 2 and tail[-1] in "-\u2010" and tail[-2].isalnum():
            segs[-1] = (tail, st)                          # "IEEE-754", "Sun-Spider": keep the hyphen
        else:
            segs[-1] = (tail + " ", st)
        line[0] = (nxt, line[0][1])
    segs.extend(line)


class Images:
    """Pictures for the EPUB, stored once each, as JPEG or PNG."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self._by_digest: dict[bytes, str] = {}

    def add(self, raw: bytes, name: str | None = None) -> str | None:
        digest = hashlib.sha1(raw).digest()
        if digest in self._by_digest:
            return self._by_digest[digest]
        try:
            im = Image.open(io.BytesIO(raw))
            im.load()
        except Exception:
            return None
        if im.format == "JPEG" and im.mode in ("RGB", "L"):
            data, ext = raw, "jpg"
        elif im.format == "PNG":
            data, ext = raw, "png"
        else:   # JPEG 2000, CMYK, TIFF…: re-save as something every reader shows
            buf = io.BytesIO()
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im.convert("RGBA").save(buf, "PNG", optimize=True)
                ext = "png"
            else:
                im.convert("RGB").save(buf, "JPEG", quality=88)
                ext = "jpg"
            data = buf.getvalue()
        name = f"{name or f'img{len(self.files) + 1}'}.{ext}"
        self.files[name] = data
        self._by_digest[digest] = name
        return name


def _render(page, longest: int = 1600) -> bytes:
    zoom = min(150 / 72, longest / max(page.rect.width, page.rect.height))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    buf = io.BytesIO()
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _language(doc, sample: str) -> str:
    lang = (getattr(doc, "language", None) or "").strip()
    if re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", lang):
        return lang
    words = Counter(re.findall(r"[a-zà-ÿ]+", sample.lower()))
    scores = {code: sum(words[w] for w in stop.split()) for code, stop in STOPWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 5 else "und"


def _title(doc, src: Path) -> str:
    t = (doc.metadata or {}).get("title", "").strip()
    if not t or re.search(r"\.(docx?|pdf|indd|pages|odt|rtf)$", t, re.I) or t.lower().startswith("microsoft"):
        return src.stem
    return t


@dataclass
class Book:
    title: str
    author: str
    language: str
    items: list[Item]
    chapters: list[tuple[int, str]]          # (index into items where the chapter starts, title)
    toc: list[tuple[int, str, int]]          # (level, title, page) from the PDF's bookmarks
    images: Images
    cover: str | None


def read_pdf(src: str | Path) -> Book:
    src = Path(src)
    with open_pdf(src) as doc:
        n = doc.page_count
        heights = [p.rect.height for p in doc]
        pages = []
        for i, page in enumerate(doc):
            pages.append(_blocks(page, i))
            progress(0.8 * (i + 1) / n)
        texty = sum(1 for blocks in pages if sum(len(b.text) for b in blocks if b.lines) >= 20)
        if n == 0 or texty < 0.2 * n:
            raise UserError(tr("This PDF has no text to put in an e-book: it looks like scanned pages. "
                               "Run text recognition (OCR) on it first."))
        _drop_running_heads(pages, heights, _body_size(pages))
        body = _body_size(pages)

        images = Images()
        cover = images.add(_render(doc[0], 1400), "cover")
        items: list[Item] = []
        drop_cap = None
        for i, blocks in enumerate(pages):
            items.append(Item("page", i))
            if not any(b.lines for b in blocks):
                has_art = any(b.image for b in blocks) or doc[i].get_drawings()
                if has_art:
                    name = cover if i == 0 else images.add(_render(doc[i]))
                    if name:
                        items.append(Item("img", i, image=name, full_page=True))
                continue
            for b in blocks:
                if b.image:
                    name = images.add(b.image)
                    if name:
                        items.append(Item("img", i, image=name))
                    continue
                text = b.text
                if len(text) == 1 and b.size >= body * 1.8 and text.isalpha():
                    if drop_cap:
                        items.append(_lone_letter(drop_cap))
                    drop_cap = b         # a big first letter, maybe set apart from its paragraph
                    continue
                big = len(text) <= 160 and b.size >= body * 1.2
                heading = big or (len(text) <= 100 and len(b.lines) <= 2 and b.all_bold and b.size >= body * 0.95
                                  and not ENDS_SENTENCE.search(text) and not text.endswith(","))
                segs: list = []
                for ln in b.lines:
                    _append_line(segs, ln)
                if drop_cap:
                    if drop_cap.page == i and b.y0 < drop_cap.y1:   # the paragraph starts beside it
                        segs[0] = (drop_cap.text + segs[0][0].lstrip(), segs[0][1])
                    else:
                        items.append(_lone_letter(drop_cap))
                    drop_cap = None
                if heading:
                    last = items[-1]
                    if (big and last.kind == "h" and last.page == i and last.size == b.size
                            and b.y0 - last.y1 < b.size * 0.8):
                        _append_line(last.segs, segs)   # a title set over two lines
                        last.y1 = b.y1
                    else:
                        items.append(Item("h", i, segs, b.size, b.y1))
                    continue
                prev = next((it for it in reversed(items) if it.kind != "page"), None)
                if (prev and prev.kind == "p" and abs(prev.size - b.size) < 1 and not ENDS_SENTENCE.search(prev.text)
                        and (prev.page == i - 1 or (prev.page == i and segs[0][0].lstrip()[:1].islower()))):
                    _append_line(prev.segs, segs)   # the paragraph carried on over a page or column break
                    continue
                items.append(Item("p", i, segs, b.size, b.y1))
            progress(0.8 + 0.15 * (i + 1) / n)

        toc = [(lvl, title.strip(), pg - 1) for lvl, title, pg in doc.get_toc(simple=True)
               if title.strip() and 1 <= pg <= n]
        meta = doc.metadata or {}
        sample = " ".join(it.text for it in items[:400] if it.kind == "p")
        title = _title(doc, src)
        if title == src.stem:   # no title in the PDF's properties: the biggest heading up front
            first = [it for it in items if it.kind == "h" and it.page <= 1]
            if first:
                title = max(first, key=lambda it: it.size).text[:200]
        return Book(title, (meta.get("author") or "").strip(), _language(doc, sample),
                    items, _chapters(items, toc), toc, images, cover)


def _lone_letter(b: Block) -> Item:
    """A big single letter that turned out not to be a drop cap: a heading, like "I" for Part I."""
    return Item("h", b.page, b.lines[0], b.size, b.y1)


def _chapters(items: list[Item], toc: list) -> list[tuple[int, str]]:
    """Where each chapter (= the XHTML file the reader opens) starts."""
    if toc:
        top = min(lvl for lvl, _, _ in toc)
        level = top
        if sum(1 for lvl, _, _ in toc if lvl == top) == 1 and sum(1 for lvl, _, _ in toc if lvl == top + 1) >= 2:
            level = top + 1    # the bookmarks hang under one entry with the book's own title
        starts = {}
        for lvl, title, pg in toc:
            if lvl <= level:
                starts.setdefault(pg, title)
        return [(k, starts[it.page]) for k, it in enumerate(items) if it.kind == "page" and it.page in starts]
    pages = {}
    for it in items:
        if it.kind == "h":
            pages.setdefault(it.size, set()).add(it.page)
    repeated = [s for s, p in pages.items() if len(p) >= 2]   # on one page only: a title block
    if not repeated:
        return []
    top = max(repeated)
    starts = []
    for k, it in enumerate(items):
        if it.kind == "h" and abs(it.size - top) <= 0.5:
            while k and items[k - 1].kind == "page":   # the page's anchor goes with its heading
                k -= 1
            starts.append((k, it.text))
    return starts


# ---------------------------------------------------------------- EPUB writing
CSS = """body { margin: 0 4%; line-height: 1.45; }
p { margin: 0 0 0.6em; text-align: justify; -webkit-hyphens: auto; hyphens: auto; }
h1, h2, h3 { line-height: 1.2; text-align: left; -webkit-hyphens: none; hyphens: none; }
h1 { font-size: 1.6em; margin: 1.2em 0 0.8em; }
h2 { font-size: 1.3em; margin: 1em 0 0.6em; }
h3 { font-size: 1.1em; margin: 1em 0 0.4em; }
figure { margin: 1em 0; text-align: center; }
figure.page { margin: 0; }
img { max-width: 100%; height: auto; }
figure.page img { max-height: 95vh; }
"""


def _x(s: str, quote: bool = False) -> str:
    return html.escape(NOT_XML.sub("", s), quote=quote)


def _inline(segs: list) -> str:
    merged: list[list] = []
    for t, st in segs:
        if merged and merged[-1][1] == st:
            merged[-1][0] += t
        else:
            merged.append([t, st])
    out = []
    for t, st in merged:
        t = _x(re.sub(r"\s+", " ", t))
        if st & ITALIC and t.strip():
            t = f"<em>{t}</em>"
        if st & BOLD and t.strip():
            t = f"<strong>{t}</strong>"
        out.append(t)
    return "".join(out).strip()


def _xhtml(title: str, lang: str, body: str, css: str = "../style.css") -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'lang="{lang}" xml:lang="{lang}">\n<head>\n<meta charset="utf-8"/>\n<title>{_x(title)}</title>\n'
            f'<link rel="stylesheet" type="text/css" href="{css}"/>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def write_epub(book: Book, out: Path):
    head_sizes = sorted({it.size for it in book.items if it.kind == "h"}, reverse=True)
    level = {s: min(k + 1, 3) for k, s in enumerate(head_sizes)}
    starts = dict(book.chapters)

    files: list[list] = []          # [title, body parts]
    page_file: dict[int, str] = {}  # PDF page → the file its anchor is in
    chapter_file: dict[int, str] = {}
    pages_in_file, has_content = 0, False
    for k, it in enumerate(book.items):
        if not files or (has_content and (k in starts or (it.kind == "page" and pages_in_file >= FILE_PAGES))):
            files.append(["", []])
            pages_in_file, has_content = 0, False
        name = f"c{len(files):03d}.xhtml"
        if k in starts:             # a chapter that opens a file (or follows only page anchors)
            files[-1][0] = files[-1][0] or starts[k]
            chapter_file[k] = name
        parts = files[-1][1]
        has_content = has_content or it.kind != "page"
        if it.kind == "page":
            page_file.setdefault(it.page, name)
            pages_in_file += 1
            parts.append(f'<span id="p{it.page + 1}"></span>')
        elif it.kind == "img":
            cls = ' class="page"' if it.full_page else ""
            parts.append(f'<figure{cls}><img src="../images/{it.image}" alt=""/></figure>')
        elif it.kind == "h":
            h = level.get(it.size, 3)
            parts.append(f"<h{h}>{_inline([(t, st & ~BOLD) for t, st in it.segs])}</h{h}>")   # bold already
        else:
            parts.append(f"<p>{_inline(it.segs)}</p>")

    # table of contents: the PDF's bookmarks (nested), else the chapter headings, else the book
    if book.toc:
        entries = [(lvl, title, f"text/{page_file.get(pg, 'c001.xhtml')}#p{pg + 1}") for lvl, title, pg in book.toc]
    else:
        entries = [(1, title or tr("Chapter {n}", n=i + 1), f"text/{chapter_file[k]}")
                   for i, (k, title) in enumerate(book.chapters)]
        if not entries or entries[0][2] != "text/c001.xhtml":   # what comes before the first chapter
            entries.insert(0, (1, book.title, "text/c001.xhtml"))
    nav, depth = [], 0
    base = min(lvl for lvl, _, _ in entries)
    for lvl, title, href in entries:
        lvl = max(1, min(lvl - base + 1, depth + 1))
        if lvl > depth:
            nav.append("<ol>" * (lvl - depth))
        else:
            nav.append("</li></ol>" * (depth - lvl) + "</li>")
        nav.append(f'<li><a href="{_x(href, True)}">{_x(title)}</a>')
        depth = lvl
    nav.append("</li></ol>" * depth)
    nav_doc = _xhtml(tr("Contents"), book.language,
                     f'<nav epub:type="toc" id="toc">\n<h1>{_x(tr("Contents"))}</h1>\n{"".join(nav)}\n</nav>',
                     "style.css")

    media = {"jpg": "image/jpeg", "png": "image/png"}
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="style.css" media-type="text/css"/>']
    for name in book.images.files:
        props = ' properties="cover-image"' if name == book.cover else ""
        iid = "cover-image" if name == book.cover else name.rsplit(".", 1)[0]
        manifest.append(f'<item id="{iid}" href="images/{name}" media-type="{media[name.rsplit(".", 1)[1]]}"{props}/>')
    spine = []
    for n in range(1, len(files) + 1):
        manifest.append(f'<item id="c{n:03d}" href="text/c{n:03d}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{n:03d}"/>')
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    creator = f"<dc:creator>{_x(book.author)}</dc:creator>\n" if book.author else ""
    cover_meta = '<meta name="cover" content="cover-image"/>\n' if book.cover else ""
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" '
           f'xml:lang="{book.language}">\n<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           f'<dc:identifier id="bookid">urn:uuid:{uuid.uuid4()}</dc:identifier>\n'
           f'<dc:title>{_x(book.title)}</dc:title>\n{creator}<dc:language>{book.language}</dc:language>\n'
           f'<meta property="dcterms:modified">{modified}</meta>\n{cover_meta}</metadata>\n'
           f'<manifest>\n{chr(10).join(manifest)}\n</manifest>\n<spine>\n{chr(10).join(spine)}\n</spine>\n</package>\n')
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles>\n</container>\n')

    def write(dst):
        with zipfile.ZipFile(dst, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)  # must come first
            deflate = dict(compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("META-INF/container.xml", container, **deflate)
            z.writestr("OEBPS/content.opf", opf, **deflate)
            z.writestr("OEBPS/nav.xhtml", nav_doc, **deflate)
            z.writestr("OEBPS/style.css", CSS, **deflate)
            for n, (title, parts) in enumerate(files, 1):
                z.writestr(f"OEBPS/text/c{n:03d}.xhtml",
                           _xhtml(title or book.title, book.language, "\n".join(parts)), **deflate)
            for name, data in book.images.files.items():
                z.writestr(f"OEBPS/images/{name}", data, compress_type=zipfile.ZIP_STORED)
    atomic_save(write, out)
    progress(1.0)


def pdf_to_epub(src: str | Path) -> list[Path]:
    book = read_pdf(src)
    out = sibling(src, ext=".epub")
    write_epub(book, out)
    return [out]


# ---------------------------------------------------------------- Kindle formats (Calibre)
CALIBRE_PLACES = ("/Applications/calibre.app/Contents/MacOS/ebook-convert",
                  str(Path.home() / "Applications/calibre.app/Contents/MacOS/ebook-convert"),
                  r"C:\Program Files\Calibre2\ebook-convert.exe",
                  "/opt/calibre/ebook-convert", "/usr/bin/ebook-convert")


def calibre_cmd() -> list[str] | None:
    """The `ebook-convert` command if Calibre is installed (apps opened from Finder don't get
    the shell's PATH, so the usual install places are checked too)."""
    for p in (shutil.which("ebook-convert"), *CALIBRE_PLACES):
        if p and os.path.exists(p):
            return [p]
    return None


def pdf_to_kindle(src: str | Path, fmt: str) -> list[Path]:
    """MOBI or AZW3: build the EPUB, then let Calibre convert it."""
    cmd = calibre_cmd()
    if not cmd:
        raise UserError(tr("{fmt} needs Calibre, which is free (calibre-ebook.com). "
                           "Install it and try again, or convert to EPUB instead.", fmt=fmt))
    book = read_pdf(src)
    out = sibling(src, ext="." + fmt.lower())
    with tempfile.TemporaryDirectory() as d:
        epub, tmp = Path(d) / "book.epub", Path(d) / f"book.{fmt.lower()}"
        write_epub(book, epub)
        from .media import _popen_kw
        try:
            r = subprocess.run([*cmd, str(epub), str(tmp)], capture_output=True, text=True, errors="replace",
                               timeout=900, **_popen_kw())
        except (OSError, subprocess.TimeoutExpired) as e:
            raise UserError(tr("Calibre couldn't make the {fmt} file.", fmt=fmt)) from e
        if r.returncode != 0 or not tmp.exists():
            lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
            print(f"ebook-convert failed ({r.returncode}):\n  " + "\n  ".join(lines[-25:]), flush=True)
            raise UserError(tr("Calibre couldn't make the {fmt} file.", fmt=fmt))
        shutil.move(str(tmp), out)
    return [out]
