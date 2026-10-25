# PassiMaker: context per a Claude Code

## Què és
Programa d'escriptori per a Windows per fer passis de fotos (moviment Ken Burns, fosa encadenada, música)
i exportar-los a MP4 Full HD (1920×1080 o 1080×1920, 30 fps). Ús intern; fora de línia excepte la música
de YouTube (decisió 0012).
Pla: docs/PLA.md · Contractes: docs/CONTRACTES.md · Comportament i valors per defecte: docs/ESPECIFICACIO.md ·
Decisions: docs/decisions/ · Estat de cada bloc: docs/sessions/

## On es desenvolupa
Sessions de Claude Code al núvol (Linux) i CI a GitHub Actions sobre Windows (decisió 0002).
El producte és només per a Windows; el nucli i la interfície (sense pantalla) es proven també a Linux.
Dues menes de sessió (24/10/2026); es fa servir la que convingui a cada tasca:
- **Al núvol**: programar, proves, PR i fusions. No pot crear etiquetes ni versions publicades, esborrar branques
  remotes, fer servir GraphQL (`gh pr`, `gh issue`: cal `gh api` o les eines de GitHub) ni els fitxers o el Windows
  de l'usuari. Per publicar una versió: el flux `publicar.yml` (docs/PUBLICAR.md).
- **Local** (Claude Code al PC de l'usuari, amb les seves credencials): **només el que el núvol no pot fer**
  (decisió de l'usuari, 24/10/2026): executar coses al PC (el programa, les mesures, fotos reals), etiquetes i
  versions publicades, i pujar la feina feta al PC. Obrir PR, revisar-les, fusionar-les, documentar i programar es
  fa des del núvol. Cal `git`, `gh` (`gh auth login`), `uv` i
  `pwsh tools/obtenir_ffmpeg.ps1`.

## Comunicació amb l'usuari
- Les preguntes i les decisions que ha de prendre l'usuari van **al final del missatge**, en un apartat
  "**Per decidir:**" numerat (una per punt, amb les opcions), i també el que li toca fer ("Pendent de la teva part").
  No s'amaguen preguntes enmig de l'explicació ni se'n fan dues en una sola frase.
- Instruccions pas a pas: un pas cada vegada, curt i clar.

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
- Executar el programa: `uv run passimaker`
- Crear un projecte des d'una carpeta: `uv run passimaker-nou <carpeta_fotos> [música...] -o <projecte.pmk>`
- Exportar sense finestra: `uv run passimaker-render <projecte.pmk> <sortida.mp4>`
- Construir el ZIP portable (Windows): `pwsh tools/construir_zip.ps1`

## Regles d'arquitectura
1. Qt només a src/passimaker/ui i src/passimaker/preview. La resta del nucli no importa PySide6 (hi ha una prova).
2. El projecte només es modifica a través del controlador (src/passimaker/model). Les dades són immutables.
3. Un sol compositor (src/passimaker/render) per a previsualització i exportació.
4. Unitats: temps en segons (float) al model; fotogrames enters a l'exportació; imatges NumPy RGB uint8 H×W×3;
   finestres de moviment normalitzades (0–1).
5. Determinisme: cap aleatorietat fora de la llavor del projecte.
6. Tot el que trigui més de 50 ms, fora del fil de la interfície.
7. FFmpeg sempre a través de src/passimaker/ffmpeg: sense shell, sense finestres de consola, amb rutes Unicode.
   És l'únic mòdul que pot fer servir subprocess (hi ha una prova).
8. Textos visibles sempre traduïbles (tr) i en català. Codi, noms i comentaris en anglès.
9. Valors per defecte i rangs, només a src/passimaker/model/defaults.py; paràmetres de moviment, a src/passimaker/motion.
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
B2 (PR #6, commit `d24243a`) · B1 (PR #5, commit `defb833`) · B7 (PR #11, commit `9d7d926`) ·
B4 (PR #12, commit `f56b8d4`) · B8 (PR #14, commit `311bed0`) · B6 (PR #15, commit `e4da3fa`) ·
B5 (PR #20, commit `d23f58e`) · B9 (PR #21, commit `dd3aaa0`) · B10 (PR #27, commit `b4a524b`) ·
B11 (PR #30, commit `427301e`) · B13 (PR #31, commit `0ced4ec`) · B12 (PR #33, commit `a71e22e`) ·
B14 (PR #37, commit `8368028`) · B15 (PR #40, commit `a96edd6`) · B16 (PR #42, commit `47d7d34`).
**Tots els blocs del pla són a `main`: versió 1.0.0** (docs/CHANGELOG.md).
Manteniment: M01 canvi de nom a PassiMaker (PR #9, commit `72341ff`, decisió 0006) ·
M02 `SHORT_SONG_FADE_FRACTION` a defaults.py (PR #16, commit `43faaaf`) ·
M03 extensió `.pmk` (PR #25, commit `66b6e92`, decisió 0009) ·
M04 arrossegar fotos amb el ratolí i so obert en pausa per al Bluetooth (PR #36, commit `56ccca7`) ·
M05 millores de les proves de l'usuari i codi compartit (PR #49, commit `2aad3e3`, decisió 0011) · icona nova (PR #48).
**Versió 1.1.0** (docs/CHANGELOG.md), publicada com a `v1.1` amb el flux `publicar.yml`.
Fita F1 aprovada (decisions 0004 i 0005). Fita F2: vídeo provat per l'usuari amb les seves fotos (vertical i
horitzontal) el 21/10/2026, correcte.
**Decidit el 24/10/2026: no es fan proves amb persones externes** (ni la de la F2, ni la de la F3, ni la F5 amb dues
persones; PLA §4.4). Les proves pràctiques les fa només l'usuari. Etiquetes `v0.5-mvp` i `v1.0` posades el 24/10/2026.
Guia i "Quant a" revisats per l'usuari el 24/10/2026: correctes (s'hi afegeix l'apartat "Imprevistos", a petició seva).
Fotos reals provades per l'usuari el 24/10/2026 (D:\TEMP_PM, càmera i mòbil, sense HEIC): miniatures instantànies i
nítides. Sense provar amb HEIC d'iPhone (decisió de l'usuari: es deixa així). Manteniment v1.1 (M05) fet. Llista de
millores de docs/proves_usuari.md reoberta el 25/10/2026 (negre quiet a l'inici i al final, en espera; silenci
a l'inici i al final, i "Ajustar a la música" que respecti les durades fetes a mà: pendents).
Decisions de l'usuari del 21/10/2026: decisió 0007 (D12, llindar de 5 fotos, textos d'error del B10).
Decisions del B5 aprovades (docs/sessions/B05.md); la nitidesa de la miniatura EXIF es revisa amb fotos reals
a Windows (vegeu docs/sessions/B10.md).
Decidit el 23/10/2026 (decisió 0010, aplicat al B15): cancel·lar una importació conserva les fotos ja llegides, una
còpia de recuperació per finestra, versió 0.5.0 i els `.pmk` sense doble clic (la P6 continua fora del pla).
Decidit el 23/10/2026 (pendent del B11 i desviacions del B14): la interfície pot fer servir `timeline`, `audio` i
`ffmpeg` (CONTRACTES §13, ampliat), i el pas del retall de les cançons és `defaults.SONG_TRIM_STEP_S`. Prova manual del B11 a
Windows feta el 23/10/2026 amb el ZIP del B12: correcta.
Prova manual del B13 a Windows feta el 23/10/2026: correcta (la fosa amb Bluetooth i l'arrossegament de fotos, al M04).
ZIP portable (B12): la CI el genera a cada PR, fusió a main i etiqueta (artefacte PassiMaker-<versió>-win64; vegeu
docs/sessions/B12.md). Etiqueta `v0.5-mvp` per a la F3: la posa l'usuari al commit `a96edd6` (docs/sessions/B15.md).
Prova manual del B14 a Windows feta el 24/10/2026: correcta; tres millores a la llista de docs/proves_usuari.md.
B15: registre a `%LOCALAPPDATA%\PassiMaker\logs`. Mesures de 1.000 fotos al PC de referència (el sobretaula de l'usuari,
D9: i7-6700K, GTX 960, 40 GB) fetes el 24/10/2026 (PR #46): importar 76 s, memòria màxima 835 MB, exportar 1,17 × la
durada; totes dins dels límits (docs/RENDIMENT.md).
**Música de YouTube (versió 1.2.0 prevista)**: pla aprovat per l'usuari el 25/10/2026 (docs/PLA_YOUTUBE.md, blocs
C01–C06, seguiment al §4.1; decisió 0012). Blocs integrats a main: C01 decisió, contractes (CONTRACTES §15) i
especificació (§1.7 bis) (PR #52, commit `7f1bc0b`) · C04 conversió a MP3, `ffmpeg.convert_to_mp3` (PR #54, commit
`5c2129b`) · C02 viabilitat (PR #57, commit `1599fb7`, docs/sessions/C02.md): yt-dlp 2026.10.21, `yt-dlp-ejs` 0.8.0 i Deno 2.9.8
(paquet `deno` de PyPI) a `uv.lock`, ZIP de prova `ProvaYoutube-win64` (128,9 MB) a la CI; prova al PC de l'usuari
el 25/10/2026, a la xarxa de casa: correcta, sense consola ni avisos de l'antivirus; a la xarxa de l'estudi no es
prova (decisió de l'usuari, 25/10/2026). Al C03, preferir l'àudio estèreo (yt-dlp tria un 5.1 amb Deno). Següent: C03. Tota la xarxa, només a `passimaker.youtube` i mai abans de l'avís.
**Gravar el so de l'ordinador** (ampliació aprovada el 25/10/2026, també a la versió 1.2.0): annex docs/PLA_GRAVACIO.md
(decisions G1–G9: sense avís, gravacions interrompudes o de més de 30 min esborrades, ones per canal, micròfon opcional),
blocs C07–C10 i C06 conjunt al §4 de docs/PLA_YOUTUBE.md. Següent: C07 i C08 en paral·lel (i el C03).
Per reobrir un bloc tancat: vegeu "Com reobrir" a docs/sessions/BNN.md.
