"""Video and audio, through FFmpeg: the binary bundled by imageio-ffmpeg (so the app works
without installing anything), or one on the system. Like convert.py, every function takes
a source path and returns the output paths, written next to the source.

Long encodes report their progress with util.progress(), which the notification shows."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .i18n import file_label, tr
from .util import UserError, progress, sibling

VIDEO_TARGETS = ["MP4", "MOV", "WEBM", "GIF", "MP3", "M4A", "WAV"]
AUDIO_TARGETS = ["MP3", "M4A", "WAV", "FLAC", "OGG"]
AUDIO_ONLY = {"MP3", "M4A", "WAV", "FLAC", "OGG"}

# Compress: (CRF, audio bitrate) per quality; lower CRF = better and bigger
QUALITY = {"high": (23, "160k"), "medium": (28, "128k"), "small": (32, "96k")}
GIF_FPS, GIF_SIDE = 12, 480


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # apps opened from Finder don't get the shell's PATH, so look in the usual places too
    for p in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if p and os.path.exists(p):
            return p
    raise UserError(tr("FFmpeg isn't available, so video and audio can't be converted."))


def _popen_kw() -> dict:
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW: no console flashing up
    return {}


# ---------------------------------------------------------------- probe
@dataclass
class Info:
    duration: float = 0.0       # seconds
    width: int = 0              # as stored (before any rotation flag)
    height: int = 0
    vcodec: str = ""            # "" when there's no video (cover art doesn't count)
    acodec: str = ""            # "" when there's no audio

    @property
    def has_video(self) -> bool:
        return bool(self.vcodec)

    @property
    def has_audio(self) -> bool:
        return bool(self.acodec)


def probe(src: str | Path) -> Info:
    """Read duration, size and codecs from `ffmpeg -i` (imageio-ffmpeg ships no ffprobe)."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(src)], capture_output=True,
                       text=True, errors="replace", **_popen_kw())
    err = r.stderr
    info = Info()
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info.duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    for line in err.splitlines():
        if "Stream #" not in line:
            continue
        v = re.search(r"Video: (\w+)", line)
        if v and "attached pic" not in line and not info.vcodec:
            info.vcodec = v[1]
            d = re.search(r", (\d{2,5})x(\d{2,5})", line)
            if d:
                info.width, info.height = int(d[1]), int(d[2])
        a = re.search(r"Audio: (\w+)", line)
        if a and not info.acodec:
            info.acodec = a[1]
    if not (info.has_video or info.has_audio):
        raise UserError(tr("This file doesn't look like a video or audio file."))
    return info


def duration_text(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------- run
def _run(src: Path, args: list[str], out: Path, duration: float):
    """ffmpeg -i src <args> out, via a hidden temp file (with the real extension, so ffmpeg
    picks the container), reporting progress from `-progress`."""
    tmp = out.with_name(f".~{out.stem}.part{out.suffix}")
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", "-i", str(src), *args,
           "-progress", "pipe:1", "-nostats", str(tmp)]
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True, errors="replace",
                                **_popen_kw())
        for line in proc.stdout:
            if line.startswith("out_time_us=") and duration > 0:
                try:
                    progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration))
                except ValueError:
                    pass
        proc.wait()
        if proc.returncode != 0:
            log.seek(0)
            tail = [ln for ln in log.read().decode("utf-8", "replace").splitlines() if ln.strip()][-1:]
            if tmp.exists():
                tmp.unlink()
            raise UserError(tr("FFmpeg couldn't process this file.") + (f" ({tail[0][:160]})" if tail else ""))
    os.replace(tmp, out)


def _scale(max_side: int) -> str:
    """Fit the longest side in max_side (never upscale), keep even sizes for H.264."""
    return (f"scale='if(gte(iw,ih),min({max_side},iw),-2)':'if(gte(iw,ih),-2,min({max_side},ih))'")


H264 = ["-c:v", "libx264", "-preset", "faster", "-pix_fmt", "yuv420p"]


# ---------------------------------------------------------------- convert
def targets_for(cat: str, src_ext: str) -> list[str]:
    cur = src_ext.lower().lstrip(".").upper()
    cur = {"M4V": "MP4", "OGA": "OGG"}.get(cur, cur)
    return [t for t in (VIDEO_TARGETS if cat == "video" else AUDIO_TARGETS) if t != cur]


def convert(src: str | Path, target: str) -> list[Path]:
    src, target = Path(src), target.upper()
    info = probe(src)
    out = sibling(src, ext="." + target.lower())
    if target in AUDIO_ONLY:
        if not info.has_audio:
            raise UserError(tr("This video has no sound."))
        codec = {"MP3": ["-c:a", "libmp3lame", "-q:a", "2"],
                 "M4A": ["-c:a", "copy"] if info.acodec == "aac" else ["-c:a", "aac", "-b:a", "192k"],
                 "WAV": ["-c:a", "pcm_s16le"], "FLAC": ["-c:a", "flac"],
                 "OGG": ["-c:a", "libvorbis", "-q:a", "5"]}[target]
        _run(src, ["-vn", "-map_metadata", "0", *codec], out, info.duration)
        return [out]
    if not info.has_video:
        raise UserError(tr("This file has no video."))
    if target == "GIF":
        vf = (f"fps={GIF_FPS},{_scale(GIF_SIDE)}:flags=lanczos,"
              "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
        _run(src, ["-an", "-vf", vf, "-loop", "0"], out, info.duration)
        return [out]
    if target == "WEBM":
        _run(src, ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-deadline", "good",
                   "-cpu-used", "4", "-c:a", "libopus", "-b:a", "128k"], out, info.duration)
        return [out]
    # MP4 / MOV: H.264 and HEVC (what phones record) just change container: instant, lossless
    if info.vcodec in ("h264", "hevc") and info.acodec in ("", "aac", "mp3", "alac"):
        tag = ["-tag:v", "hvc1"] if info.vcodec == "hevc" else []   # so Apple players open HEVC
        try:
            _run(src, ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", *tag, "-movflags", "+faststart"],
                 out, info.duration)
            return [out]
        except UserError:
            pass   # odd streams: re-encode below
    _run(src, [*H264, "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
         out, info.duration)
    return [out]


# ---------------------------------------------------------------- compress
def compress(src: str | Path, quality: str = "medium", max_side: int | None = None,
             keep_audio: bool = True) -> Path:
    """Re-encode to H.264 MP4 at a quality level, optionally smaller and/or without sound."""
    src = Path(src)
    info = probe(src)
    if not info.has_video:
        raise UserError(tr("This file has no video."))
    crf, abr = QUALITY[quality]
    args = [*H264, "-crf", str(crf)]
    if max_side:
        args += ["-vf", _scale(max_side)]
    args += ["-c:a", "aac", "-b:a", abr] if keep_audio and info.has_audio else ["-an"]
    out = sibling(src, file_label("Compressed"), ".mp4")
    _run(src, [*args, "-movflags", "+faststart"], out, info.duration)
    return out
