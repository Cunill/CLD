# Passi: context per a Claude Code

## Què és
Programa d'escriptori per a Windows per fer passis de fotos (moviment Ken Burns, fosa encadenada, música)
i exportar-los a MP4 Full HD (1920×1080 o 1080×1920, 30 fps). Ús intern i fora de línia.
Pla: docs/PLA.md · Contractes: docs/CONTRACTES.md · Comportament i valors per defecte: docs/ESPECIFICACIO.md ·
Decisions: docs/decisions/ · Estat de cada bloc: docs/sessions/

## On es desenvolupa
Sessions de Claude Code al núvol (Linux) i CI a GitHub Actions sobre Windows (decisió 0002).
El producte és només per a Windows; el nucli i la interfície (sense pantalla) es proven també a Linux.

## Pila
Python 3.12, uv, PySide6-Essentials, NumPy, OpenCV (headless), Pillow + pillow-heif, sounddevice,
FFmpeg (7.1.1 fixat a Windows a vendor/ffmpeg; FFmpeg ≥ 6 del sistema a Linux), PyInstaller.
Proves: pytest, pytest-qt, Hypothesis. Estil: ruff. Tipus: pyright (estricte a src/).

## Ordres
- Preparar l'entorn: `uv sync` i obtenir FFmpeg: `pwsh tools/obtenir_ffmpeg.ps1` (Windows) o
  `bash tools/obtenir_ffmpeg.sh` (Linux)
- Linux: Qt necessita `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0` i el so `libportaudio2`
- Proves ràpides (per defecte): `uv run pytest`
- Proves d'un mòdul: `uv run pytest tests/unit/<mòdul>`
- Totes excepte rendiment: `uv run pytest -m "not perf"`
- Rendiment: `uv run pytest -m perf`
- Estil i tipus: `uv run ruff check .` · `uv run ruff format --check .` · `uv run pyright`
- Dades de prova per inspeccionar-les: `uv run python -m tests.fixtures.generate tests/_generated`
- Executar el programa: `uv run passi`
- Crear un projecte des d'una carpeta: `uv run passi-nou <carpeta_fotos> [música...] -o <projecte.passi>`
- Exportar sense finestra: `uv run passi-render <projecte.passi> <sortida.mp4>`
- Construir el ZIP portable (Windows): `pwsh tools/construir_zip.ps1`

## Regles d'arquitectura
1. Qt només a src/passi/ui i src/passi/preview. La resta del nucli no importa PySide6 (hi ha una prova).
2. El projecte només es modifica a través del controlador (src/passi/model). Les dades són immutables.
3. Un sol compositor (src/passi/render) per a previsualització i exportació.
4. Unitats: temps en segons (float) al model; fotogrames enters a l'exportació; imatges NumPy RGB uint8 H×W×3;
   finestres de moviment normalitzades (0–1).
5. Determinisme: cap aleatorietat fora de la llavor del projecte.
6. Tot el que trigui més de 50 ms, fora del fil de la interfície.
7. FFmpeg sempre a través de src/passi/ffmpeg: sense shell, sense finestres de consola, amb rutes Unicode.
   És l'únic mòdul que pot fer servir subprocess (hi ha una prova).
8. Textos visibles sempre traduïbles (tr) i en català. Codi, noms i comentaris en anglès.
9. Valors per defecte i rangs, només a src/passi/model/defaults.py; paràmetres de moviment, a src/passi/motion.
10. Cap dependència nova sense proposar-la abans.

## Protocol de sessió (un bloc per sessió)
1. Partir de main actualitzat i crear la branca que indica el prompt (bloc/BNN-nom).
   Si la branca ja existeix, continuar-hi i llegir docs/sessions/BNN.md.
2. Llegir només els fitxers que indica el prompt i docs/CONTRACTES.md. No explorar tot el repositori.
3. Modificar només els fitxers permesos pel prompt. Si cal tocar-ne d'altres o canviar un contracte:
   aturar-se i proposar-ho.
4. Escriure les proves alhora que el codi. No afeblir ni esborrar proves per fer-les passar.
   No regenerar imatges golden sense permís explícit.
5. Abans de cada commit: proves del bloc, suite ràpida, estil i tipus, tot en verd.
6. Commits petits i descriptius en català ("B3: regles d'equilibri del sorteig").
7. En acabar: push, PR amb `gh pr create` (resum, criteris d'acceptació marcats, desviacions) i
   nota a docs/sessions/BNN.md.
8. Condició d'aturada:
   - Criteris complerts → aturar-se i fer el resum.
   - Bloqueig (2 intents fallits sobre el mateix problema, cal canviar un contracte, o el context
     s'acosta al límit) → commit "WIP", nota a docs/sessions/BNN.md amb l'estat i el pas següent,
     i aturar-se.

## Estat
Blocs integrats a main: B0 (PR #1, commit `bd4cde4`) · B3 (PR #2, commit `1c49679`) ·
B2 (PR #6, commit `d24243a`) · B1 (PR #5, commit `defb833`).
Fita F1 aprovada (decisions 0004 i 0005). Pendents: B4, B5, B6, B7–B16.
Per reobrir un bloc tancat: vegeu "Com reobrir" a docs/sessions/BNN.md.
