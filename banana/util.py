"""Shared helpers: output paths, file categories, sizes."""
from __future__ import annotations

import os
import threading
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".tif", ".tiff",
              ".avif", ".bmp", ".gif", ".ico"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".wmv", ".flv", ".mpg", ".mpeg",
              ".3gp", ".mts", ".m2ts"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".wma"}


def category(path: str | Path) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOCX_EXTS:
        return "docx"
    if ext in TEXT_EXTS:
        return "text"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def unique_path(path: str | Path) -> Path:
    """Return `path`, or `name (1).ext`, `name (2).ext`... if it already exists."""
    p = Path(path)
    if not p.exists():
        return p
    i = 1
    while True:
        cand = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not cand.exists():
            return cand
        i += 1


class UserError(Exception):
    """An error with a message that's fine to show the user as-is."""


# Runtime options (filled from Settings at start-up; plain values so worker threads can read them)
CONFIG = {
    "output": "next",        # "next" = beside the original, "folder" = a "Banana" subfolder
    "jpg_quality": 90,
    "pdf_dpi": 200,
    "menu_shape": "banana",  # "banana" or "round" (radial.petal)
}


def output_dir(src: str | Path) -> Path:
    d = Path(src).parent
    if CONFIG.get("output") == "folder":
        d = d / "Banana"
        d.mkdir(exist_ok=True)
    return d


def sibling(src: str | Path, suffix_label: str = "", ext: str | None = None) -> Path:
    """Output path for `src`. sibling('a.jpg', 'Cropped') -> 'a Cropped.jpg' (never overwrites)."""
    s = output_dir(src) / Path(src).name
    stem = f"{s.stem} {suffix_label}".strip() if suffix_label else s.stem
    new_ext = ext if ext is not None else s.suffix
    if not new_ext.startswith("."):
        new_ext = "." + new_ext
    return unique_path(s.with_name(stem + new_ext))


def human_size(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def file_size(path: str | Path) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------- background job lifetime
# QThreadPool runs a QRunnable in C++, but the Python object (and the QObject carrying its
# signals) can be garbage-collected while it's still running: results then never arrive,
# or the app crashes. Keep every job alive until its result has been handled.
ALIVE: set = set()


# Progress of long jobs (video): the job's thread installs a callback, the work calls progress().
_local = threading.local()


def set_progress_callback(cb):
    _local.cb = cb


def progress(fraction: float):
    """Report 0..1 done from inside a background job (no-op outside one)."""
    cb = getattr(_local, "cb", None)
    if cb is not None:
        cb(fraction)


def keep(job):
    job.setAutoDelete(False)
    ALIVE.add(job)
    return job


def release(job):
    ALIVE.discard(job)
