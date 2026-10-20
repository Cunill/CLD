#!/usr/bin/env bash
# Linux (sessions al núvol): comprova que hi ha FFmpeg >= 6 al sistema.
# A Windows es fa servir tools/obtenir_ffmpeg.ps1, que descarrega la versió fixada.
# Ús: bash tools/obtenir_ffmpeg.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "$root/vendor/ffmpeg/bin/ffmpeg" && -x "$root/vendor/ffmpeg/bin/ffprobe" ]]; then
    echo "FFmpeg present a vendor/ffmpeg/bin"
    exit 0
fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
    echo "No s'ha trobat FFmpeg. Instal·la'l amb: sudo apt-get install -y ffmpeg" >&2
    exit 1
fi
major="$(ffmpeg -version | head -n1 | sed -E 's/^ffmpeg version n?([0-9]+).*/\1/')"
if [[ ! "$major" =~ ^[0-9]+$ ]] || (( major < 6 )); then
    echo "Cal FFmpeg 6 o posterior (trobada: $(ffmpeg -version | head -n1))" >&2
    exit 1
fi
echo "Fent servir l'FFmpeg del sistema: $(ffmpeg -version | head -n1)"
