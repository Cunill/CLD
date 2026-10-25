# PassiMaker: pla de la funció "Música de YouTube"

> Proposta de funcionalitat nova: cercar cançons a YouTube i descarregar-les en MP3, des de la cerca o amb l'enllaç
> directe, per afegir-les al passi.
> Versió del pla: 0.2 · Data: 25/10/2026 · Estat: **aprovat per l'usuari el 25/10/2026** (decisions al §0)
> Versió del programa prevista: **1.2.0**

---

## 0. Decisions de l'usuari (25/10/2026)

| # | Tema | Decisió |
|---|---|---|
| 1 | Seguir endavant | **Sí, amb tot el pla** (C01–C06) |
| 2 | Aspectes legals | **Només l'avís**, sense filtre Creative Commons. L'avís té una **casella de conformitat obligatòria** i **cap connexió a internet abans d'acceptar-lo** (§2.0) |
| 3 | Format | **MP3 de 192 kbps** |
| 4 | Carpeta de destinació | **Es pregunta cada vegada** (§2.2) |
| 5 | Escoltar abans de descarregar | **Botó "Obre a YouTube"** que obre el navegador |
| 6 | PR d'aquest pla | **No**: el document es queda a la branca fins al C01 |
| 7 | Validesa de la conformitat | **Una vegada per cada sessió del programa**: no es desa enlloc i es torna a demanar cada vegada que s'obre PassiMaker (§2.0) |
| 8 | Començar el C01 | **En una sessió nova**, branca `bloc/C01-decisio-youtube` (prompt al §4) |

---

## 1. Què canvia respecte del pla original

Aquesta funció xoca amb tres decisions preses i amb dues regles del CLAUDE.md. Cal aprovar-ho abans de programar res
(decisió nova **0012**).

| Què | Ara | Amb aquesta funció |
|---|---|---|
| Xarxa (PLA, Pas 0) | Totalment fora de línia | Connexió a internet **només** quan l'usuari obre "Música de YouTube". La resta del programa continua funcionant sense xarxa. |
| Regla 10 (dependències) | — | Dependència nova: **yt-dlp** (llicència Unlicense, domini públic). Probablement també **Deno** (entorn JavaScript que yt-dlp necessita per a YouTube des de finals del 2025; es confirma al C02). |
| Regla 7 (subprocess) | Només `passimaker.ffmpeg` llança processos | yt-dlp llança Deno per dins. El nostre codi no crida subprocess; cal comprovar que no s'obren finestres de consola i, si cal, ajustar la prova de la regla 7 (C02). |
| Mida del ZIP | ~150 MB (FFmpeg + Qt) | +~5 MB (yt-dlp) i, si cal Deno, +~40 MB comprimits |
| Manteniment | Versió estable, sense actualitzacions obligatòries | YouTube canvia sovint i trenca yt-dlp cada poques setmanes o mesos: cal publicar versions noves de PassiMaker amb yt-dlp actualitzat (§6). |

### 1.1 Aspectes legals (important)

- Les **Condicions del servei de YouTube** prohibeixen descarregar contingut si YouTube no ofereix un botó de
  descàrrega. Fer-ho no és un delicte per si mateix, però incompleix el contracte d'ús de YouTube.
- La majoria de cançons de YouTube tenen **drets d'autor**. Fer-les servir en un vídeo, encara que sigui d'ús intern de
  l'estudi, pot necessitar llicència; si el vídeo es publica (YouTube, Instagram…), la plataforma el pot silenciar o
  bloquejar.
- Mesures (decisió 2 del §0):
  1. **Avís amb casella de conformitat obligatòria** i sense cap connexió abans d'acceptar-lo (§2.0). L'avís inclou
     una **declinació explícita de responsabilitat** sobre els drets d'autor (petició de l'usuari, 25/10/2026, C01).
  2. A la guia, un apartat amb fonts de música lliure: Biblioteca d'àudio de YouTube (descàrrega oficial des de YouTube
     Studio), Free Music Archive, Pixabay Music.

---

## 2. Especificació funcional

### 2.0 Avís de conformitat i garantia de no-connexió

**L'avís.** En triar "Des de YouTube…" s'obre primer un diàleg modal "Abans de fer servir YouTube":

```
┌─ Abans de fer servir YouTube ───────────────────────────────────────────┐
│ Aquesta funció es connecta a internet per cercar i descarregar àudio   │
│ de YouTube.                                                             │
│                                                                         │
│ · Les condicions de YouTube no permeten descarregar contingut si        │
│   YouTube no ofereix un botó de descàrrega.                             │
│ · La majoria de cançons tenen drets d'autor. Descarrega i fes servir    │
│   només música que tinguis dret a fer servir.                           │
│ · Ets responsable de l'ús que en facis.                                 │
│ · PassiMaker i els seus autors declinen qualsevol responsabilitat       │
│   derivada de l'ús de la música descarregada, i en particular per       │
│   qualsevol infracció dels drets d'autor o de les condicions de         │
│   YouTube.                                                              │
│                                                                         │
│ ☐ He llegit l'avís, n'accepto les condicions i hi estic conforme        │
│                                                                         │
│                                   [Cancel·la]   [Accepta i continua]    │
└─────────────────────────────────────────────────────────────────────────┘
```

- La casella **no** està marcada mai d'entrada. [Accepta i continua] està **desactivat** fins que es marca.
- [Cancel·la], Esc o tancar la finestra: no s'obre la funció i no es desa res.
- **La conformitat val per a la sessió del programa** (decisió 7): es guarda només a la memòria i **no es desa
  enlloc** (ni `QSettings`, ni registre, ni el `.pmk`). Mentre PassiMaker continua obert, tornar a obrir la finestra
  de YouTube no torna a mostrar l'avís; en tancar el programa es perd i la propera vegada es torna a demanar.
- Es pot retirar abans d'hora des de la finestra de YouTube (enllaç "Retira la conformitat", que la tanca i
  cancel·la les descàrregues en curs). La conformitat és del programa, no de cada finestra principal: totes les
  finestres obertes del mateix PassiMaker la comparteixen.

**Garantia de no-connexió prèvia.** Abans de l'acceptació, el programa **no obre cap connexió de xarxa**, ni tan sols
per comprovar si hi ha internet. Es garanteix així:

1. **Una sola porta d'entrada.** Tota la xarxa de la funció passa per `passimaker.youtube`, i totes les funcions
   públiques que poden connectar-se reben un objecte `ConsentToken`. Només el pot crear `consent.grant(...)`, que es
   crida en acceptar l'avís i que només viu a la memòria. Sense testimoni, la funció llança
   `YoutubeConsentError` **abans** de fer res.
2. **yt-dlp no es carrega abans d'hora.** `import yt_dlp` es fa dins de les funcions, mai a nivell de mòdul ni a
   l'arrencada; tampoc no s'importa des de `ui/` (yt-dlp no fa connexions en importar-lo, però així ni tan sols és a
   memòria).
3. **Res automàtic.** La finestra de YouTube no fa cap cerca, ni baixa miniatures, ni comprova versions en obrir-se: la
   primera connexió és la primera cerca o enllaç que l'usuari demana.
4. **Proves que ho demostren** (C03 i C05), amb la xarxa bloquejada (`socket.socket.connect`, `socket.create_connection`
   i `socket.getaddrinfo` substituïts per una funció que fa fallar la prova):
   - arrencar el programa, obrir i desar un projecte i exportar: cap intent de connexió;
   - obrir l'avís, marcar i desmarcar la casella, cancel·lar: cap intent de connexió, `yt_dlp` no és a `sys.modules`,
     i no hi ha cap testimoni;
   - cridar `search`, `resolve` i `download_audio` sense testimoni: `YoutubeConsentError` i cap intent de connexió;
   - acceptar, tancar el programa (simulat amb un estat nou) i tornar a obrir YouTube: torna a sortir l'avís; i
     cap clau de conformitat a `QSettings` ni a cap fitxer.
   - Prova estàtica: cap mòdul fora de `passimaker.youtube` importa `yt_dlp`, `urllib.request`, `http.client` o
     `socket` (com la prova actual de PySide6 i de subprocess).

### 2.1 Recorregut

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Franja de música → [+ Música ▾] → **"Des de YouTube…"** | S'obre el diàleg "Música de YouTube" (no modal: es pot continuar treballant). Si encara no s'ha acceptat en aquesta sessió del programa, abans surt l'avís del §2.0. |
| 2a | Escriu "Ludovico Einaudi Nuvole Bianche" i prem Retorn | Llista de 10 resultats: miniatura, títol, canal, durada. Es poden carregar 10 més ("Més resultats"). |
| 2b | O bé enganxa un enllaç (`youtube.com/watch?v=…`, `youtu.be/…`, `music.youtube.com/…`, `shorts/…`) | El camp el reconeix sol i mostra un únic resultat amb les dades del vídeo. |
| 3 | Selecciona un o diversos resultats i prem **[Descarrega en MP3]** | Cada fila mostra el progrés (descarregant → convertint → fet). Es pot cancel·lar cada descàrrega. |
| 4 | Casella **"Afegeix al projecte en acabar"** (marcada per defecte) | En acabar, la cançó s'afegeix a la franja de música amb l'ordre `AddSongs` (desfer funciona com sempre). |
| 5 | [Mostrar a la carpeta] | Obre la carpeta on s'ha desat l'MP3. |
| — | Botó **[Obre a YouTube]** a cada resultat | Obre el vídeo al navegador per escoltar-lo abans de descarregar-lo (`QDesktopServices.openUrl`; el programa no s'hi connecta). |

### 2.2 Comportament i valors per defecte

| Paràmetre | Per defecte | Notes |
|---|---|---|
| Resultats per pàgina | 10 | `defaults.YOUTUBE_RESULTS_PER_PAGE` |
| Durada màxima acceptada | 20 min | Evita descarregar per error mescles d'hores. `defaults.YOUTUBE_MAX_DURATION_S`. Els resultats més llargs surten en gris amb el motiu. |
| Format | MP3, 192 kbps, 48 kHz estèreo | `defaults.YOUTUBE_MP3_BITRATE_KBPS`. 48 kHz perquè és la freqüència del mesclador (CONTRACTES §0). |
| Carpeta de destinació | **Es pregunta cada vegada** | En prémer [Descarrega en MP3] s'obre el selector de carpeta, un cop per a tota la selecció. Proposa la darrera carpeta feta servir (o `Documents` la primera vegada). Cancel·lar-lo no descarrega res. |
| Nom del fitxer | `<títol>.mp3`, netejat de caràcters no vàlids a Windows | Si ja existeix: `<títol> (2).mp3`. Mai se sobreescriu res. |
| Metadades | Títol, canal (com a artista), URL d'origen al comentari | Etiquetes ID3 escrites per FFmpeg. |
| Descàrregues simultànies | 2 | La resta queden a la cua. |

### 2.3 Errors (textos en català, traduïbles)

| Situació | Missatge |
|---|---|
| Sense connexió | "No hi ha connexió a internet. Comprova la xarxa i torna-ho a provar." |
| Enllaç no vàlid | "Aquest enllaç no és d'un vídeo de YouTube." |
| Vídeo privat, esborrat, amb restricció d'edat o de país | "Aquest vídeo no es pot descarregar (és privat, s'ha esborrat o té restriccions)." |
| Directe en curs | "No es poden descarregar directes." |
| YouTube ha canviat i yt-dlp no funciona | "YouTube ha canviat i aquesta versió de PassiMaker ja no pot descarregar. Cal una versió nova del programa." (+ detall al registre) |
| Massa llarg | "Aquest vídeo dura més de 20 minuts." |

### 2.4 Fora d'aquest pla

Llistes de reproducció senceres, vídeo (només àudio), altres webs que yt-dlp admet, escoltar la cançó dins del
programa (es fa al navegador amb [Obre a YouTube]), filtre Creative Commons (descartat, decisió 2).

---

## 3. Arquitectura

```
ui/youtube_dialog.py  (Qt)                       ── regla 1: Qt només a ui/
   │  QThreadPool / fils de treball                ── regla 6
   ▼
passimaker.youtube  (nucli, sense Qt)  ── mòdul nou
   ├─ consent.py   ConsentToken i conformitat; sense testimoni no hi ha xarxa (§2.0)
   ├─ links.py      reconeix i normalitza enllaços (pur, sense xarxa)
   ├─ search.py     search(...) / resolve(...)      → yt-dlp (ytsearch, extract_flat)
   ├─ download.py   download_audio(...)             → yt-dlp (només baixa el millor àudio, sense postprocés)
   ├─ files.py      nom de fitxer segur, sense sobreescriure
   └─ types.py      SearchResult, DownloadResult, errors
   │
   ▼
passimaker.ffmpeg.convert_to_mp3(...)  ── regla 7: la conversió la fa el nostre pont FFmpeg
   │
   ▼
model: AddSongs (controlador)           ── regla 2: el projecte només canvia pel controlador
```

Decisions de disseny:

- **yt-dlp com a biblioteca Python** (`import yt_dlp`), no com a executable: així el nostre codi no llança cap procés i
  els errors arriben com a excepcions. yt-dlp **no** fa la conversió (no se li passa FFmpeg): baixa l'àudio original
  (M4A/WebM) i el converteix `passimaker.ffmpeg`, que ja amaga la consola i gestiona les rutes Unicode.
- **Cerca sense clau d'API**: amb `ytsearchN:` de yt-dlp. L'alternativa oficial (YouTube Data API v3) demana una clau
  de Google i té quota diària; no compensa per a ús intern.
- **Proves sense xarxa**: el mòdul rep un "backend" injectable (protocol `YoutubeBackend`). Les proves fan servir un
  substitut a `tests/fakes` amb respostes desades. Les proves amb xarxa real porten una marca nova, `xarxa`, excloses
  per defecte i a la CI (els servidors de GitHub sovint reben el bloqueig "confirma que no ets un robot" de YouTube);
  les fa l'usuari al seu PC.
- **Miniatures dels resultats**: es baixen en un fil amb `urllib` (biblioteca estàndard), petites (`mqdefault`, 320 px)
  i només a memòria.

### 3.1 Contracte proposat (CONTRACTES §15, nou)

| Operació | Rep | Retorna |
|---|---|---|
| `parse_link(text)` | text enganxat | `video_id: str` o `None` |
| `search(testimoni, consulta, limit, offset, cancel)` | — | `tuple[SearchResult, ...]` |
| `resolve(testimoni, video_id, cancel)` | — | `SearchResult` |
| `download_audio(testimoni, video_id, carpeta_temp, progress, cancel)` | — | `Path` del fitxer d'àudio original |
| `ffmpeg.convert_to_mp3(origen, destí, kbps, metadades, progress, cancel)` | — | `None` (escriu a un fitxer temporal i el reanomena en acabar) |
| `safe_target_path(carpeta, títol)` | — | `Path` lliure, vàlid a Windows |
| `fetch_thumbnail(testimoni, url, cancel)` | — | `bytes` de la imatge (la UI la converteix) |
| `consent.grant()` / `consent.current()` / `consent.revoke()` | — | `ConsentToken` o `None`; estat només a la memòria del procés (§2.0) |

`SearchResult`: `video_id`, `title`, `channel`, `duration_s` (`float | None`), `thumbnail_url`, `is_live`,
`url`. Errors (hereten de `PassiMakerError`): `YoutubeOfflineError`, `YoutubeUnavailableError`,
`YoutubeBrokenError`, `YoutubeTooLongError`, `YoutubeConsentError`.

---

## 4. Blocs de desenvolupament

Mateix protocol que la resta (CLAUDE.md): un bloc per sessió, branca `bloc/CNN-nom`, nota a `docs/sessions/CNN.md`.

| Bloc | Nom | Mòduls | Mida | Depèn de | Model | On |
|---|---|---|---|---|---|---|
| C01 | Decisió 0012, contracte i especificació | documentació, esquelet de `youtube` | Petit | aprovació | Sonnet | Núvol |
| C02 | Prova de viabilitat a Windows | script de prova, paquet | Petit | C01 | Opus | Núvol + **local** |
| C03 | Nucli `passimaker.youtube` | `youtube` (nou) | Mitjà | C02 | Opus | Núvol |
| C04 | Conversió a MP3 al pont FFmpeg | `ffmpeg` | Petit | C01 (en paral·lel amb C03) | Sonnet | Núvol |
| C05 | Diàleg "Música de YouTube" | `ui` | Gran | C03, C04 | Sonnet | Núvol |
| C06 | Empaquetat, guia i versió 1.2.0 | paquet, `ui/help.py`, documentació | Mitjà | C05 | Sonnet | Núvol + **local** |

### 4.1 Seguiment: estimació i consum

Es posa al dia en tancar cada bloc (a la mateixa PR del bloc). "Sessions" són sessions de Claude Code; "temps teu" són
les hores de l'usuari (revisar, decidir, provar al PC). Estimació en tres escenaris: optimista / probable / pessimista.

| Bloc | Depèn de | En paral·lel amb | Tanda | Sessions estimades (opt. / prob. / pes.) | Temps teu estimat (h) | Estat | Sessions consumides | Temps teu consumit (h) | PR · commit |
|---|---|---|---|---|---|---|---|---|---|
| Pla (aquest document) | — | — | — | — | — | ✅ aprovat el 25/10/2026 | 1 | — | branca `ccr-08701f22-8ayer4` (sense PR, decisió 6) |
| C01 Decisió i contracte | aprovació del pla | — (és la base de tots) | T1 | 1 / 1 / 1 | 0,5 | ✅ aprovat per l'usuari el 25/10/2026 (es tanca en fusionar la PR) | 1 | — | PR #52 · branca `ccr-59466ea5-miqdh0` |
| C02 Prova de viabilitat | C01 | **C04** | T2 | 1 / 1 / 2 | 1,0 | ⏳ pendent | — | — | — |
| C03 Nucli `youtube` | C01, C02 | **C04** (si encara no s'ha fet) | T3 | 1 / 1 / 2 | 0,5 | ⏳ pendent | — | — | — |
| C04 Conversió a MP3 | C01 | **C02** o **C03** | T2 (o T3) | 1 / 1 / 1 | 0,25 | ⏳ pendent | — | — | — |
| C05 Diàleg | C03, C04 | — | T4 | 1 / 2 / 2 | 1,0 | ⏳ pendent | — | — | — |
| C06 Empaquetat i versió | C05 | — | T5 | 1 / 1 / 2 | 1,0 | ⏳ pendent | — | — | — |
| **Subtotal dels blocs** |  |  |  | **6 / 7 / 10** | **4,25** | | **1** | **0** | |
| Sessions de correcció després de la prova de l'usuari | C06 | — | després del C06 | 0 / 1 / 2 | inclòs a sota | ⏳ pendent | — | — | — |
| Revisió de les PR i prova final de l'usuari | — | — | totes | — | 1,5 / 3 / 6 | ⏳ pendent | — | — | — |
| **Total** |  |  |  | **6 / 8 / 12 sessions** | **6 / 7 / 10 h** | | **2** (el pla i el C01) | **—** | |

Llegenda de l'estat: ⏳ pendent · 🔧 en curs · ✅ tancat (fusionat a `main`) · ⛔ aturat (vegeu `docs/sessions/CNN.md`).

**Dependències i blocs en paral·lel.** Una *tanda* és un grup de blocs que es poden fer **alhora**, en sessions de
Claude Code diferents, perquè no depenen l'un de l'altre ni toquen els mateixos fitxers de codi. Una tanda comença quan
tots els blocs de què depèn són a `main`.

```
T1          T2                    T3              T4          T5
C01 ──┬──▶ C02 (viabilitat) ──▶ C03 (nucli) ──┐
      │                                       ├──▶ C05 ──▶ C06 ──▶ correccions
      └──▶ C04 (MP3, pont FFmpeg) ────────────┘
```

| Parella en paral·lel | Per què és possible | Fitxers de codi de cadascun |
|---|---|---|
| C02 ∥ C04 | C04 només necessita el contracte de `convert_to_mp3` (C01); no depèn de yt-dlp | C02: script de prova, `pyproject.toml`, `uv.lock`, paquet · C04: `src/passimaker/ffmpeg`, `tests/**/ffmpeg` |
| C03 ∥ C04 | C03 baixa l'àudio original i C04 el converteix: es troben només al contracte | C03: `src/passimaker/youtube`, `tests/**/youtube` · C04: com a dalt |

- **No es poden fer en paral·lel:** C01 amb res (fixa els contractes); C03 abans del C02 (pot canviar l'enfocament);
  C05 abans del C03 i el C04 (la interfície els fa servir tots dos); C06 abans del C05.
- **Fitxers compartits:** la taula d'aquest §4.1 i l'apartat Estat del CLAUDE.md. Cada bloc en paral·lel hi escriu
  només la seva fila; el que es fusiona segon porta `main` a la seva branca (fusió, sense reescriure la història) i
  resol el conflicte abans de fusionar.
- **Camí crític:** C01 → C02 → C03 → C05 → C06 (5 sessions probables). Fer el C04 en paral·lel estalvia **1 sessió**
  del calendari; el total de sessions no canvia.

**Calendari** (a 4 h/setmana del teu temps, començant quan s'aprovi el C01):

| Escenari | Sessions | Hores teves | Setmanes |
|---|---|---|---|
| Optimista | 6 | 6 h | 1,5 |
| **Probable** | **8** | **7 h** | **2** |
| Pessimista | 12 | 10 h | 2,5–3 |

### C01 · Decisió, contracte i especificació
- **Fa:** `docs/decisions/0012-musica-de-youtube.md` (xarxa, dependències, regla 7, aspectes legals, manteniment);
  CONTRACTES §15 i ampliació del §8 (`convert_to_mp3`); ESPECIFICACIO §1.7 bis (el §2 d'aquest pla); valors nous a
  `defaults.py`; tipus i signatures sense implementació a `src/passimaker/youtube/`.
- **Acceptació:** documents aprovats per l'usuari; ruff i pyright nets; la prova de "Qt fora del nucli" cobreix el
  mòdul nou.
- **No fa:** cap dependència nova (yt-dlp entra al C02, quan s'hagi comprovat que funciona) ni cap implementació.

```text
Bloc C01: Música de YouTube, decisió, contracte i especificació. Model: Sonnet.
Context: PassiMaker 1.1.0 és a main. El pla d'aquesta funció és a docs/PLA_YOUTUBE.md de la branca
ccr-08701f22-8ayer4 (no és a main): porta'l amb `git fetch origin ccr-08701f22-8ayer4` i
`git checkout origin/ccr-08701f22-8ayer4 -- docs/PLA_YOUTUBE.md`. Llegeix-ne el §0, el §1, el §2, el §3 i la fitxa del
C01; i docs/CONTRACTES.md.
Branca: bloc/C01-decisio-youtube (des de main actualitzat).
Objectiu: deixar decidit i definit tot el que els blocs C02–C06 necessiten, sense implementar-ho.
Fes:
1. docs/decisions/0012-musica-de-youtube.md: xarxa només a la funció de YouTube i mai abans de l'avís, dependències
   yt-dlp (i Deno, a confirmar al C02), regla 7 (yt-dlp llança Deno per dins), aspectes legals, conformitat per
   sessió del programa, manteniment (§6 del pla). Les decisions 1–8 del §0, amb data 25/10/2026.
2. docs/ESPECIFICACIO.md: apartat nou de la música de YouTube a partir del §2 del pla (avís, recorregut, valors,
   errors, fora d'abast).
3. docs/CONTRACTES.md: §15 nou (`passimaker.youtube`, §3.1 del pla), §8 ampliat amb `convert_to_mp3`, §13 (la
   interfície pot fer servir `youtube`).
4. src/passimaker/model/defaults.py: els valors del §2.2 del pla (resultats per pàgina, durada màxima, kbps,
   descàrregues simultànies).
5. src/passimaker/youtube/: tipus, errors (amb les claus de missatge a passimaker.i18n), ConsentToken i signatures
   sense implementació (les funcions avisen que no estan implementades). `convert_to_mp3` igual a
   src/passimaker/ffmpeg.
6. tests/unit/test_architecture.py: el mòdul nou sense Qt; cap mòdul fora de passimaker.youtube importa yt_dlp,
   urllib.request, http.client ni socket.
7. docs/PLA_YOUTUBE.md: posa al dia la taula del §4.1 (C01 tancat, sessions i PR).
8. CLAUDE.md, apartat Estat: una línia sobre la funció de YouTube i el pla.
Criteris d'acceptació: decisió, especificació i contractes coherents amb el pla; tots els tipus i signatures del §3.1
existeixen; suite ràpida, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: els dels punts 1–8, docs/sessions/C01.md i tests/unit/youtube/ (proves dels tipus i de
parse_link si el vols deixar fet; és pur i sense xarxa).
Condició d'aturada: la del CLAUDE.md. A docs/sessions/C01.md, anota les decisions que hagis pres.
```

### C02 · Prova de viabilitat (spike)
Bloc curt per eliminar els riscos grossos abans d'invertir-hi més.
- **Fa:** una branca amb un script mínim que, des del ZIP de PyInstaller a Windows, cerca, baixa un àudio i el
  converteix. Comprova: (1) si yt-dlp necessita Deno i com s'empaqueta; (2) que no s'obre cap finestra de consola des
  d'una aplicació sense consola; (3) que l'antivirus (Windows Defender) no bloqueja res; (4) que funciona darrere de la
  xarxa de l'estudi (servidor intermediari?); (5) mida final del ZIP.
- **Local:** l'usuari executa el ZIP de prova al seu PC (un pas cada vegada).
- **Acceptació:** informe a `docs/sessions/C02.md` amb el resultat de cada punt i la recomanació final (seguir, canviar
  d'enfocament o abandonar).

### C03 · Nucli `passimaker.youtube`
- **Fa:** `links.py`, `search.py`, `download.py`, `files.py` amb el backend injectable i el substitut de proves.
  Cancel·lació i progrés amb `CancelToken` i `ProgressCallback`. Traducció dels errors de yt-dlp als errors propis.
- **Proves:** enllaços (Hypothesis: formats vàlids i no vàlids, paràmetres extra com `&t=30s`, `&list=…`), noms de
  fitxer (caràcters reservats de Windows, noms reservats com `CON`, longitud, duplicats), cancel·lació, durada màxima,
  directes, errors; **proves de no-connexió del §2.0** (xarxa bloquejada, sense testimoni, `yt_dlp` no carregat) i
  la prova estàtica d'imports de xarxa. Una prova `xarxa` amb un vídeo Creative Commons estable.
- **Acceptació:** cobertura de totes les files de la taula d'errors del §2.3; cap import de PySide6; pyright estricte.

### C04 · Conversió a MP3
- **Fa:** `passimaker.ffmpeg.convert_to_mp3` (libmp3lame, 48 kHz, estèreo, etiquetes ID3, progrés, cancel·lació,
  escriptura atòmica). Comprova que l'FFmpeg 7.1.1 fixat porta libmp3lame (la build GPL sí).
- **Proves:** amb els tons de `tests/fixtures` (WAV, M4A): durada conservada (±50 ms), 48 kHz, etiquetes llegibles,
  rutes amb accents i emojis, cancel·lació a mitges sense deixar fitxers.

### C05 · Diàleg "Música de YouTube"
- **Fa:** `ui/youtube_dialog.py` i l'entrada al menú de [+ Música]. Camp únic de cerca/enllaç, llista de resultats
  amb miniatures, cua de descàrregues amb progrés per fila, carpeta de destinació, casella "Afegeix al projecte", botó
  [Obre a YouTube], selector de carpeta a cada descàrrega i **avís de conformitat del §2.0** (casella obligatòria,
  botó desactivat fins que es marca, conformitat per sessió del programa, retirar-la). Tot fora del fil de la interfície. En tancar el diàleg amb descàrregues actives, pregunta.
- **Proves:** pytest-qt amb el backend substitut: cerca, enllaç, selecció múltiple, cancel·lació, error de xarxa,
  afegir al projecte (comprova l'ordre `AddSongs` al controlador), textos traduïbles.
- **Acceptació:** cap operació de més de 50 ms al fil de la interfície; el programa sense xarxa s'obre i funciona igual.

### C06 · Empaquetat, guia i versió
- **Fa:** PyInstaller amb yt-dlp (i Deno si cal); `tools/construir_zip.ps1`; CI; apartat nou a la guia (`ui/help.py`)
  i a "Imprevistos" ("YouTube ha canviat"); CHANGELOG; versió 1.2.0; flux de manteniment del §6.
- **Local:** prova de l'usuari amb el ZIP: una cerca, un enllaç, una descàrrega afegida a un passi i exportada.
- **Acceptació:** prova de l'usuari correcta; versió publicada amb `publicar.yml`.

---

## 5. Riscos

| Risc | Probabilitat | Impacte | Mitigació |
|---|---|---|---|
| YouTube canvia i la descarrega deixa de funcionar | **Alta** (diversos cops l'any) | La funció falla fins que es publica una versió nova | Missatge clar (§2.3); flux de manteniment (§6); la resta del programa no es veu afectada |
| YouTube bloqueja l'adreça IP ("confirma que no ets un robot") | Mitjana | No es pot descarregar des d'aquella xarxa | Missatge clar; poques descàrregues simultànies; no és solucionable des del programa |
| Problema legal (condicions de YouTube, drets d'autor) | Mitjana | Reclamació o vídeo silenciat si es publica | §1.1 i §2.0: avís amb conformitat obligatòria, fonts de música lliure a la guia |
| L'antivirus marca Deno o yt-dlp | Baixa–mitjana | El ZIP no s'executa | Es comprova al C02 |
| Finestres de consola en llançar Deno | Mitjana | Molèstia visual | Es comprova al C02; si passa, s'ajusta la configuració o es descarta Deno |
| El ZIP creix massa | Baixa | Descàrrega més lenta | Es mesura al C02 |

## 6. Manteniment

yt-dlp publica versions noves sovint. Proposta:

1. Un flux setmanal a GitHub Actions comprova si hi ha una versió nova de yt-dlp i, si n'hi ha, obre una PR que
   l'actualitza a `uv.lock` (la CI la prova com qualsevol altra).
2. Quan l'usuari vegi el missatge "YouTube ha canviat", obre una sessió al núvol: es fusiona la PR pendent i es
   publica una versió de pedaç (1.2.1, 1.2.2…) amb `publicar.yml`. L'usuari només ha de baixar el ZIP nou.
3. Alternativa descartada: que el programa s'actualitzi yt-dlp sol des d'internet. És més còmode però executa codi
   baixat sense revisar i complica el ZIP portable.

---

## Per decidir

Res pendent: el pla està aprovat (decisions 1–8 del §0).

**Pendent de la teva part:** res del C01 (aprovat el 25/10/2026). Següent: tanda T2, C02 i C04 (prompts per escriure).
