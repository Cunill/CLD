# Rendiment de PassiMaker

Mesures del bloc B15 (23/10/2026) amb **1.000 fotos sintètiques de 24 MP**: 950 JPEG de 6000×4000 i 50 HEIC
(1 de cada 20), sense miniatura EXIF (el cas més lent). Les generen `tests/perf/mesura_1000.py`, que també fa les
mesures, cadascuna en un procés propi. Prova: `uv run pytest -m perf tests/perf/test_thousand_photos.py -s`.

**On s'ha mesurat:** Linux, sessió al núvol, 4 nuclis, 15 GB de memòria. **Falta el PC de referència** (Windows,
4 nuclis, gràfics integrats): vegeu "Pendent".

## Resum

| Criteri (PLA, B15) | Límit | Abans | Després |
|---|---|---|---|
| Importar 1.000 fotos amb totes les miniatures | < 2 min | 92,7 s | 92,7 s (no ha canviat) |
| Memòria màxima en exportar 1.000 fotos | < 1,5 GB (1.536 MB) | **1.594 MB** ❌ | **1.254 MB** ✅ |
| Temps d'exportació (decisió 0008) | ≤ 3 × la durada | — | 1,49 × (1.000 s de vídeo en 1.492 s) |

## Importació
Ordre: `uv run python -m tests.perf.mesura_1000 importar <carpeta>`. El mateix que fa la finestra: llegir les
capçaleres, afegir les fotos al projecte (amb el sorteig dels moviments) i demanar totes les miniatures.

| Pas | Temps acumulat |
|---|---|
| Capçaleres de les 1.000 fotos | 0,65 s |
| Afegides al projecte | 0,94 s |
| L'última miniatura | **92,7 s** |

- Memòria màxima del procés: 1.056 MB (la memòria cau d'imatges de la finestra, 768 MB, és plena).
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
- **Repetir-ho al PC de referència** (Windows): `uv run pytest -m perf tests/perf/test_thousand_photos.py -s`
  (generar les fotos, uns 2 min; importar, uns 2 min; exportar, uns 25 min a Linux). Els resultats s'afegeixen a
  `tests/_artefactes/rendiment/mil_fotos.txt`; copiar-los en aquest document.
- Amb fotos reals: HEIC d'iPhone (miniatura incrustada) i JPEG de càmera (miniatura EXIF).
