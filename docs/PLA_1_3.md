# PassiMaker: pla de la versió 1.3.0 (millores de l'usuari)

> Millores demanades per l'usuari el 29/10/2026, durant i després de la prova del ZIP 1.2.0.
> Versió del pla: 1.1 · Data: 30/10/2026 (afegit el M13) · Estat: **aprovat per l'usuari el 29/10/2026** (decisions al §0)
> Versió del programa prevista: **1.3.0** · Blocs de manteniment M07–M13 (el protocol del CLAUDE.md, com sempre).

---

## 0. Decisions de l'usuari (29/10/2026)

| # | Tema | Decisió |
|---|---|---|
| 1 | Imatges negres (millora 5 de `docs/proves_usuari.md`) | **Dues fitxes negres al tauler de fotos**, la primera i l'última, cadascuna amb la seva durada (per defecte 2 s). Es queden fixes en aquesta posició; es poden esborrar i tornar a afegir |
| 2 | Proporcions | Forma del **vídeo exportat**: 16:9 (1920×1080), 3:2 (1620×1080) i 4:3 (1440×1080), horitzontals; el vertical 9:16 (1080×1920) continua |
| 3 | Marge de la previsualització | El de **sota de la previsualització** (entre la previsualització i el panell de propietats): que es vegi i es pugui arrossegar amunt i avall amb un recorregut ample |
| 4 | Ordre aleatori | Un **botó que barreja les fotos un cop**; cada vegada que es prem, torna a barrejar. Les fitxes negres no es mouen. Es pot desfer |
| 5 | Ajustar a la música (millora 7) | Les fotos amb la **durada posada a mà no es toquen**; la resta de la música es reparteix entre les altres, en **0,4–24 s**. Si totes tenen durada a mà, no fa res i avisa |
| 6 | Començar | **Ara** (29/10/2026) |
| 7 | Silenci a l'inici i al final de la música (millora 6) | **Afegit al pla 1.3.0 com a bloc M13** (30/10/2026): X segons de silenci abans de la música i Y després, opcionals i independents de les fitxes negres; "Ajustar a la música" els té en compte. Comença quan el M07 i el M08 siguin a `main`, en paral·lel amb el M09 i el M10 |

---

## 1. Blocs

| Bloc | Nom | Mòduls | Mida | Depèn de | Model | On |
|---|---|---|---|---|---|---|
| M07 | "Ajustar a la música": durades fetes a mà fixes i 0,4–24 s | `timeline`, `model`, `ui` (avís) | Petit | — | Sonnet | Núvol |
| M08 | Imatges negres d'inici i final | `model`, `timeline`, `render`, `projectio`, `ui` | Mitjà | — | Opus | Núvol |
| M09 | Ordre aleatori | `model`, `ui` | Petit | M08 | Sonnet | Núvol |
| M10 | Proporcions 4:3, 3:2 i 16:9 | `model`, `motion`, `render`, `export`, `preview`, `ui` | Gran | M08 | Opus | Núvol |
| M11 | Marge de la previsualització ajustable | `ui` | Petit | — | Sonnet | Núvol |
| M12 | ZIP, guia, CHANGELOG, prova de l'usuari i publicar la `v1.3` | paquet, `ui/help.py`, documentació | Petit | M07–M11, M13 | Sonnet | Núvol + **local** |
| M13 | Silenci a l'inici i al final de la música | `model`, `timeline`, `audio`, `projectio`, `ui` | Mitjà | M07, M08 | Opus | Núvol |

### 1.1 Seguiment: estimació i consum

| Bloc | Estat | Model recomanat | Depèn de | En paral·lel amb | Tanda | Sessions estimades (opt. / prob. / pes.) | Temps teu estimat (h) | Sessions consumides | Temps teu consumit (h) | PR · commit |
|---|---|---|---|---|---|---|---|---|---|---|
| Pla (aquest document) | ✅ aprovat el 29/10/2026 (M13 afegit el 30/10/2026) | Opus | — | — | — | — | — | 1 | — | PR #91 (el pla) · `9df0171`; PR #92 (el M13) · `270cedc` |
| M07 Ajustar a la música | ✅ tancat: fusionat a `main` el 30/10/2026 (prova manual encara no confirmada) | Sonnet | — | **M08**, **M11** | T1 | 1 / 1 / 1 | 0,25 | 1 | — | PR #93 (l'ajust a la música) · `18030c1` (CI de Windows en verd) · decisió 0014 · **prova manual de l'usuari pendent** (6 passos a docs/sessions/M07.md; es pot fer amb el ZIP de la CI o amb el de la v1.3) |
| M08 Imatges negres | ✅ fusionat a `main` el 30/10/2026; pendent de la prova manual de l'usuari (docs/sessions/M08.md) | Opus | — | **M07**, **M11** | T1 | 1 / 1 / 2 | 0,5 | 1 | — | PR #95 (les fitxes negres) · `4e24694` (CI de Windows en verd) |
| M09 Ordre aleatori | ✅ fet a la PR #98 (pendent de fusionar i de la prova manual) | Sonnet | M08 | **M10**, **M13** | T2 | 1 / 1 / 1 | 0,25 | — | — | — |
| M10 Proporcions | 🔧 PR #99 oberta (branca `ccr-ad368bc5-c6nhgt`), pendent de la CI, la fusió i la prova manual de l'usuari (docs/sessions/M10.md); **sis formats** (16:9, 3:2 i 4:3, horitzontals i verticals; decisió de l'usuari del 30/10/2026) | Opus | M08 | **M09**, **M13** | T2 | 1 / 2 / 2 | 0,75 | 1 | — | — |
| M11 Marge de la previsualització | ✅ fusionat a `main` el 30/10/2026; pendent de la prova manual de l'usuari (docs/sessions/M11.md) | Sonnet | — | **M07**, **M08** | T1 | 1 / 1 / 1 | 0,25 | 1 | — | PR #94 (el marge ajustable) · `44fd44d` |
| M12 Versió 1.3.0 | ⏳ pendent | Sonnet | M07–M11, M13 | — | T3 | 1 / 1 / 1 | 1,0 | — | — | — |
| M13 Silenci a l'inici i al final de la música | ⏳ pendent (es pot començar) | Opus | M07, M08 | **M09**, **M10** | T2 | 1 / 1 / 2 | 0,5 | — | — | — |
| **Subtotal dels blocs** | | | | | | **7 / 8 / 10** | **3,5** | **3** | **—** | |
| Correccions després de la prova de l'usuari | ⏳ pendent | Sonnet | M12 | — | després del M12 | 0 / 1 / 2 | inclòs a sota | — | — | — |
| Revisió de les PR i prova final de l'usuari | ⏳ pendent | — | — | — | totes | — | 1 / 2 / 4 | — | — | — |
| **Total** | | | | | | **7 / 9 / 12 sessions** | **4,5 / 5,5 / 7,5 h** | **4** (el pla + 3) | **—** | |

Llegenda de l'estat: ⏳ pendent · 🔧 en curs · ✅ tancat (fusionat a `main`) · ⛔ aturat.

**Tandes.** T1: M07, M08 i M11 alhora (toquen parts diferents; comparteixen `defaults.py`, `model/editing.py` i
`ui/main_window.py` en funcions diferents: el que es fusiona segon porta `main` a la seva branca i resol). T2: M09 i M10,
quan el M08 sigui a `main` (totes dues han de tenir en compte les fitxes negres), i el M13 quan el M07 i el M08
hi siguin (toca "Ajustar a la música" del M07 i el format del `.pmk` del M08; amb el M10 comparteix `projectio`, en
camps diferents). T3: M12.

**Fitxers compartits del seguiment:** la taula del §1.1 i l'apartat Estat del CLAUDE.md. Cada bloc hi escriu només la
seva fila i la seva línia.

### 1.2 Proves manuals de l'usuari (Windows)

| Prova | Estat | Passos | Ajornable? | Quan es fa |
|---|---|---|---|---|
| M07 Ajustar a la música | ⏳ pendent | 6 (docs/sessions/M07.md) | Sí | Amb el ZIP 1.3.0, al M12 (o abans amb el ZIP de la CI de `main`) |
| M08 Imatges negres | ⏳ pendent | 10 (docs/sessions/M08.md) | Sí | Amb el ZIP 1.3.0, al M12 |
| M11 Marge de la previsualització | ⏳ pendent | 6 (docs/sessions/M11.md) | Sí | Amb el ZIP 1.3.0, al M12 |
| M09 Ordre aleatori | ⏳ pendent (bloc per fer) | a docs/sessions/M09.md | Sí | Amb el ZIP 1.3.0, al M12 |
| M10 Proporcions | ⏳ pendent (bloc per fer) | a docs/sessions/M10.md | Sí | Amb el ZIP 1.3.0, al M12 |
| M13 Silenci de la música | ⏳ pendent (bloc per fer) | a docs/sessions/M13.md | Sí | Amb el ZIP 1.3.0, al M12 |
| Prova final de la versió 1.3.0 | ⏳ pendent | al M12 | **No** (cal abans de publicar la `v1.3`) | M12 |

Cap bloc depèn de la prova manual d'un altre: les proves automàtiques i la CI de Windows ja hi passen. Fer-les totes
juntes al M12 estalvia temps; el risc és que un error trobat tard demani una correcció (fila "Correccions després de la
prova de l'usuari").

---

## 2. Fitxes i prompts

### M07 · "Ajustar a la música": durades fetes a mà fixes i 0,4–24 s

```text
Bloc M07: "Ajustar a la música" respecta les durades fetes a mà, rang 0,4–24 s. Model: Sonnet.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M08 (imatges negres) i el M11 (marge de la previsualització), en altres
sessions. No facis res fora d'aquest bloc: modifica només els fitxers permesos de sota, encara que vegis errors o millores
en d'altres (anota-les a docs/sessions/M07.md). A la taula del §1.1 de docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md,
escriu només la fila i la línia del M07; si en acabar un altre bloc ja és a main, porta main a la teva branca (fusió,
sense reescriure la història) i resol el conflicte conservant els canvis de l'altre bloc.
Context: v1.2.0 publicada. Llegeix docs/PLA_1_3.md (§0, decisió 5), docs/proves_usuari.md (millora 7),
docs/decisions/0005-durades-curtes-i-moviment-ajustable.md i 0011-durada-0-4-24-i-nou-moviment.md, docs/ESPECIFICACIO.md
§1.7 ("Ajustar a la música"), src/passimaker/timeline/fit.py i types.py, src/passimaker/model/editing.py (fit_to_music,
_keep_fitted), src/passimaker/model/defaults.py, src/passimaker/ui/duration_status.py, ui/dialogs.py (fit_question) i
ui/main_window.py (fit_to_music), i les proves que en depenen (tests/unit/timeline/test_fit.py,
tests/unit/model/test_commands.py, tests/unit/test_contracts.py, tests/ui/test_music.py). Hi ha un esborrany aturat al
commit 0d4a10f (branca ccr-08701f22-8ayer4) que només canviava el límit a 1–24 s: mira'l com a referència, no el copiïs.
Branca: bloc/M07-ajustar-musica des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Fes:
1. defaults.FIT_TO_MUSIC_DURATION_RANGE = 0,4–24 s (el mateix que PHOTO_DURATION_RANGE). Comprova que el moviment i la
   fosa ja suporten 0,4 s (decisió 0011).
2. timeline.fit_to_music: accepta quines durades són fixes (p. ex. un paràmetre `fixed`); les fixes no canvien, es resten
   de la música, i la resta es reparteix entre les altres amb les proporcions i els límits de sempre. Si totes són fixes,
   o la música no arriba a cobrir les fixes, no canvia res i ho indica al FitResult.
3. model.editing.fit_to_music i _keep_fitted: fixes = fotos amb duration_s posat a mà (les "per defecte" s'ajusten).
   Qualsevol element amb una durada pròpia (com les fitxes negres del M08) també compta com a fix: escriu-ho de manera
   que no calgui saber si és una foto o una altra cosa.
4. Avís quan totes les fotos tenen durada a mà (text en català, traduïble, a ui/duration_status.py o ui/dialogs.py) i
   avís de música massa llarga o curta amb els nous límits; cap text de la interfície ha de parlar d'1–3 s.
5. Decisió 0014 (docs/decisions/0014-ajustar-a-la-musica.md): fixes i 0,4–24 s; nota a la 0011. ESPECIFICACIO §1.7 al dia.
6. Proves: Hypothesis per a fit_to_music amb fixes (les fixes no canvien, la suma arriba a la música quan es pot,
   proporcions entre les lliures, cas "totes fixes"); controlador; avís de la interfície. Les proves de l'algorisme poden
   passar límits explícits; no afebleixis cap prova.
7. docs/proves_usuari.md: millora 7 "Fet (M07)". docs/sessions/M07.md. La fila del M07 a docs/PLA_1_3.md §1.1 i una línia
   a l'Estat del CLAUDE.md.
Criteris d'acceptació: decisió 5 del pla complerta; suite ràpida, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: src/passimaker/timeline/fit.py i types.py, src/passimaker/model/editing.py (només l'ajust a la música),
src/passimaker/model/defaults.py (només el rang), src/passimaker/ui/duration_status.py, ui/dialogs.py i ui/main_window.py
(només l'ajust a la música), src/passimaker/i18n (si cal un missatge), les proves esmentades i les noves de l'ajust,
docs/decisions/0011 i 0014, docs/ESPECIFICACIO.md §1.7, docs/proves_usuari.md (millora 7), docs/sessions/M07.md, la fila
del M07 a docs/PLA_1_3.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre, atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md. A docs/sessions/M07.md, la prova manual que l'usuari ha de fer (un pas cada vegada).
```

### M08 · Imatges negres d'inici i final

```text
Bloc M08: dues fitxes negres, a l'inici i al final del passi. Model: Opus.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M07 (ajustar a la música) i el M11 (marge de la previsualització), en
altres sessions. No facis res fora d'aquest bloc: modifica només els fitxers permesos de sota, encara que vegis errors o
millores en d'altres (anota-les a docs/sessions/M08.md). No toquis timeline/fit.py ni l'ajust a la música (són del M07):
n'hi ha prou que les fitxes negres tinguin una durada pròpia, que el M07 tractarà com a fixa. A la taula del §1.1 de
docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i la línia del M08; si en acabar un altre bloc ja
és a main, porta main a la teva branca (fusió, sense reescriure la història) i resol el conflicte conservant els canvis de
l'altre bloc.
Context: v1.2.0 publicada. Llegeix docs/PLA_1_3.md (§0, decisió 1), docs/proves_usuari.md (millora 5),
docs/ESPECIFICACIO.md (§1.2 storyboard, §1.4 fosa, §1.10 desar), docs/CONTRACTES.md (§1 model, §5 línia de temps, §7
compositor, §12 desar i obrir), src/passimaker/model/ (types, commands, controller, editing, defaults),
src/passimaker/timeline/build.py, src/passimaker/render/compositor.py, src/passimaker/projectio/,
src/passimaker/ui/storyboard.py, ui/photos.py, ui/photo_panel.py i ui/main_window.py.
Branca: bloc/M08-imatges-negres des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: un projecte nou té, per defecte, una fitxa negra al principi i una al final del tauler, cadascuna amb la seva
durada (defaults.BLACK_SLIDE_DURATION_S = 2,0, dins de PHOTO_DURATION_RANGE). Es queden sempre la primera i l'última:
afegir, moure, ordenar o duplicar fotos no les desplaça, i no es poden arrossegar a dins del passi. Es poden esborrar
(Supr, com una foto) i tornar a afegir des del menú ("Afegeix negre a l'inici" / "al final"), i es pot canviar la seva
durada. Es dibuixen negres al compositor (previsualització i exportació, regla 3), amb les foses de sempre amb la foto
del costat, sense moviment ni encaix. Desfer/refer funciona com sempre.
Fes:
1. Proposa primer el model a docs/sessions/M08.md (p. ex. un tipus d'element al costat de Photo, o un camp a Project) i
   el canvi de contracte (CONTRACTES §1, §5, §7, §12), i atura't perquè l'usuari ho aprovi. És un canvi de contracte.
2. Quan s'aprovi: model, ordres i controlador; línia de temps; compositor; desar i obrir amb format_version 2: un .pmk de
   la versió 1 s'obre sense fitxes negres (no se n'hi afegeixen) i es desa ja en versió 2; tauler de fotos (fitxa negra
   amb la durada, sense miniatura de foto); menú per tornar-les a afegir; propietats de la fitxa (només la durada).
3. Proves: model (posicions fixes en afegir, moure, ordenar, duplicar, esborrar i tornar a afegir; desfer/refer),
   línia de temps (durades i foses), compositor (fotogrames negres), desar/obrir (versió 1 i 2), interfície (pytest-qt).
4. ESPECIFICACIO (on toqui), CONTRACTES, docs/proves_usuari.md (millora 5 "Fet (M08)"), docs/sessions/M08.md, la fila
   del M08 a docs/PLA_1_3.md §1.1 i una línia a l'Estat del CLAUDE.md.
Criteris d'acceptació: decisió 1 del pla complerta; un .pmk antic s'obre igual que abans; suite ràpida, ruff i pyright en
verd; cap dependència nova.
Fitxers permesos: src/passimaker/model/ (excepte l'ajust a la música d'editing.py), timeline/build.py i types.py (excepte
fit), render/, projectio/, ui/storyboard.py, ui/photos.py, ui/photo_panel.py, ui/properties.py, ui/main_window.py (només
el menú de les fitxes negres), i18n, les proves de tot això, docs/CONTRACTES.md, docs/ESPECIFICACIO.md,
docs/proves_usuari.md (millora 5), docs/sessions/M08.md, la fila del M08 a docs/PLA_1_3.md i l'apartat Estat del
CLAUDE.md. Si cal tocar-ne cap altre, atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md (i la del punt 1). A docs/sessions/M08.md, la prova manual que l'usuari ha de fer.
```

### M09 · Ordre aleatori

```text
Bloc M09: botó per barrejar les fotos a l'atzar. Model: Sonnet.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M10 (proporcions) i el M13 (silenci de la música), en altres sessions. No facis res fora d'aquest bloc:
modifica només els fitxers permesos de sota, encara que vegis errors o millores en d'altres (anota-les a
docs/sessions/M09.md). A la taula del §1.1 de docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i
la línia del M09; si en acabar un altre bloc ja és a main, porta main a la teva branca (fusió, sense reescriure la
història) i resol el conflicte conservant els canvis de l'altre bloc.
Context: M07, M08 i M11 a main (commit 4e24694). Les fitxes negres del M08 són elements de Project.slides; Project.photos
és derivat i dataclasses.replace(project, photos=…) dona ValueError (cal _with_photos o slides=). Llegeix
docs/sessions/M08.md ("Per als altres blocs"), docs/PLA_1_3.md (§0, decisió 4), src/passimaker/model/commands.py
(SortPhotos), model/editing.py (com s'aplica SortPhotos, _with_photos, la llavor `seed`), ui/main_window.py (accions
"Ordenar per data" i "Ordenar per nom", menú i barra d'eines) i les proves que en depenen (tests/unit/model/
test_commands.py, tests/unit/model/test_black_slides.py, tests/ui/test_window.py o la de les accions d'ordenar).
Branca: bloc/M09-ordre-aleatori des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: una acció "Barreja les fotos" (al costat de les d'ordenar, al menú i amb un botó visible al tauler o a la barra
d'eines) que canvia l'ordre de totes les fotos a l'atzar. Cada vegada que es prem dona un ordre nou; les fitxes negres no
es mouen; un sol pas de desfer/refer; desactivada amb menys de dues fotos. Determinisme (regla 5): l'ordre surt de la
llavor del projecte i de l'ordre actual (p. ex. random.Random amb una clau feta de `seed` i dels identificadors en
l'ordre actual), de manera que el mateix projecte barrejat dona sempre el mateix resultat, sense camps nous ni canvi de
format del .pmk. Si veus que cal un camp nou o canviar un contracte, atura't i proposa-ho.
Fes: ordre nova ShufflePhotos al controlador (model/commands.py, model/editing.py, model/__init__.py); l'acció i el botó
a ui/main_window.py (tr, en català); proves (ordre diferent, mateixes fotos, fitxes negres al lloc, determinisme,
desfer/refer, Hypothesis si cal; pytest-qt per a l'acció); docs/ESPECIFICACIO.md (on hi ha "ordenar"), docs/CONTRACTES.md
(l'ordre nova), docs/sessions/M09.md, la fila del M09 a docs/PLA_1_3.md §1.1 i una línia a l'Estat del CLAUDE.md.
Criteris d'acceptació: decisió 4 del pla complerta; suite ràpida (i `-m "not perf"` abans de pujar), ruff i pyright en
verd; cap dependència nova.
Fitxers permesos: model/commands.py, model/editing.py (només l'ordre nova), model/__init__.py, ui/main_window.py (només
l'acció i el botó), i18n, les proves de tot això, docs/ESPECIFICACIO.md, docs/CONTRACTES.md (l'ordre nova),
docs/sessions/M09.md, la fila del M09 a docs/PLA_1_3.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre,
atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md. A docs/sessions/M09.md, la prova manual que l'usuari ha de fer (un pas cada vegada).
```

### M10 · Proporcions 4:3, 3:2 i 16:9

```text
Bloc M10: el vídeo es pot exportar en 16:9, 3:2, 4:3 (horitzontals) o 9:16 (vertical). Model: Opus.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M09 (ordre aleatori) i el M13 (silenci de la música), en altres sessions. No facis res fora d'aquest bloc:
modifica només els fitxers permesos de sota, encara que vegis errors o millores en d'altres (anota-les a
docs/sessions/M10.md). A la taula del §1.1 de docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i
la línia del M10; si en acabar un altre bloc ja és a main, porta main a la teva branca (fusió, sense reescriure la
història) i resol el conflicte conservant els canvis de l'altre bloc.
Context: M07, M08 i M11 a main (commit 4e24694). Les fitxes negres del M08 són elements de Project.slides; Project.photos
és derivat i dataclasses.replace(project, photos=…) dona ValueError (cal _with_photos o slides=). Llegeix
docs/sessions/M08.md ("Per als altres blocs"), docs/PLA_1_3.md (§0, decisió 2), docs/CONTRACTES.md, docs/ESPECIFICACIO.md (format de sortida),
src/passimaker/model/types.py (OutputFormat i size), motion/geometry.py (output_aspect, resolve_fit, base_window),
motion/draw.py, render/canvas.py, export/pipeline.py (mida de sortida), importer/photo.py, projectio/__init__.py,
ui/project_panel.py (_FORMATS, selector), ui/main_window.py i ui/player_panel.py (on la previsualització fa servir la
proporció), cli.py, i les proves que en depenen (cerca OutputFormat a tests/).
Branca: bloc/M10-proporcions des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: quatre formats de sortida: 16:9 (1920×1080, l'actual HORIZONTAL), 3:2 (1620×1080), 4:3 (1440×1080) i 9:16
(1080×1920, l'actual VERTICAL). Moviment, encaix (omplir o sencera amb franges), compositor, exportació (FFmpeg, 30 fps),
previsualització i selector de la interfície funcionen amb tots quatre. Els .pmk antics s'obren igual: "horizontal" →
16:9 i "vertical" → 9:16. Les fitxes negres (M08) no tenen mida ni encaix.
Fes:
1. Proposa primer el canvi de contracte a docs/sessions/M10.md (valors nous d'OutputFormat i noms al .pmk, si cal
   format_version 3 o només valors nous, com ho veuen els .pmk antics i la 1.2.0) i atura't perquè l'usuari ho aprovi.
2. Quan s'aprovi: model, motion, compositor, exportació, desar/obrir, previsualització, selector (tr, en català) i
   passimaker-nou (opció del format, si ja n'hi ha). Comprova les mides parells per a l'H.264 i que les imatges golden
   no canvien en 16:9 (no les regeneris sense permís explícit; si cal golden nous per als formats nous, demana-ho).
3. Proves: mides i proporcions, encaix i moviment (Hypothesis, finestres dins de 0–1), compositor sense magenta ni vores
   en els quatre formats, exportació curta en 3:2 i 4:3 (marca lent si cal), desar/obrir (antics i nous), interfície.
4. docs/CONTRACTES.md, docs/ESPECIFICACIO.md, docs/sessions/M10.md, la fila del M10 a docs/PLA_1_3.md §1.1 i una línia a
   l'Estat del CLAUDE.md. Recorda que el "Què és" del CLAUDE.md diu "1920×1080 o 1080×1920": proposa'n el canvi a la
   nota de sessió (el fa el M12).
Criteris d'acceptació: decisió 2 del pla complerta; un .pmk antic s'obre igual; 16:9 i 9:16 donen el mateix vídeo que
abans; suite ràpida i `-m "not perf"`, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: model/types.py, model/defaults.py (si cal), model/__init__.py, motion/, render/, export/, importer/photo.py,
projectio/, preview/ (només la proporció), ui/project_panel.py, ui/player_panel.py i ui/main_window.py (només el que
depèn del format), cli.py (només el format), i18n, les proves de tot això, docs/CONTRACTES.md, docs/ESPECIFICACIO.md,
docs/sessions/M10.md, la fila del M10 a docs/PLA_1_3.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre,
atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md (i la del punt 1). A docs/sessions/M10.md, la prova manual que l'usuari ha de fer.
```

### M11 · Marge de la previsualització ajustable

```text
Bloc M11: el marge de sota de la previsualització es pot arrossegar amunt i avall. Model: Sonnet.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M07 i el M08, en altres sessions. No facis res fora d'aquest bloc:
modifica només els fitxers permesos de sota (anota la resta a docs/sessions/M11.md). A la taula del §1.1 de
docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i la línia del M11; si en acabar un altre bloc ja
és a main, porta main a la teva branca (fusió, sense reescriure la història) i resol el conflicte conservant els canvis
de l'altre bloc.
Context: v1.2.0 publicada. Llegeix docs/PLA_1_3.md (§0, decisió 3), src/passimaker/ui/main_window.py (_build_layout: el
QSplitter vertical `left` amb player_panel i properties), ui/player_panel.py (mida mínima) i ui/properties.py, i les proves
de la finestra (tests/ui/test_window.py).
Branca: bloc/M11-marge-previsualitzacio des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: la línia entre la previsualització i el panell de propietats es veu (més gruixuda, amb un indicador d'arrossegar
i el cursor ↕) i es pot arrossegar amunt i avall amb un recorregut ample: la previsualització pot arribar a ser petita o
ocupar gairebé tota l'alçada (deixant el mínim útil a les propietats). La posició es recorda entre sessions
(QSettings), i un doble clic a la línia la torna a la posició per defecte. Investiga primer per què ara costa de moure
(mida mínima, factors d'estirament, mida de la línia) i anota-ho a docs/sessions/M11.md.
Fes: el canvi a ui/main_window.py (només la disposició) i, si cal, les mides mínimes a ui/player_panel.py i
ui/properties.py; proves pytest-qt (arrossegar, límits, recordar, doble clic); docs/sessions/M11.md; la fila del M11 a
docs/PLA_1_3.md §1.1 i una línia a l'Estat del CLAUDE.md.
Criteris d'acceptació: decisió 3 del pla complerta; suite ràpida, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: ui/main_window.py (només _build_layout i el que calgui per recordar la posició), ui/player_panel.py i
ui/properties.py (només mides mínimes), tests/ui/test_window.py o una prova nova, docs/sessions/M11.md, la fila del M11 a
docs/PLA_1_3.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre, atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md. A docs/sessions/M11.md, la prova manual que l'usuari ha de fer (un pas cada vegada).
```

### M13 · Silenci a l'inici i al final de la música

```text
Bloc M13: segons de silenci abans i després de la música, opcionals. Model: Opus.
ATENCIÓ, BLOCS EN PARAL·LEL: es fa alhora que el M09 (ordre aleatori) i el M10 (proporcions), en altres sessions. No facis res fora d'aquest bloc:
modifica només els fitxers permesos de sota, encara que vegis errors o millores en d'altres (anota-les a
docs/sessions/M13.md). A la taula del §1.1 de docs/PLA_1_3.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i
la línia del M13; si en acabar un altre bloc ja és a main, porta main a la teva branca (fusió, sense reescriure la
història) i resol el conflicte conservant els canvis de l'altre bloc.
Context: M07, M08 i M11 a main (commit 4e24694). Les fitxes negres del M08 són elements de Project.slides; Project.photos
és derivat i dataclasses.replace(project, photos=…) dona ValueError (cal _with_photos o slides=). Llegeix
docs/sessions/M08.md ("Per als altres blocs") i docs/sessions/M07.md, docs/PLA_1_3.md (§0, decisió 7), docs/proves_usuari.md (millora 6),
docs/CONTRACTES.md, docs/ESPECIFICACIO.md §1.7 (Música i "Ajustar a la música"), src/passimaker/model/types.py (Music,
Project), model/defaults.py, model/editing.py (music_duration, fit_to_music), timeline/audio_plan.py
(build_audio_plan: avui la música comença a 0), timeline/build.py i fit.py, audio/mixer.py, projectio/__init__.py,
ui/song_panel.py i ui/duration_status.py, i les proves que en depenen (tests/unit/timeline/test_audio_plan.py,
test_fit.py, tests/unit/audio/test_mixer.py, tests/unit/projectio/, tests/ui/test_music.py).
Branca: bloc/M13-silenci-musica des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: dos valors del projecte, X segons de silenci abans que comenci la música i Y segons de silenci després que
acabi, per defecte 0 (com ara), amb el rang a defaults.py. Són independents de les fitxes negres (la música continua
començant a t = X encara que hi hagi negre). "Ajustar a la música" (M07) fa durar el passi X + música + Y. La fosa final
de la música acaba a (durada del passi − Y). Previsualització i exportació amb el mateix pla d'àudio (regla 3). Es poden
canviar a la interfície (al panell de música, amb tr i en català) i es pot desfer.
Fes:
1. Proposa primer el model a docs/sessions/M13.md (on van els dos camps: Music o Project; noms; .pmk: camps nous amb 0
   per als antics, si cal format_version 3, i com es combina amb el M10 si també canvia el format) i el canvi de
   contracte, i atura't perquè l'usuari ho aprovi.
2. Quan s'aprovi: model i ordre nova al controlador; build_audio_plan (desplaçament X i final a total − Y); fit_to_music
   i duration_status; desar/obrir; controls a ui/song_panel.py.
3. Proves: pla d'àudio (inici, final i fosa amb X i Y; música més llarga o més curta que el passi), ajustar a la música
   amb X i Y, mescla (silenci exacte al principi i al final), desar/obrir (antics i nous), interfície (pytest-qt),
   desfer/refer.
4. docs/CONTRACTES.md, docs/ESPECIFICACIO.md §1.7, docs/proves_usuari.md (millora 6 "Fet (M13)"), docs/sessions/M13.md,
   la fila del M13 a docs/PLA_1_3.md §1.1 i una línia a l'Estat del CLAUDE.md.
Criteris d'acceptació: decisió 7 del pla complerta; amb X = Y = 0 el so és idèntic a l'actual; un .pmk antic s'obre
igual; suite ràpida i `-m "not perf"`, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: model/types.py, model/defaults.py, model/commands.py, model/editing.py (música i ajust), model/__init__.py,
timeline/, audio/mixer.py (si cal), projectio/, ui/song_panel.py, ui/duration_status.py, i18n, les proves de tot això,
docs/CONTRACTES.md, docs/ESPECIFICACIO.md, docs/proves_usuari.md (millora 6), docs/sessions/M13.md, la fila del M13 a
docs/PLA_1_3.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre, atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md (i la del punt 1). A docs/sessions/M13.md, la prova manual que l'usuari ha de fer.
```

### M12 · Versió 1.3.0

Prompt: s'escriu quan M07–M11 i el M13 siguin a `main`. ZIP, guia (fitxes negres, barrejar, proporcions), CHANGELOG 1.3.0,
silenci de la música, versió, prova de l'usuari amb el ZIP i publicar la `v1.3`.
