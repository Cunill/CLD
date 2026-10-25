# PyInstaller configuration of ProvaYoutube.exe (block C02, spike; docs/sessions/C02.md). The CI job
# "Prova de YouTube (Windows)" runs it:
#   uv run --group packaging pyinstaller packaging/ProvaYoutube.spec --noconfirm
# Result: dist/ProvaYoutube/ with ProvaYoutube.exe and bin/ (Python, yt-dlp, yt-dlp-ejs, FFmpeg and Deno).
# Same layout as PassiMaker.spec: one folder, no console, everything but the .exe in bin/.
# ruff: noqa
import importlib.metadata
import sys
from pathlib import Path

from deno import find_deno_bin

ROOT = Path(SPECPATH).parent
NAME = "ProvaYoutube"
CONTENTS = "bin"
FFMPEG_DIR = ROOT / "vendor" / "ffmpeg"
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

datas = []
for tool in ("ffmpeg", "ffprobe"):
    binary = FFMPEG_DIR / "bin" / f"{tool}{EXE_SUFFIX}"
    if binary.is_file():
        datas.append((str(binary), "."))
    elif sys.platform == "win32":
        raise SystemExit(f"Falta {binary}: executa abans pwsh tools/obtenir_ffmpeg.ps1")
# Deno from the `deno` Python package (uv.lock): tools/prova_youtube.py looks for it in sys._MEIPASS (bin/).
datas.append((find_deno_bin(), "."))
for file in importlib.metadata.distribution("deno").files or []:
    if file.name == "LICENSE":
        datas.append((str(file.locate()), "llicencies/Deno"))
if (FFMPEG_DIR / "LICENSE.txt").is_file():
    datas.append((str(FFMPEG_DIR / "LICENSE.txt"), "llicencies/FFmpeg"))

a = Analysis(
    [str(ROOT / "tools" / "prova_youtube.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,  # yt-dlp's own hook adds the yt-dlp-ejs scripts (yt_dlp_ejs/**/*.js)
    hiddenimports=[],
    excludes=["PySide6", "shiboken6", "cv2", "tkinter", "_tkinter", "pydoc_data", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / "PassiMaker.ico"),
    upx=False,
    contents_directory=CONTENTS,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)
