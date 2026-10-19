# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Banana (a personal fork of [DragShift](https://github.com/llamaboi55/DragShift), MIT; keep its LICENSE and credit, and don't add tip/donation links) is a PySide6 tray app for Windows, macOS and Linux (X11). The user starts dragging a file, presses Shift, and a radial "liquid-glass" menu appears under the cursor. Dropping the file on a slice converts it or opens a tool window. Results are always written next to the original, and the original is never modified.

## Commands

```bash
pip install -r requirements.txt          # Linux also needs: sudo apt install libxcb-cursor0 libxkbcommon-x11-0
python -m banana                      # run from source (python run.py also works)
python -m banana --selftest           # exercise every library + build every window, then exit (what CI runs on frozen builds)
QT_QPA_PLATFORM=offscreen python -m pytest -q                      # all tests (CI sets offscreen)
python -m pytest -q tests/test_v11.py::test_compress_target_size   # a single test
pyinstaller Banana.spec --noconfirm   # folder build (.app bundle on macOS); ONEFILE=1 for the portable Windows exe
packaging/linux/build-deb.sh 1.2.0       # .deb from dist/banana (run after pyinstaller on Linux)
```

There is no linter config. Logs go to `~/Library/Logs/Banana/log.txt` (macOS), `%LOCALAPPDATA%\Banana\log.txt` (Windows) or `~/.local/share/Banana/log.txt` (Linux). Frozen builds redirect stdout/stderr there.

The version string lives in several places that must be bumped together: `banana/__init__.py`, `Banana.spec` (`CFBundle*Version`), `installer/Banana.iss`, `installer/version_info.txt`. The .deb version is passed to `build-deb.sh` in `.github/workflows/build.yml`.

## Architecture

**Layers.** The processing code has no UI, so it can be tested headless:
- `util.py` holds the file categories (`category()` → image/pdf/docx/text/video/audio), the output-path rules (`sibling()` never overwrites and respects `CONFIG["output"]`), `UserError` (its message is shown to the user as-is), `keep()`/`release()`, and `progress()` for long jobs.
- `convert.py` does the format conversions. `targets_for(cat, ext)` defines which targets the menu offers, and `convert(src, cat, target)` dispatches to them. Every function returns a list of output paths.
- `imaging.py` holds the pure image/PDF tool logic (compress, resize, metadata, split/merge/protect, redact, adjust, backgrounds).
- `report.py` turns `(action, srcs, outs)` into the `Result` shown in a toast ("2.4 MB → 610 KB · 75% smaller").

The UI sits on top of these: `radial.py` (the menu), `tools.py` (tool windows built on `window.GlassWindow`/`ImageView`), `toasts.py`, `settings.py`.

**Radial menu geometry.** Settings → Menu shape picks "banana" (default: a long band under the cursor, petals are sectors of a big circle centred far above the hub) or "round" (the original ring). Everything geometric goes through `radial.frame()` (window size + hub position) and `radial.petal(n, i)` (centre, angles, radii): the liquid render, fallback paint, hover, labels (`label_room()` shrinks text to fit tilted petals), the no-compositor mask, `hit()`, and `hub_on_screen()`/`petal_on_screen()`, which the E2E scripts use to aim. Don't hard-code radii or the 400 px window anywhere else.

**Look.** Accents are banana yellows (`glass.ACCENT_A/B/C`), with dark `glass.INK` text on them. The app icon and the macOS menu-bar icon come from `banana/shape.py`; `QT_QPA_PLATFORM=offscreen python packaging/make_icons.py` regenerates `banana/assets/banana.{png,ico,icns}`.

**App flow (`app.py`).** `BananaApp` wires everything together. `build_rings()` decides the menu contents (Convert ring plus Tools ring) from the file category. `run_item()` dispatches an `Item.key` of the form `"convert:PNG"` or `"tool:Crop"`: it either submits a background job or opens a tool window. Item keys and tool names in `GLYPHS`/`HINTS`/`IMAGE_TOOLS`/`PDF_TOOLS`/`VIDEO_TOOLS` must stay in sync with that dispatch. When you add a tool window, also add it to `selftest()`.

**Background work.** `submit()` runs a function on `QThreadPool` as a `Job`, shows a spinner toast only if the job takes over 150 ms, and then shows the `report.summarize` result. Every `QRunnable` must go through `keep(job)` and be `release()`d when its signal fires. Otherwise Python can GC the job while it is still running, and results get lost or the app crashes. `LiquidBacking` and the radial render job follow the same pattern. Tool windows get `self.submit` injected by `open_window()`. `ToolWindow.run()` closes the window immediately and saves at full resolution in the background. Without the app it runs synchronously (this is how tests and selftest use it). Editors work on a reduced preview (`open_preview`) and apply the edits to the full image when saving.

**Trigger (`trigger.py`).** The trigger polls global input state every 15 ms instead of installing hooks: `GetAsyncKeyState` on Windows, `platform_mac` (NSEvent, no Accessibility permission needed) and `platform_linux` (XQueryPointer through ctypes libX11; unavailable on Wayland). The platform modules expose the same `left_button_down / key_down / escape_down` interface. Logic: button held, moved ≥10 px and trigger key down → show the menu. A Shift tap while the menu is open flips the ring. If no file drag enters the menu, it hides itself. Menus opened from the tray, right-click or Send To use `click_mode` and are not managed by the watcher.

**Single instance + hand-off.** `handoff.try_handoff()` runs *before Qt is imported* (`run.py`, `__main__.py`). It writes JSON `{"files": [...]}` or `{"show": bool}` straight to the running instance's `QLocalServer` endpoint (a named pipe `\\.\pipe\Banana-<user>` on Windows, a Unix socket in the temp dir elsewhere), so right-click → Banana opens instantly. `app._ipc` reads it, and `queue_files()` debounces for 280 ms because Explorer launches once per selected file. On macOS, "Open With" files arrive as `QEvent.FileOpen` (`BananaQApplication`), not through argv.

**Glass rendering.** `liquid.py` is a numpy renderer. It takes a screenshot of what is behind a surface plus a signed distance field of the surface's shape, then refracts the pixels per-pixel (bezel lensing, RGB dispersion, specular rim, adaptive tint). `glass.py` provides the painting helpers, the QSS, `grab_screen` (on macOS it captures "below window N" so the drag image and Banana's own windows are left out), `hidden_drag_images` (on Windows it briefly hides Explorer's drag picture during capture), `LiquidBacking` for windows, and `apply_shape`/`no_compositor()`. Without a compositor (common on XFCE) translucent windows show black corners, so windows get masked to their exact shape instead. The radial menu draws a cheap blurred fallback right away and swaps in the liquid render (~60 ms later, from a worker thread). Keep these paths non-blocking so the menu always opens instantly.

**Video and audio (`media.py`).** FFmpeg comes from `imageio_ffmpeg.get_ffmpeg_exe()` (bundled binary, no ffprobe), with fallbacks to the system. `probe()` parses `ffmpeg -i` stderr. `_run()` writes to a hidden temp file with the real extension and reports progress through `util.progress()`, which `app.Job` forwards to the notification. MP4/MOV from H.264/HEVC sources is a stream copy (HEVC tagged `hvc1`). Always map streams explicitly (`_vmap`/`_amap`): iPhones add a spatial-audio track FFmpeg can't decode, and its default selection picks it. The imageio-ffmpeg wheel is per-architecture (an x86_64 venv bundles an x86_64 ffmpeg).

**Language (`i18n.py`).** Source strings are English. Wrap every user-visible string in `tr("…")` (placeholders as `tr("{n} files", n=3)`; plurals with `trn(n, one, many)`; words that go into output file names with `file_label()`) and add the Spanish text to `i18n.ES`. `tests/test_i18n.py` fails if a wrapped literal has no Spanish entry. Strings that reach `tr()` through a variable (tables like `HINTS`, `RATIOS`) must be added to `keys_from_tables()` in that test. Keep internal keys (`Item.key`, `tool_name`, `report.summarize` actions) in English. Windows build their text when they open, so call `tr()` at runtime, not in class-level constants.

**Settings.** `settings.Settings` wraps QSettings. `apply()` copies the values that worker threads need into the plain dict `util.CONFIG`, because threads must not touch Qt objects. Start-at-login is a registry Run key on Windows, a LaunchAgent on macOS and `~/.config/autostart` on Linux.

## Packaging and CI

- `Banana.spec` excludes many Qt modules and filters out large Qt binaries (`DROP`). When you add a PySide6 module, check it isn't excluded there. On Linux the spec must **not** strip binaries, because Debian 12's `strip` corrupts numpy's OpenBLAS.
- `build.yml` runs, on every push, pytest + PyInstaller + `--selftest` on Windows (onefile, folder build and an Inno Setup installer with a silent install/uninstall check), on macOS (arm64 and Intel .dmg; signing/notarization only runs if the secrets exist, see `docs/MAC-SIGNING.md`), and on Linux. The Linux job runs in a `debian:12` container with Python 3.12 via uv, because 3.11 hits a C-extension refcount bug, and it includes an XFCE end-to-end run. Pushes to `main` publish to the `latest` release, and `v*` tags publish a tagged release.
- `demo/e2e_{windows,mac,linux}.py` are real-desktop E2E scripts. They synthesize real mouse/keyboard drags (pyautogui/pywinauto via `winkit.py`, Quartz events, or XTest/xdotool), drop files on every slice, drive the tool windows and verify every output file. `e2e_mac.py` and `e2e_linux.py` import the shared sample-file builders and verifiers from `e2e_windows.py`. They are meant for CI runners (they move the real mouse and create folders like `~/BananaTest`), so don't run them on a dev machine casually. Results are force-pushed to the `e2e-output`, `e2e-mac-output` and `e2e-linux-output` branches. `demo/record_demo.py` (triggered by the `demo` branch) records the showcase video.
