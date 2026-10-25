"""Catalan message catalogue for the errors raised by the core (block B10).

The interface writes its own text with Qt's ``tr()``; the core modules cannot (rule 1: no Qt
outside ui/ and preview/), so they raise ``PassiMakerError`` with a ``message_key`` and whoever
shows it to the user translates it here.

The texts were approved in decision 0007 (proposed in the notes of blocks B1, B4 and B7).

Keys:

- ``projectio.*`` opening and saving a project (B1)
- ``images.*`` decoding a photo (B4)
- ``import.*`` one line per ``passimaker.importer.ImportFailure`` value (B4); the caller builds
  the key as ``f"import.{failure.reason.value}"`` so that this module imports nothing
- ``ffmpeg.*`` the FFmpeg bridge (B7)
- ``export.*`` exporting (B9)
- ``youtube.*`` music from YouTube (C01, decision 0012)
"""

from __future__ import annotations

from collections.abc import Mapping

MESSAGES: Mapping[str, str] = {
    # passimaker.projectio (B1)
    "projectio.corrupt": "El fitxer del projecte està malmès i no es pot obrir.",
    "projectio.newer_version": (
        "Aquest projecte s'ha fet amb una versió més nova de PassiMaker. Actualitza el programa per obrir-lo."
    ),
    "projectio.read_error": "No s'ha pogut llegir el fitxer del projecte.",
    "projectio.write_error": "No s'ha pogut desar el projecte.",
    # passimaker.images (B4)
    "images.not_found": "No es troba el fitxer de la foto.",
    "images.corrupt": "La foto està malmesa i no es pot llegir.",
    "images.unsupported": "Aquest format d'imatge no s'admet.",
    "images.too_large": "La foto és massa gran per obrir-la.",
    "images.out_of_memory": "No hi ha prou memòria per obrir la foto.",
    # passimaker.importer.ImportFailure (B4)
    "import.unsupported": "El format d'aquest fitxer no s'admet.",
    "import.raw": "Els fitxers RAW de càmera no s'admeten. Exporta'ls abans a JPG.",
    "import.corrupt": "El fitxer està malmès i no es pot llegir.",
    "import.too_small": "La imatge és massa petita (menys de 64 píxels).",
    "import.not_found": "No es troba el fitxer.",
    # passimaker.ffmpeg (B7)
    "ffmpeg.not_found": "No s'ha trobat FFmpeg. Torna a descomprimir el programa.",
    "ffmpeg.file_not_found": "No es troba el fitxer.",
    "ffmpeg.unreadable": "El fitxer està malmès o té un format que no es pot llegir.",
    "ffmpeg.no_audio": "El fitxer no té so.",
    "ffmpeg.disk_full": "El disc és ple. Allibera espai i torna-ho a provar.",
    "ffmpeg.write_error": "No es pot escriure el fitxer (permisos o carpeta inexistent).",
    "ffmpeg.encode_error": "No s'ha pogut crear el vídeo.",
    "ffmpeg.aborted": "S'ha cancel·lat l'exportació.",
    "ffmpeg.timeout": "FFmpeg no respon (el disc és molt lent?).",
    "ffmpeg.failed": "Error inesperat d'FFmpeg.",
    # passimaker.export (B9)
    "export.no_photos": "El projecte no té cap foto.",
    "export.missing_files": "No es troben alguns fitxers del projecte.",
    "export.disk_full": "No hi ha prou espai al disc.",
    "export.write_error": "No es pot escriure el vídeo en aquesta carpeta.",
    "export.failed": "L'exportació ha fallat per un error inesperat.",
    # passimaker.youtube (C01, decision 0012)
    "youtube.offline": "No hi ha connexió a internet. Comprova la xarxa i torna-ho a provar.",
    "youtube.invalid_link": "Aquest enllaç no és d'un vídeo de YouTube.",
    "youtube.unavailable": "Aquest vídeo no es pot descarregar (és privat, s'ha esborrat o té restriccions).",
    "youtube.live": "No es poden descarregar directes.",
    "youtube.broken": (
        "YouTube ha canviat i aquesta versió de PassiMaker ja no pot descarregar. "
        "Cal una versió nova del programa."
    ),
    "youtube.too_long": "Aquest vídeo dura més de 20 minuts.",
    "youtube.consent": "Cal acceptar l'avís abans de fer servir YouTube.",
}


def message(key: str) -> str:
    """Catalan text for a message key (falls back to the key itself)."""
    return MESSAGES.get(key, key)
