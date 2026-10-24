# Rendiment de PassiMaker

Mesures del bloc B15 (23/10/2026) amb **1.000 fotos sintètiques de 24 MP**: 950 JPEG de 6000×4000 i 50 HEIC
(1 de cada 20), sense miniatura EXIF (el cas més lent). Les generen `tests/perf/mesura_1000.py`, que també fa les
mesures, cadascuna en un procés propi. Prova: `uv run pytest -m perf tests/perf/test_thousand_photos.py -s`.

**On s'ha mesurat:**
- **Linux**, sessió al núvol, 4 nuclis, 15 GB de memòria (23/10/2026, B15): columnes "Abans" i "Després".
- **PC de referència (Windows)** (24/10/2026, decisió D9): Windows 10 Pro, Intel Core i7-6700K (4 nuclis, 8 fils,
  4 GHz), 40 GB de memòria, NVIDIA GeForce GTX 960. Amb el codi de `main` (el de "Després"), sense fer servir el PC
  mentre es mesurava.

## Resum

| Criteri (PLA, B15) | Límit | Linux, abans | Linux, després | PC de referència (Windows) |
|---|---|---|---|---|
| Importar 1.000 fotos amb totes les miniatures | < 2 min | 92,7 s | 92,7 s (no ha canviat) | **76,2 s** ✅ |
| Memòria màxima en exportar 1.000 fotos | < 1,5 GB (1.536 MB) | **1.594 MB** ❌ | **1.254 MB** ✅ | **835 MB** ✅ |
| Temps d'exportació (decisió 0008) | ≤ 3 × la durada | — | 1,49 × (1.000 s de vídeo en 1.492 s) | **1,17 ×** (1.000 s de vídeo en 1.170 s) ✅ |

## Importació
Ordre: `uv run python -m tests.perf.mesura_1000 importar <carpeta>`. El mateix que fa la finestra: llegir les
capçaleres, afegir les fotos al projecte (amb el sorteig dels moviments) i demanar totes les miniatures.

| Pas | Temps acumulat (Linux) | Temps acumulat (PC de referència) |
|---|---|---|
| Capçaleres de les 1.000 fotos | 0,65 s | 0,53 s |
| Afegides al projecte | 0,94 s | 0,81 s |
| L'última miniatura | **92,7 s** | **76,2 s** |

- Memòria màxima del procés: 1.056 MB a Linux i 961 MB al PC de referència (la memòria cau d'imatges de la
  finestra, 768 MB, és plena).
- Generar les 1.000 fotos de prova: 14,4 s al PC de referència.
- **On va el temps:** una JPEG de 24 MP es descodifica a 1/8 en 66 ms; una HEIC de 24 MP no es pot descodificar a
  mida reduïda i triga **2,5 s**. Les 50 HEIC són uns 60 dels 93 s (2 fils de miniatures).
- **Millora possible (no feta):** els HEIC dels mòbils porten una miniatura incrustada, que pillow-heif pot fer
  servir (`Image.draft`). No es pot provar aquí (pillow-heif 1.8 no en pot escriure cap i no hi ha fotos reals
  d'iPhone). Es proposa per al B16.

## Exportació
Ordre: `uv run python -m tests.perf.mesura_1000 exportar <carpeta> <video.mp4> [--fotos N]`. Projecte amb totes les
fotos, 1 s per foto (el mínim) i fosa de 0,5 s; sense música. Memòria: el màxim de memòria resident del procés
(`ru_maxrss`; a Windows, `PeakWorkingSetSize`). FFmpeg és un procés a part i no compta en el límit.

| Mesura | Fotos | Memòria màxima | Temps | × durada | FFmpeg |
|---|---|---|---|---|---|
| Abans | 1.000 | **1.594 MB** (aturada als 6 min: ja passava del límit) | — | — | — |
| Abans | 100 | 1.497 MB | 149 s | 1,49 | 663 MB |
| Després | 100 | 1.114 MB | 153 s | 1,53 | 651 MB |
| **Després** | **1.000** | **1.254 MB** | **1.492 s** | **1,49** | 658 MB |
| **PC de referència (Windows)** | **1.000** | **835 MB** | **1.170 s** | **1,17** | — (no es pot mesurar a Windows) |

**Al PC de referència**, una primera passada amb el mateix codi va donar 1.059 s (1,06 ×) i 75,0 s d'importació,
però la memòria va sortir a 0 MB: `peak_memory_bytes()` (`tests/perf/mesura_1000.py`) no declarava els tipus de
ctypes, la crida a `GetProcessMemoryInfo` fallava sense avís i la prova del límit passava sense mesurar res.
Corregit com al B13 (`tests/unit/preview/test_memory.py`): tipus declarats i error si la crida falla. Les xifres
de la taula són de la segona passada, amb la correcció.

**Coll d'ampolla trobat:** l'exportació feia servir una memòria cau d'imatges com la de la finestra (768 MB) a més
dels llenços del compositor (192 MB), i alhora descodificava fotos de 24 MP (una HEIC sencera, uns 70 MB, més les
còpies intermèdies). L'exportació recorre les fotos en ordre i només necessita les visibles i les 2 següents.
**Correcció:** la seva memòria cau d'imatges és ara de **384 MB** (`export.params.IMAGE_MEMORY_BYTES`). No alenteix
l'exportació (no torna a descodificar fotos). La finestra conserva els 768 MB.

## Altres mesures (blocs anteriors)
| Què | Resultat | On |
|---|---|---|
| 1.000 miniatures (12 MP, amb miniatura EXIF), primera vegada | ~36 s a la CI de Windows (límit 60 s) | B5 |
| Compositor, temps per imatge | ≤ 35 ms a 1080p, ≤ 15 ms a 960×540 | B6 |
| Exportació (20 fotos, 40 s de vídeo) | 1,5 × la durada a la CI de Windows | B9, decisió 0008 |
| Anar a una foto de 1.000 a la previsualització | < 300 ms | B13 |

## Pendent
- Per repetir les mesures: `uv run pytest -m perf tests/perf/test_thousand_photos.py -s` (uns 21 min al PC de
  referència). Els resultats s'afegeixen a `tests/_artefactes/rendiment/mil_fotos.txt`; copiar-los en aquest document.
- Amb fotos reals: HEIC d'iPhone (miniatura incrustada) i JPEG de càmera (miniatura EXIF).
