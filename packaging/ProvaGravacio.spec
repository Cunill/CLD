# PyInstaller configuration of ProvaGravacio.exe (block C08, spike; docs/sessions/C08.md). The CI job
# "Prova de gravació (Windows)" runs it:
#   uv run --group packaging pyinstaller packaging/ProvaGravacio.spec --noconfirm
# Result: dist/ProvaGravacio/ with ProvaGravacio.exe and bin/ (Python, soundcard, NumPy and FFmpeg).
# Same layout as PassiMaker.spec: one folder, no console, everything but the .exe in bin/.
# ruff: noqa
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).parent
NAME = "ProvaGravacio"
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
if (FFMPEG_DIR / "LICENSE.txt").is_file():
    datas.append((str(FFMPEG_DIR / "LICENSE.txt"), "llicencies/FFmpeg"))
# The report gives the versions from the package metadata, which PyInstaller does not bring by itself.
datas += copy_metadata("soundcard") + copy_metadata("cffi")
# soundcard's C declarations (soundcard/*.py.h). Its own PyInstaller hook adds them too, but PyInstaller finds
# that hook only if `import soundcard` works while building (not on a machine without sound).
datas += collect_data_files("soundcard")

a = Analysis(
    [str(ROOT / "tools" / "prova_gravacio.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["soundcard", "soundcard.mediafoundation"],  # imported with importlib
    excludes=[
        "PySide6",
        "shiboken6",
        "cv2",
        "sounddevice",
        "yt_dlp",
        "tkinter",
        "_tkinter",
        "pydoc_data",
        "IPython",
        "matplotlib",
    ],
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
