"""Video and audio through FFmpeg: conversions, audio extraction, compression, progress."""
import subprocess
from pathlib import Path

import pytest

from banana import app, convert, media, report
from banana.util import UserError, category, set_progress_callback

try:
    FFMPEG = media.ffmpeg_exe()
except UserError:
    FFMPEG = None
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="no FFmpeg")


def make_video(path: Path, vcodec="libx264", size="640x360", seconds=2, audio=True, rotate=None) -> Path:
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p"]
    if vcodec == "libx265":
        cmd += ["-x265-params", "log-level=error"]
    tmp = path.with_name("raw_" + path.name)
    subprocess.run(cmd + [str(tmp if rotate else path)], check=True)
    if rotate:   # phone-style: pixels stored landscape, a flag says "show it rotated"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-display_rotation", str(rotate),
                        "-i", str(tmp), "-c", "copy", str(path)], check=True)
    return path


IPHONE = """
  Duration: 00:00:05.03, start: 0.000000, bitrate: 12000 kb/s
  Stream #0:0[0x1](und): Video: hevc (Main 10) (hvc1 / 0x31637668), yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67), 1920x1080, 9000 kb/s, 29.98 fps, 30 tbr, 600 tbn (default)
  Stream #0:1[0x2](und): Audio: none (apac / 0x63617061), 48000 Hz, 4 channels, 600 kb/s (default)
  Stream #0:2[0x3](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 166 kb/s
  Stream #0:3[0x4](und): Data: none (mebx / 0x7862656D), 0 kb/s (default)
"""


def test_iphone_spatial_audio_uses_the_aac_track():
    """FFmpeg can't decode the 4-channel spatial-audio track and would pick it by default."""
    info = media.parse_probe(IPHONE)
    assert (info.vcodec, info.width, info.height, round(info.duration, 2)) == ("hevc", 1920, 1080, 5.03)
    assert (info.acodec, info.audio_index) == ("aac", 1)
    assert media._amap(info) == ["-map", "0:a:1"]
    only_spatial = media.parse_probe(IPHONE.replace("Audio: aac (LC)", "Audio: none (LC)"))
    assert not only_spatial.has_audio


def test_categories_and_menu():
    assert category("a.MOV") == "video" and category("b.m4a") == "audio"
    assert "MP4" in convert.targets_for("video", ".mov") and "MOV" not in convert.targets_for("video", ".mov")
    assert convert.targets_for("audio", ".mp3") == ["M4A", "WAV", "FLAC", "OGG"]
    rings = app.BananaApp.build_rings(None, ["clip.mov"])
    assert [i.key for i in list(rings.values())[1]] == ["tool:Compress"]


def test_mov_to_mp4_keeps_hevc_without_reencoding(tmp_path):
    src = make_video(tmp_path / "iPhone.mov", "libx265")
    out = convert.convert(src, "video", "MP4")[0]
    assert out.name == "iPhone.mp4"
    info = media.probe(out)
    assert info.vcodec == "hevc" and info.acodec == "aac" and abs(info.duration - 2) < 0.2
    head = subprocess.run([FFMPEG, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "hvc1" in head                 # tagged so QuickTime / iPhone play it
    r = report.summarize("convert:MP4", [src], [out])
    assert r.title == "MOV → MP4"


@pytest.mark.parametrize("target,codec", [("MP3", "mp3"), ("M4A", "aac"), ("WAV", "pcm_s16le")])
def test_extract_audio(tmp_path, target, codec):
    src = make_video(tmp_path / "Clip.mov")
    out = convert.convert(src, "video", target)[0]
    info = media.probe(out)
    assert not info.has_video and info.acodec == codec and abs(info.duration - 2) < 0.2


def test_no_sound_is_a_clear_error(tmp_path):
    src = make_video(tmp_path / "Silent.mp4", audio=False)
    with pytest.raises(UserError):
        convert.convert(src, "video", "MP3")


def test_gif_and_webm(tmp_path):
    src = make_video(tmp_path / "Clip.mov", seconds=1)
    assert convert.convert(src, "video", "GIF")[0].stat().st_size > 0
    assert media.probe(convert.convert(src, "video", "WEBM")[0]).vcodec == "vp9"


def test_compress_smaller_scaled_and_progress(tmp_path):
    src = make_video(tmp_path / "Clip.mov", size="1280x720")
    seen = []
    set_progress_callback(seen.append)
    try:
        out = media.compress(src, "small", 480, keep_audio=False)
    finally:
        set_progress_callback(None)
    info = media.probe(out)
    assert out.name == "Clip Compressed.mp4" and out.stat().st_size < src.stat().st_size
    assert (info.width, info.height) == (480, 270) and not info.has_audio
    assert seen and 0.5 < seen[-1] <= 1.0
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".~")]   # no temp files left


def test_compress_portrait_phone_video_keeps_it_upright(tmp_path):
    src = make_video(tmp_path / "Portrait.mov", size="1280x720", seconds=1, rotate=90)
    out = media.compress(src, "medium", 640)
    info = media.probe(out)
    assert (info.width, info.height) == (360, 640)     # rotated upright, longest side 640


def test_audio_conversions(tmp_path):
    mp3 = convert.convert(make_video(tmp_path / "Song.mov"), "video", "MP3")[0]
    for target, codec in (("FLAC", "flac"), ("OGG", "vorbis"), ("M4A", "aac")):
        assert media.probe(convert.convert(mp3, "audio", target)[0]).acodec == codec
