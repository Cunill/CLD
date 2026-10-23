#!/usr/bin/env bash
# Linux (sessions al núvol): instal·la les llibreries de sistema de Qt i del so, comprova FFmpeg
# i prepara l'entorn de Python. Es pot executar tantes vegades com calgui.
# Ús: bash tools/preparar_sessio_nuvol.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

packages=(libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 libportaudio2 ffmpeg)
missing=()
for p in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || missing+=("$p")
done
if (( ${#missing[@]} > 0 )); then
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y -q "${missing[@]}" >/dev/null 2>&1 \
        || { apt-get update -q >/dev/null && apt-get install -y -q "${missing[@]}" >/dev/null; }
fi

bash tools/obtenir_ffmpeg.sh
uv sync -q
echo "Entorn preparat"
