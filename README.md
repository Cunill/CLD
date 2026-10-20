# Passi

Programa d'escriptori per a Windows per fer passis de fotos amb moviment de càmera (Ken Burns),
fosa encadenada i música, i exportar-los a MP4 Full HD. És l'equivalent de la funció de passi de
fotos del Windows Movie Maker. Ús intern, fora de línia.

- Pla i full de ruta: [docs/PLA.md](docs/PLA.md)
- Especificació funcional: [docs/ESPECIFICACIO.md](docs/ESPECIFICACIO.md)
- Contractes entre mòduls: [docs/CONTRACTES.md](docs/CONTRACTES.md)
- Instruccions per a Claude Code: [CLAUDE.md](CLAUDE.md)

## Posada en marxa

    uv sync
    pwsh tools/obtenir_ffmpeg.ps1      # Windows
    bash tools/obtenir_ffmpeg.sh       # Linux
    uv run pytest

Estat: en desenvolupament (bloc B0 fet: estructura, contractes i eines de prova).
