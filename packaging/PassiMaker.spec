# PyInstaller configuration of PassiMaker.exe (block B12). Run by tools/construir_zip.ps1:
#   uv run --group packaging pyinstaller packaging/PassiMaker.spec --noconfirm
# Result: dist/PassiMaker/ with PassiMaker.exe and bin/ (Python, Qt, the libraries and FFmpeg).
# One folder, not one file: it starts faster and antivirus programs flag it less often (risk R8).
# ruff: noqa
import importlib.metadata
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from passimaker import __version__  # noqa: E402

NAME = "PassiMaker"
CONTENTS = "bin"
"""Everything but the .exe goes to bin/, FFmpeg included: the program finds ffmpeg.exe and ffprobe.exe
in sys._MEIPASS (passimaker.ffmpeg.locate, "carpeta del programa")."""
FFMPEG_DIR = ROOT / "vendor" / "ffmpeg"
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

# Qt modules the program does not use (it uses QtCore, QtGui and QtWidgets only; risk R9).
QT_UNUSED = [
    "QtNetwork", "QtQml", "QtQuick", "QtQuickWidgets", "QtQuickControls2", "QtPdf", "QtPdfWidgets",
    "QtSvg", "QtSvgWidgets", "QtOpenGL", "QtOpenGLWidgets", "QtSql", "QtTest", "QtDBus", "QtXml",
    "QtConcurrent", "QtPrintSupport", "QtHelp", "QtUiTools", "QtDesigner", "QtNetworkAuth",
    "QtMultimedia", "QtMultimediaWidgets", "QtWebEngineCore", "QtWebEngineWidgets", "QtCharts",
    "Qt3DCore", "QtBluetooth", "QtPositioning", "QtSerialPort", "QtStateMachine", "QtTextToSpeech",
]
EXCLUDES = [f"PySide6.{m}" for m in QT_UNUSED] + ["tkinter", "_tkinter", "pydoc_data", "IPython", "matplotlib"]

_DROP = [
    re.compile(p, re.IGNORECASE)
    for p in (
        # Qt libraries and plugins of the unused modules (the PySide6 hook would still bring some).
        r"(^|[\\/])(lib)?Qt6(Network|Qml|Quick|Pdf|Svg|OpenGL|Sql|Test|Xml|Concurrent|PrintSupport|VirtualKeyboard)\b",
        r"[\\/]plugins[\\/](tls|networkinformation|qmltooling|sqldrivers|position|generic|platforminputcontexts|virtualkeyboard)[\\/]",
        r"[\\/]plugins[\\/]imageformats[\\/](lib)?q(svg|pdf|tga|wbmp|icns|tiff|webp)",
        r"[\\/]plugins[\\/]iconengines[\\/]",
        r"opengl32sw\.dll$",  # software OpenGL (20 MB): the widgets draw without OpenGL
        r"opencv_videoio_ffmpeg",  # OpenCV's own FFmpeg (25 MB): video goes through passimaker.ffmpeg
        r"[\\/]translations[\\/](?!qtbase_ca\.qm$|qt_ca\.qm$)[^\\/]+\.qm$",  # only Catalan
    )
]


def keep(entry) -> bool:
    destination = entry[0].replace("\\", "/")
    source = str(entry[1]) if len(entry) > 1 else ""
    return not any(p.search("/" + destination) or p.search(source) for p in _DROP)


datas = []
for tool in ("ffmpeg", "ffprobe"):
    binary = FFMPEG_DIR / "bin" / f"{tool}{EXE_SUFFIX}"
    if binary.is_file():
        datas.append((str(binary), "."))
    elif sys.platform == "win32":
        raise SystemExit(f"Falta {binary}: executa abans pwsh tools/obtenir_ffmpeg.ps1")
if (FFMPEG_DIR / "LICENSE.txt").is_file():
    datas.append((str(FFMPEG_DIR / "LICENSE.txt"), "llicencies/FFmpeg"))
# Music from YouTube (block C06): Deno from the `deno` Python package (uv.lock), next to ffmpeg.exe, where
# passimaker.youtube.find_deno looks for it. The scripts of yt-dlp-ejs are added by yt-dlp's own PyInstaller hook.
from deno import find_deno_bin  # noqa: E402

datas.append((find_deno_bin(), "."))
for file in importlib.metadata.distribution("deno").files or []:
    if file.name == "LICENSE":
        datas.append((str(file.locate()), "llicencies/Deno"))
# Recording the sound of the computer (block C06): soundcard's C declarations (soundcard/*.py.h) and the
# metadata of soundcard and cffi, as in packaging/ProvaGravacio.spec (spike C08).
datas += copy_metadata("soundcard") + copy_metadata("cffi") + collect_data_files("soundcard")
# The window icon, next to passimaker/ui/app.py (passimaker.ui.app.ICON_FILE).
datas.append((str(ROOT / "src" / "passimaker" / "ui" / "app_icon.png"), "passimaker/ui"))

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    # passimaker.preview.sound imports sounddevice with importlib (so a PC without PortAudio still starts):
    # PyInstaller cannot see it. Its hook brings PortAudio (bin/_sounddevice_data).
    # passimaker.recorder imports soundcard.mediafoundation with importlib (after the COM initialisation): same.
    hiddenimports=["sounddevice", "soundcard", "soundcard.mediafoundation"],
    excludes=EXCLUDES,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]
pyz = PYZ(a.pure)


def _version_info():
    from PyInstaller.utils.win32 import versioninfo as vi

    numbers = tuple(int(n) for n in re.findall(r"\d+", __version__)[:4])
    numbers += (0,) * (4 - len(numbers))
    strings = [
        vi.StringStruct("CompanyName", "PassiMaker"),
        vi.StringStruct("FileDescription", "PassiMaker: passis de fotos"),
        vi.StringStruct("FileVersion", __version__),
        vi.StringStruct("InternalName", NAME),
        vi.StringStruct("OriginalFilename", f"{NAME}.exe"),
        vi.StringStruct("ProductName", NAME),
        vi.StringStruct("ProductVersion", __version__),
        vi.StringStruct("LegalCopyright", "Ús intern"),
    ]
    return vi.VSVersionInfo(
        ffi=vi.FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            vi.StringFileInfo([vi.StringTable("040304B0", strings)]),  # Catalan, Unicode
            vi.VarFileInfo([vi.VarStruct("Translation", [0x0403, 1200])]),
        ],
    )


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / "PassiMaker.ico"),
    version=_version_info() if sys.platform == "win32" else None,
    upx=False,
    contents_directory=CONTENTS,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)
