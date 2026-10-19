# PyInstaller spec. ONEFILE=1 -> portable single exe; otherwise a folder for the installer.
import os
from PyInstaller.utils.hooks import collect_all

onefile = os.environ.get("ONEFILE") == "1"
heif_datas, heif_bins, heif_hidden = collect_all("pillow_heif")
ff_datas, ff_bins, ff_hidden = collect_all("imageio_ffmpeg")   # its FFmpeg binary (video/audio)

a = Analysis(
    ["run.py"],
    datas=[("banana/assets", "banana/assets"), ("LICENSE", ".")] + heif_datas + ff_datas,   # MIT: ship the notice
    binaries=heif_bins + ff_bins,
    hiddenimports=["win32com.client", "PySide6.QtNetwork", "AppKit", "Quartz", "objc"] + heif_hidden + ff_hidden,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "pandas", "yaml", "PySide6.QtSql", "PySide6.QtTest",
              "PySide6.QtOpenGL", "PySide6.QtSvgWidgets", "PySide6.QtDesigner", "matplotlib", "scipy"],
)

DROP = ("Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6WebEngine", "Qt63D", "Qt6Multimedia", "Qt6Charts",
        "Qt6VirtualKeyboard", "Qt6Designer", "Qt6ShaderTools", "Qt6Sql", "Qt6Test", "opengl32sw",
        "Qt6OpenGL", "Qt6DataVisualization", "Qt6Positioning", "Qt6Sensors", "Qt6SerialPort",
        "Qt6Bluetooth", "Qt6Nfc", "Qt6RemoteObjects", "Qt6Scxml", "Qt6SpatialAudio", "Qt6TextToSpeech",
        "Qt6WebChannel", "Qt6WebSockets", "Qt6Svg", "qtquick", "qml",
        "libgtk-3", "libgdk-3", "libqgtk3", "libatk-")
a.binaries = [b for b in a.binaries if not any(d.lower() in b[0].lower() for d in DROP)]
a.datas = [d for d in a.datas if "translations" not in d[0].replace("\\", "/")]

pyz = PYZ(a.pure)
import sys
IS_MAC = sys.platform == "darwin"
common = dict(name="Banana", console=False, upx=False)
IS_LINUX = sys.platform.startswith("linux")
if IS_MAC:
    common.update(icon="banana/assets/banana.icns")
elif IS_LINUX:
    common.update(name="banana")       # icon comes from the .desktop file / hicolor theme
else:
    common.update(icon="banana/assets/banana.ico", version="installer/version_info.txt")

def min_macos(binaries) -> str:
    """The macOS the bundle really needs: the highest `minos` among the bundled binaries
    (e.g. numpy's Apple Silicon wheels want 14.0), so older Macs get a clear message."""
    import re
    import subprocess
    best = (11, 0)
    for _, path, _ in binaries:
        try:
            out = subprocess.run(["otool", "-l", path], capture_output=True, text=True, timeout=20).stdout
        except Exception:
            continue
        m = re.search(r"LC_BUILD_VERSION.*?minos (\d+)\.(\d+)", out, re.S) or \
            re.search(r"LC_VERSION_MIN_MACOSX.*?version (\d+)\.(\d+)", out, re.S)
        if m:
            best = max(best, (int(m[1]), int(m[2])))
    print(f"Banana: minimum macOS for this build: {best[0]}.{best[1]}")
    return f"{best[0]}.{best[1]}"


if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, argv_emulation=False, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="Banana", upx=False)
    app = BUNDLE(
        coll,
        name="Banana.app",
        icon="banana/assets/banana.icns",
        bundle_identifier="com.marvainstein.banana",
        info_plist={
            "CFBundleName": "Banana",
            "CFBundleDisplayName": "Banana",
            "CFBundleShortVersionString": "1.1.0",
            "CFBundleVersion": "1.1.0",
            "LSUIElement": True,                 # menu-bar app, no Dock icon
            "LSMinimumSystemVersion": min_macos(a.binaries),
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            # show up in Finder's "Open With" for any file, and accept drops on the app icon
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Any file",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.item", "public.content", "public.data"],
            }],
        },
    )
elif IS_LINUX:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="banana", upx=False)  # no strip: breaks OpenBLAS with Debian 12 binutils
elif onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="Banana", upx=False)
