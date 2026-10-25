# PassiMaker: pla de la música de YouTube i de la gravació del so

> Proposta de funcionalitat nova: cercar cançons a YouTube i descarregar-les en MP3, des de la cerca o amb l'enllaç
> directe, per afegir-les al passi; i (ampliació, blocs C07–C10) gravar en directe el so que sona a l'ordinador.
> Especificació de la gravació: annex `docs/PLA_GRAVACIO.md`.
> Versió del pla: 0.3 · Data: 25/10/2026 · Estat: **aprovat per l'usuari el 25/10/2026** (decisions al §0; ampliació
> de la gravació aprovada el mateix dia, decisions G1–G9 de l'annex)
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
| 9 | Ampliació: gravar el so de l'ordinador | **Aprovada i incorporada** (blocs C07–C10; annex `docs/PLA_GRAVACIO.md`, decisions G1–G9): sense avís, gravacions interrompudes i les que arriben als 30 min s'esborren, ones per canal, micròfon opcional, MP3 192 kbps, **una sola versió 1.2.0** amb YouTube i gravació (el C06 empaqueta les dues) |

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
| YouTube bloqueja la xarxa ("confirma que no ets un robot", massa peticions) | "YouTube no deixa descarregar des d'aquesta xarxa ara mateix. Torna-ho a provar més tard o des d'una altra connexió." (el detall, al registre) |
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
| C06 | Empaquetat, guia i versió 1.2.0 (YouTube i gravació) | paquet, `ui/help.py`, documentació | Mitjà | C05, C10 | Sonnet | Núvol + **local** |
| C07 | Gravació: decisió 0013, contracte i especificació | documentació, esquelet de `recorder` | Petit | C01 | Sonnet | Núvol |
| C08 | Gravació: prova de viabilitat a Windows | script de prova, paquet | Petit | C01 (en paral·lel amb C07) | Opus | Núvol + **local** |
| C09 | Nucli `passimaker.recorder` | `recorder` (nou) | Mitjà | C08 (i el C03, pel trasllat de `safe_target_path`) | Opus | Núvol |
| C10 | Finestra "Grava el que sona" (ones) | `ui` | Gran | C05, C09 | Sonnet | Núvol |

### 4.1 Seguiment: estimació i consum

Es posa al dia en tancar cada bloc (a la mateixa PR del bloc). "Sessions" són sessions de Claude Code; "temps teu" són
les hores de l'usuari (revisar, decidir, provar al PC). Estimació en tres escenaris: optimista / probable / pessimista.

| Bloc | Depèn de | En paral·lel amb | Tanda | Sessions estimades (opt. / prob. / pes.) | Temps teu estimat (h) | Estat | Sessions consumides | Temps teu consumit (h) | PR · commit |
|---|---|---|---|---|---|---|---|---|---|
| Pla (aquest document) | — | — | — | — | — | ✅ aprovat el 25/10/2026; ampliació de la gravació aprovada i incorporada el mateix dia | 1 | — | branca `ccr-08701f22-8ayer4` |
| C01 Decisió i contracte | aprovació del pla | — (és la base de tots) | T1 | 1 / 1 / 1 | 0,5 | ✅ tancat el 25/10/2026 | 1 | — | PR #52 · `7f1bc0b` |
| C02 Prova de viabilitat | C01 | **C04** | T2 | 1 / 1 / 2 | 1,0 | ✅ tancat el 25/10/2026; prova al PC correcta (xarxa de casa; a la de l'estudi no es prova, decisió de l'usuari) (`docs/sessions/C02.md`) | 1 | — | PR #57 · `1599fb7` |
| C03 Nucli `youtube` | C01, C02 | **C04** (si encara no s'ha fet) | T3 | 1 / 1 / 2 | 0,5 | ✅ tancat el 25/10/2026 | 1 | — | PR #58 · `5c7fd88` |
| C04 Conversió a MP3 | C01 | **C02** o **C03** | T2 (o T3) | 1 / 1 / 1 | 0,25 | ✅ tancat el 25/10/2026 | 1 | — | PR #54 · `5c2129b` |
| C05 Diàleg | C03, C04 | **C08** o **C09** | T4 | 1 / 2 / 2 | 1,0 | 🔧 en curs: finestra feta i provada amb el substitut; falta la prova de l'usuari a Windows (`docs/sessions/C05.md`) | 1 | — | branca `claude/practical-hawking-1i180s` |
| C06 Empaquetat i versió (YouTube i gravació) | C05, C10 | — | T6 | 1 / 1 / 2 | 1,25 | ⏳ pendent | — | — | — |
| C07 Gravació: decisió i contracte | C01 | **C08**, **C03** | T3 | 1 / 1 / 1 | 0,5 | ⛔ aturat per l'usuari (sessió "C07 mp3"); la feina feta encara no s'ha pujat | — | — | branca `claude/keen-pascal-io3h1f` (no pujada) |
| C08 Gravació: prova de viabilitat | C01 | **C07**, **C03** o **C05** | T3 | 1 / 1 / 2 | 1,0 | ⛔ aturat (sessió "C08 mp3"): sounddevice no serveix; `soundcard` 0.4.6 aprovada per l'usuari (G10), pendent de continuar | — | — | branca `claude/confident-ritchie-rk3iju` (nota pujada) |
| C09 Nucli `recorder` | C07, C08 (i C03) | **C05** | T4 | 1 / 2 / 2 | 0,5 | ⏳ pendent | — | — | — |
| C10 Finestra de gravació | C05, C09 | — | T5 | 1 / 2 / 2 | 1,0 | ⏳ pendent | — | — | — |
| **Subtotal dels blocs** |  |  |  | **10 / 13 / 17** | **7,5** | | **4** | **—** | |
| Sessions de correcció després de la prova de l'usuari | C06 | — | després del C06 | 0 / 2 / 3 | inclòs a sota | ⏳ pendent | — | — | — |
| Revisió de les PR i prova final de l'usuari | — | — | totes | — | 2,5 / 5 / 10 | ⏳ pendent | — | — | — |
| **Total** |  |  |  | **10 / 15 / 20 sessions** | **10 / 12,5 / 17,5 h** | | **5** (el pla i l'ampliació, C01, C02, C03 i C04) | **—** | |

Llegenda de l'estat: ⏳ pendent · 🔧 en curs · ✅ tancat (fusionat a `main`) · ⛔ aturat (vegeu `docs/sessions/CNN.md`).

**Dependències i blocs en paral·lel.** Una *tanda* és un grup de blocs que es poden fer **alhora**, en sessions de
Claude Code diferents, perquè no depenen l'un de l'altre ni toquen els mateixos fitxers de codi. Una tanda comença quan
tots els blocs de què depèn són a `main`.

```
T1      T2                  T3                    T4               T5                T6
C01 ─┬─▶ C02 (viabilitat) ─▶ C03 (nucli) ────┬──▶ C05 (diàleg) ─────┐
     ├─▶ C04 (MP3) ───────────────────────────┤                     │
     ├──────────────────────▶ C07 (decisió) ──┼──▶ C09 (nucli) ─────┴─▶ C10 (finestra) ─▶ C06 ─▶ correccions
     └──────────────────────▶ C08 (viabilitat)┘
                     (C09 espera el C03, el C07 i el C08)
```

| Parella en paral·lel | Per què és possible | Fitxers de codi de cadascun |
|---|---|---|
| C02 ∥ C04 | C04 només necessita el contracte de `convert_to_mp3` (C01); no depèn de yt-dlp | C02: script de prova, `pyproject.toml`, `uv.lock`, paquet · C04: `src/passimaker/ffmpeg`, `tests/**/ffmpeg` |
| C03 ∥ C04 | C03 baixa l'àudio original i C04 el converteix: es troben només al contracte | C03: `src/passimaker/youtube`, `tests/**/youtube` · C04: com a dalt |
| C03 ∥ C07 | C07 només escriu documents i l'esquelet de `recorder`; no toca `youtube` | C07: `src/passimaker/recorder`, documentació, `defaults.py` (valors nous al final) |
| C07 ∥ C08 | El C08 és una prova a part (`tools/`, `packaging/`, CI) que no fa servir res del C07: es basa en l'annex `docs/PLA_GRAVACIO.md`. El C09 llegeix tots dos | C07: com a dalt · C08: `tools/prova_gravacio.py`, `packaging/ProvaGravacio.spec`, treball nou de la CI |
| C05 ∥ C08 / C09 | La finestra de YouTube i la gravació no es toquen fins al C10 | C05: `src/passimaker/ui` · C08: `tools/`, `packaging/`, CI · C09: `src/passimaker/recorder`, `src/passimaker/common` |

- **No es poden fer en paral·lel:** C01 amb res (fixa els contractes); C03 abans del C02 (pot canviar l'enfocament);
  C05 abans del C03 i el C04 (la interfície els fa servir tots dos); C09 abans del C07 i el C08 (pot
  canviar la tecnologia) i del C03 (es trasllada `safe_target_path`, que el C03 modifica); C10 abans del C05 (comparteixen
  el menú [+ Música ▾]) i del C09; C06 abans del C05 i el C10.
- **Fitxers compartits:** la taula d'aquest §4.1 i l'apartat Estat del CLAUDE.md. Cada bloc en paral·lel hi escriu
  només la seva fila; el que es fusiona segon porta `main` a la seva branca (fusió, sense reescriure la història) i
  resol el conflicte abans de fusionar.
- **Camí crític** (des d'ara, amb el C01, el C02 i el C04 fets): C08 → C09 → C10 → C06 (6 sessions probables; el C07
  va alhora que el C08). El
  C03 i el C05 (3 sessions) es fan alhora i no l'allarguen.

**Calendari** (a 4 h/setmana del teu temps, començant quan s'aprovi el C01):

| Escenari | Sessions | Hores teves | Setmanes |
|---|---|---|---|
| Optimista | 10 | 10 h | 2,5 |
| **Probable** | **15** | **12,5 h** | **3–3,5** |
| Pessimista | 20 | 17,5 h | 4,5 |

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

```text
Bloc C02: Música de YouTube, prova de viabilitat a Windows (spike). Model: Opus.
Context: el C01 és a main (PR #52, commit 7f1bc0b). Llegeix docs/PLA_YOUTUBE.md (§1, §3, §5 i la fitxa del C02),
docs/decisions/0012-musica-de-youtube.md, docs/CONTRACTES.md (§8 i §15), packaging/PassiMaker.spec,
tools/construir_zip.ps1, packaging/provar_paquet.ps1 i .github/workflows/ci.yml.
Branca: bloc/C02-viabilitat-youtube des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: comprovar, abans d'invertir-hi més, que yt-dlp funciona des d'un ZIP de PyInstaller a Windows, i decidir
seguir, canviar d'enfocament o abandonar. No s'implementa passimaker.youtube (és el C03).
Fes:
1. Dependència yt-dlp (aprovada a la decisió 0012) a pyproject.toml i uv.lock, amb la versió fixada. Esbrina si per a
   YouTube cal un entorn JavaScript (Deno, o el paquet yt-dlp-ejs) i com s'ha d'empaquetar; si cal Deno, NO l'afegeixis
   sense proposar-ho: explica-ho a docs/sessions/C02.md (mida, llicència, d'on es baixa, suma SHA-256) i atura't.
2. Un script mínim de prova, tools/prova_youtube.py, sense Qt i sense consola: amb un enllaç i una cerca fixos (un vídeo
   Creative Commons estable), cerca 3 resultats, baixa el millor àudio a una carpeta temporal sense postprocés de
   yt-dlp, comprova el fitxer amb passimaker.ffmpeg.probe i escriu un informe de text (versions, temps, mida, errors
   complets) al costat de l'executable. Ha de funcionar també darrere d'un servidor intermediari (variables
   HTTPS_PROXY del sistema).
3. Un .spec propi (packaging/ProvaYoutube.spec, console=False, amb el mateix FFmpeg) i un treball nou a
   .github/workflows/ci.yml que construeix el ZIP "ProvaYoutube-win64" i el publica com a artefacte. No canviïs el
   ZIP de PassiMaker ni el treball que ja existeix.
4. Proves (a Linux, sense xarxa): l'script es pot importar sense connectar-se; la prova d'arquitectura continua
   passant (tools/ no és dins de src, però cap mòdul de src importa yt_dlp).
5. docs/sessions/C02.md amb els resultats dels 5 punts de la fitxa del C02: (1) Deno sí o no i com s'empaqueta;
   (2) cap finestra de consola; (3) Windows Defender no bloqueja res; (4) funciona a la xarxa de l'estudi; (5) mida
   del ZIP. Els punts 2–4 els comprova l'usuari al seu PC: dona-li les instruccions pas a pas (un pas cada vegada) per
   baixar l'artefacte, executar-lo i enganxar-te l'informe.
6. docs/PLA_YOUTUBE.md: només la fila del C02 de la taula del §4.1. CLAUDE.md, apartat Estat: una línia del C02.
   Si el C04 ja és a main, porta main a la branca (fusió) i resol el conflicte d'aquests dos fitxers.
Criteris d'acceptació: ZIP de prova generat per la CI; informe de l'usuari amb els 5 punts; recomanació final a
docs/sessions/C02.md; suite ràpida, ruff i pyright en verd.
Fitxers permesos: pyproject.toml, uv.lock, tools/prova_youtube.py, packaging/ProvaYoutube.spec,
.github/workflows/ci.yml (només el treball nou), tests/unit/test_prova_youtube.py, docs/sessions/C02.md, la fila del
C02 a docs/PLA_YOUTUBE.md i l'apartat Estat del CLAUDE.md. Res de src/passimaker/youtube ni de src/passimaker/ffmpeg.
Condició d'aturada: la del CLAUDE.md. També t'atures si cal Deno (punt 1) o si la prova a Windows falla dues vegades
pel mateix motiu: anota-ho a docs/sessions/C02.md amb el pas següent.
```

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

```text
Bloc C04: Música de YouTube, conversió a MP3 al pont FFmpeg. Model: Sonnet.
Context: el C01 és a main (PR #52, commit 7f1bc0b): hi ha la signatura de passimaker.ffmpeg.convert_to_mp3 i el tipus
Mp3Tags, sense implementar. Llegeix docs/CONTRACTES.md (§0 i §8), la fitxa del C04 a docs/PLA_YOUTUBE.md,
docs/sessions/C01.md, src/passimaker/ffmpeg/ (sobretot _mp3.py, _audio.py, _process.py i types.py) i
tests/integration/ffmpeg/.
Branca: bloc/C04-mp3 des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: implementar convert_to_mp3 tal com diu el contracte §8, sense canviar-ne la signatura.
Fes:
1. src/passimaker/ffmpeg/_mp3.py: libmp3lame a bitrate_kbps constant, 48 kHz estèreo (AUDIO_SAMPLE_RATE,
   AUDIO_CHANNELS), etiquetes ID3 (títol, artista, comentari) amb accents i emojis, sense la imatge de portada.
   Progrés amb ProgressCallback (a partir de la durada que dona probe) i cancel·lació amb CancelToken que atura FFmpeg
   en menys de 2 s. Escriptura atòmica: fitxer temporal al costat del destí i reanomenar-lo en acabar; si falla o es
   cancel·la, no queda cap fitxer (ni el temporal). Sempre a través de _process (sense shell ni consola, rutes Unicode).
   Errors: FfmpegError amb les claus que ja existeixen (file_not_found, unreadable, no_audio, disk_full, write_error,
   failed); si en cal una de nova, proposa-la i atura't.
2. Comprova que l'FFmpeg 7.1.1 fixat a Windows (build "essentials" de Gyan) porta libmp3lame; si no, atura't i
   proposa una alternativa (no canviïs la build sense permís).
3. Proves a tests/integration/ffmpeg/test_mp3.py amb els tons de tests/fixtures (WAV, M4A, i mono i 44,1 kHz si n'hi
   ha): durada conservada (±50 ms), 48 kHz estèreo, bitrate, etiquetes llegibles amb ffprobe, rutes amb accents i
   emojis, destí que ja existeix (es reemplaça només en acabar bé), fitxer sense so (ffmpeg.no_audio), cancel·lació a
   mitges sense deixar fitxers, i progrés que no recula. Les proves de més de ~5 s porten la marca "lent".
4. docs/sessions/C04.md: què s'ha fet, les decisions preses i els resultats.
5. docs/PLA_YOUTUBE.md: només la fila del C04 de la taula del §4.1. CLAUDE.md, apartat Estat: una línia del C04.
   Si el C02 ja és a main, porta main a la branca (fusió) i resol el conflicte d'aquests dos fitxers.
Criteris d'acceptació: contracte §8 complert; proves del bloc, suite ràpida, ruff i pyright (estricte) en verd; CI de
Windows en verd; cap dependència nova.
Fitxers permesos: src/passimaker/ffmpeg/_mp3.py (i _process.py només si cal per a la cancel·lació, explicant-ho),
tests/integration/ffmpeg/test_mp3.py, tests/unit/ffmpeg/, docs/sessions/C04.md, la fila del C04 a
docs/PLA_YOUTUBE.md i l'apartat Estat del CLAUDE.md.
Condició d'aturada: la del CLAUDE.md.
```

### C05 · Diàleg "Música de YouTube"
- **Fa:** `ui/youtube_dialog.py` i l'entrada al menú de [+ Música]. Camp únic de cerca/enllaç, llista de resultats
  amb miniatures, cua de descàrregues amb progrés per fila, carpeta de destinació, casella "Afegeix al projecte", botó
  [Obre a YouTube], selector de carpeta a cada descàrrega i **avís de conformitat del §2.0** (casella obligatòria,
  botó desactivat fins que es marca, conformitat per sessió del programa, retirar-la). Tot fora del fil de la interfície. En tancar el diàleg amb descàrregues actives, pregunta.
- **Proves:** pytest-qt amb el backend substitut: cerca, enllaç, selecció múltiple, cancel·lació, error de xarxa,
  afegir al projecte (comprova l'ordre `AddSongs` al controlador), textos traduïbles.
- **Acceptació:** cap operació de més de 50 ms al fil de la interfície; el programa sense xarxa s'obre i funciona igual.
- **En paral·lel amb el C07 i el C08**: no depèn de la gravació; tot el que fa servir ja és a `main` (comprovat el
  25/10/2026: fitxers, especificació, contractes, valors i 1.303 proves en verd).

```text
Bloc C05: Música de YouTube, finestra "Música de YouTube". Model: Sonnet.
ATENCIÓ, BLOCS EN PARAL·LEL: aquest bloc (C05) es pot fer alhora que el C07 i el C08 (gravació del so), en altres
sessions. No facis res fora d'aquest bloc: modifica només els fitxers permesos de sota, encara que vegis errors o
millores en d'altres (anota-les a docs/sessions/C05.md). No toquis src/passimaker/recorder, src/passimaker/youtube,
src/passimaker/ffmpeg, tools/, packaging/, .github/ ni res del C07 o del C08. A la taula del §4.1 de
docs/PLA_YOUTUBE.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i la línia del C05, i fes-ho després de
portar main a la teva branca (fusió, sense reescriure la història). Si en acabar un altre bloc ja és a main, torna a
portar main i resol el conflicte conservant els canvis de l'altre bloc.
Context: el C01, el C02, el C03 i el C04 són a main. Llegeix docs/PLA_YOUTUBE.md (§0, §2 i la fitxa del C05),
docs/ESPECIFICACIO.md §1.7 bis, docs/CONTRACTES.md (§13 i §15), docs/sessions/C03.md (sobretot "Decisions preses en
aquesta sessió") i docs/sessions/C04.md, src/passimaker/youtube/, src/passimaker/ui/main_window.py (add_music_action,
choose_music, add_songs), src/passimaker/ui/dialogs.py, src/passimaker/ui/music_strip.py, tests/fakes/youtube.py i
tests/ui/conftest.py.
Branca: bloc/C05-dialeg-youtube des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: la finestra "Música de YouTube" completa, provada amb el backend substitut, sense xarxa a les proves.
Fes:
1. [+ Música] passa a ser un botó amb menú: "Des de fitxers…" (el que fa ara) i "Des de YouTube…". Deixa-ho preparat
   perquè el C10 hi afegeixi "Grava el que sona…" amb una sola línia.
2. src/passimaker/ui/youtube_dialog.py (no modal), amb tot el que diu ESPECIFICACIO §1.7 bis:
   - avís de conformitat (§2.0 del pla): casella obligatòria, botó desactivat fins que es marca, conformitat per
     sessió del programa (youtube.consent), "Retira la conformitat";
   - camp únic de cerca o enllaç (parse_link), resultats amb miniatura (fetch_thumbnail), títol, canal i durada; els
     directes i els massa llargs en gris amb el motiu; [Més resultats]; [Obre a YouTube] amb QDesktopServices.openUrl;
   - selecció múltiple, [Descarrega en MP3], selector de carpeta a cada descàrrega a través de ui/dialogs.py (proposa
     la darrera carpeta), cua amb 2 baixades alhora (defaults), progrés per fila (descarregant, convertint, fet),
     cancel·lació per fila;
   - download_audio i després ffmpeg.convert_to_mp3, amb safe_target_path demanat just abans de convertir cada cançó
     (el C03 avisa que no reserva el nom); casella "Afegeix al projecte en acabar" amb MainWindow.add_songs;
     [Mostrar a la carpeta];
   - errors amb passimaker.i18n.message: cada error de YouTube, OSError (disc ple, sense permís) com un error
     d'escriptura; cancel·lar dona CancelledError a youtube però torna normalment a convert_to_mp3 (vegeu C03 i C04);
   - en tancar amb baixades actives, pregunta; si es confirma, cancel·la i no deixa fitxers a mitges.
   Tot el que toca la xarxa o el disc, fora del fil de la interfície (regla 6). La finestra rep el backend per
   paràmetre (per defecte, YtDlpBackend) per poder-la provar amb tests/fakes/youtube.py.
3. Proves pytest-qt (tests/ui/test_youtube_dialog.py), amb el substitut i la xarxa bloquejada: avís (casella, cancel·lar
   sense conformitat, conformitat per sessió, retirar-la), cerca, enllaç, més resultats, selecció múltiple, cua de 2,
   cancel·lació, cada error, afegir al projecte (l'ordre AddSongs arriba al controlador), tancar amb baixades actives,
   textos traduïbles (tests/ui/test_translations.py continua passant). Cap prova obre connexions.
4. docs/PLA_YOUTUBE.md: només la fila del C05 de la taula del §4.1. CLAUDE.md, apartat Estat: una línia del C05.
Criteris d'acceptació: tot el §1.7 bis funciona amb el substitut; cap operació de més de 50 ms al fil de la interfície;
el programa sense xarxa s'obre i funciona igual; la prova d'arquitectura continua passant; suite ràpida, ruff i
pyright en verd; cap dependència nova.
Fitxers permesos: src/passimaker/ui/youtube_dialog.py (nou), src/passimaker/ui/main_window.py (només el menú de
[+ Música] i obrir la finestra), src/passimaker/ui/dialogs.py (només el selector de carpeta, si cal),
tests/ui/test_youtube_dialog.py (nou), tests/ui/conftest.py (només si cal un fixture), docs/sessions/C05.md, la fila
del C05 a docs/PLA_YOUTUBE.md i l'apartat Estat del CLAUDE.md. Si cal tocar-ne cap altre (p. ex. un valor nou a
defaults.py o un canvi a passimaker.youtube), atura't i proposa-ho.
Condició d'aturada: la del CLAUDE.md. A docs/sessions/C05.md, anota les decisions que hagis pres i la prova manual
que l'usuari ha de fer a Windows (un pas cada vegada).
```

### C06 · Empaquetat, guia i versió 1.2.0 (YouTube i gravació)
- **Fa:** PyInstaller amb yt-dlp, `yt-dlp-ejs` i Deno (C02) i, si el C08 en tria una, la dependència de captura;
  `tools/construir_zip.ps1`; CI; apartats nous a la guia (`ui/help.py`): música de YouTube i "Grava el que sona" (sense
  apartat legal de la gravació, G2); a "Imprevistos": "YouTube ha canviat" i "No s'ha gravat cap so"; CHANGELOG;
  versió 1.2.0; flux de manteniment del §6.
- **Local:** prova de l'usuari amb el ZIP: una cerca i un enllaç de YouTube; una cançó gravada de Spotify i una del
  navegador; totes afegides a un passi i exportades.
- **Acceptació:** prova de l'usuari correcta; versió publicada amb `publicar.yml`.

### C07 · Gravació: decisió 0013, contracte i especificació
- **Fa:** `docs/decisions/0013-gravar-el-so.md`; ESPECIFICACIO §1.7 ter (annex §2); CONTRACTES §16 (annex §3.2) i §13
  (la interfície pot fer servir `recorder`); valors nous a `defaults.py`; esquelet de `src/passimaker/recorder/`; marca
  `so` a `pyproject.toml`.
- **No fa:** cap dependència nova, cap implementació, ni el trasllat de `safe_target_path` (és del C09, quan el C03
  sigui a `main`).

```text
Bloc C07: Gravar el so de l'ordinador, decisió, contracte i especificació. Model: Sonnet.
ATENCIÓ, BLOCS EN PARAL·LEL: aquest bloc (C07) es fa alhora que el C08 (prova de viabilitat de la gravació), en una
altra sessió, i potser també que el C03 (PR #58). No facis res fora d'aquest bloc: modifica només els fitxers
permesos de sota, encara que vegis errors o millores en d'altres (anota-les a docs/sessions/C07.md). No toquis
tools/, packaging/, .github/ ni res del C08 o del C03. A la taula del §4.1 de docs/PLA_YOUTUBE.md i a l'apartat
Estat del CLAUDE.md, escriu només la fila i la línia del C07; si en acabar un altre bloc ja és a main, porta main a
la branca (fusió, sense reescriure la història) i resol el conflicte conservant els canvis de l'altre bloc.
Context: PassiMaker 1.1.0 és a main amb el C01, el C02 i el C04 de la música de YouTube. Llegeix docs/PLA_GRAVACIO.md
(sencer: és l'annex aprovat de la gravació, decisions G1–G9), docs/PLA_YOUTUBE.md (§0 i §4, fitxa del C07),
docs/decisions/0012-musica-de-youtube.md (com a model), docs/CONTRACTES.md, docs/ESPECIFICACIO.md §1.7 i §1.7 bis,
src/passimaker/model/defaults.py, src/passimaker/youtube/ (com a model d'esquelet) i tests/unit/test_architecture.py.
Branca: bloc/C07-decisio-gravacio des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: deixar decidit i definit tot el que el C08, el C09 i el C10 necessiten, sense implementar-ho.
Fes:
1. docs/decisions/0013-gravar-el-so.md: gravació del so de l'ordinador amb WASAPI loopback, sense xarxa, sense avís
   (G2), gravacions interrompudes i les que arriben als 30 min s'esborren (G1, G5), ones per canal (G3), micròfon i
   entrada de línia opcionals per selecció (G6), MP3 192 kbps (G7), una sola versió 1.2.0 (G4), tecnologia de captura
   a decidir al C08 (annex §3.1; sounddevice primer). Data 25/10/2026.
2. docs/ESPECIFICACIO.md: §1.7 ter "Grava el que sona", a partir de l'annex §2 (recorregut, valors, errors,
   interrompuda vs. acabada, ones, fora d'abast).
3. docs/CONTRACTES.md: §16 nou (passimaker.recorder, annex §3.2, amb Monitor, peaks_since i overview); §13 (la
   interfície pot fer servir recorder); anota que safe_target_path passarà a passimaker.common al C09.
4. src/passimaker/model/defaults.py: els valors de l'annex §2.2 i §2.4 (llindars, aturada per silenci, durada màxima i
   avís, retall, espai mínim, finestra de les ones, columnes per segon), afegits al final.
5. src/passimaker/recorder/: tipus (AudioSource, SourceKind, RecordingResult, StopReason), errors amb les claus de
   missatge a passimaker.i18n (textos de l'annex §2.3), protocol CaptureBackend i signatures de Recorder, Monitor,
   list_sources i trim_silence sense implementació (avisen que no estan implementades). Sense Qt i sense xarxa.
6. pyproject.toml: marca "so" (proves que necessiten una targeta de so real; excloses per defecte i a la CI).
7. tests/unit/test_architecture.py: comprova que recorder no importa Qt ni mòduls de xarxa (si les proves que ja
   hi ha ja ho cobreixen, afegeix-hi només un cas explícit).
8. docs/PLA_YOUTUBE.md: només la fila del C07 a la taula del §4.1. CLAUDE.md, apartat Estat: una línia del C07.
   Si el C03 (PR #58) ja és a main, porta main a la branca (fusió) i resol els conflictes d'aquests fitxers i del
   pyproject.toml (el C03 hi afegeix la marca "xarxa").
Criteris d'acceptació: decisió, especificació i contractes coherents amb l'annex; tots els tipus i signatures de
l'annex §3.2 existeixen; suite ràpida, ruff i pyright en verd; cap dependència nova.
Fitxers permesos: els dels punts 1–8, docs/sessions/C07.md i tests/unit/recorder/ (proves dels tipus i, si vols, de
trim_silence, que és pur). Res de src/passimaker/youtube, src/passimaker/ui ni src/passimaker/ffmpeg.
Condició d'aturada: la del CLAUDE.md. A docs/sessions/C07.md, anota les decisions que hagis pres.
```

### C08 · Gravació: prova de viabilitat a Windows (spike)
- **En paral·lel amb el C07**: no fa servir res del C07 (es basa en l'annex).
- **Fa:** `ProvaGravacio.exe` (com el `ProvaYoutube` del C02) que llista els orígens, grava 20 s i escriu un informe;
  comprova la tecnologia de captura (annex §3.1) i els casos reals al PC de l'usuari.
- **Acceptació:** informe a `docs/sessions/C08.md` amb el resultat de cada punt i la recomanació (seguir amb
  sounddevice, passar a `soundcard`, o aturar).

```text
Bloc C08: Gravar el so de l'ordinador, prova de viabilitat a Windows (spike). Model: Opus.
ATENCIÓ, BLOCS EN PARAL·LEL: aquest bloc (C08) es fa alhora que el C07 (decisió 0013, contracte i especificació de la
gravació), en una altra sessió, i potser també que el C03 (PR #58). No facis res fora d'aquest bloc: modifica només
els fitxers permesos de sota, encara que vegis errors o millores en d'altres (anota-les a docs/sessions/C08.md). No
toquis docs/decisions/, docs/CONTRACTES.md, docs/ESPECIFICACIO.md, src/ ni res del C07 o del C03; la decisió 0013 i el
contracte §16 els escriu el C07, i aquí no hi són: fes servir l'annex docs/PLA_GRAVACIO.md. A la taula del §4.1 de
docs/PLA_YOUTUBE.md i a l'apartat Estat del CLAUDE.md, escriu només la fila i la línia del C08; si en acabar un altre
bloc ja és a main, porta main a la branca (fusió, sense reescriure la història) i resol el conflicte conservant els
canvis de l'altre bloc.
Context: el C01, el C02 i el C04 són a main; el C07 es fa alhora. Llegeix docs/PLA_GRAVACIO.md (§0, §1, §2.2, §3,
§5), docs/PLA_YOUTUBE.md (fitxa del C08), docs/CONTRACTES.md §8, src/passimaker/preview/sound.py (com fa servir
sounddevice el programa), i com a model del C02: tools/prova_youtube.py, packaging/ProvaYoutube.spec, el treball
"prova-youtube-windows" de .github/workflows/ci.yml i docs/sessions/C02.md.
Branca: bloc/C08-viabilitat-gravacio des de main actualitzat (o la que imposi la sessió al núvol; anota-ho).
Objectiu: comprovar a Windows, abans d'implementar passimaker.recorder (C09), que es pot gravar el so de l'ordinador
des d'un ZIP de PyInstaller, i triar la tecnologia. No s'implementa passimaker.recorder.
Fes:
1. Esbrina si sounddevice 0.5.x (ja és una dependència) veu les sortides de Windows com a entrades WASAPI "[Loopback]"
   i hi pot gravar. Si no: proposa soundcard (o PyAudioWPatch) a docs/sessions/C08.md (llicència, mida, versió) i
   atura't sense afegir-la (regla 10).
2. tools/prova_gravacio.py, sense Qt i sense consola (finestra de missatge de Windows en acabar, amb ctypes, com el
   C02): llista tots els orígens (sortides loopback i entrades: micròfon, línia) amb freqüència i canals; grava 20 s de
   l'origen per defecte (o el que es triï amb --origen N) a un WAV temporal mentre calcula el nivell i els pics per
   canal; detecta blocs perduts i canvis de dispositiu; comprova el WAV amb passimaker.ffmpeg.probe i el converteix a
   MP3 amb passimaker.ffmpeg.convert_to_mp3; escriu informe_prova_gravacio.txt al costat de l'executable (versions,
   orígens, nivells, pics, blocs perduts, temps, errors complets). Opcions: --durada S, --origen N, --llista,
   --sense-dispositiu (només versions, per a la CI), --conservar.
3. packaging/ProvaGravacio.spec (console=False, mateix FFmpeg) i un treball nou a .github/workflows/ci.yml que
   construeix el ZIP "ProvaGravacio-win64", l'executa amb --sense-dispositiu i el publica com a artefacte. No canviïs
   el ZIP de PassiMaker ni els treballs que ja hi ha.
4. Proves (a Linux, sense targeta de so): l'script es pot importar sense obrir cap dispositiu; execució
   --sense-dispositiu; execució completa amb un backend fals (tons i silenci); la prova d'arquitectura continua passant.
5. docs/sessions/C08.md amb els punts: (1) sounddevice sí o no; (2) Spotify d'escriptori, YouTube a Chrome o Edge i el
   Reproductor multimèdia de Windows; (3) auriculars Bluetooth i canvi de sortida a mitges; (4) si el volum de Windows i
   el de cada aplicació afecten la gravació; (5) cap demanda de permís de micròfon per al loopback, ni avís de
   l'antivirus, ni finestra de consola; (6) blocs perduts en una gravació de 10 min; (7) el micròfon, si l'usuari el
   tria (G6); (8) mida del ZIP. Els punts 2–7 els fa l'usuari al seu PC: dona-li les instruccions pas a pas (un pas cada
   vegada) per baixar l'artefacte, executar-lo i enganxar-te l'informe.
6. docs/PLA_YOUTUBE.md: només la fila del C08 de la taula del §4.1. CLAUDE.md, apartat Estat: una línia del C08.
   Si mentrestant s'ha fusionat un altre bloc a main (el C07 o el C03), porta main a la branca (fusió) i resol el
   conflicte d'aquests fitxers; si l'usuari aprova una dependència nova, també el del pyproject.toml (el C07 hi afegeix
   la marca "so").
Criteris d'acceptació: ZIP de prova generat per la CI; informe de l'usuari amb els punts 2–7; recomanació final a
docs/sessions/C08.md; suite ràpida, ruff i pyright en verd.
Fitxers permesos: tools/prova_gravacio.py, packaging/ProvaGravacio.spec, .github/workflows/ci.yml (només el treball
nou), tests/unit/test_prova_gravacio.py, docs/sessions/C08.md, la fila del C08 a docs/PLA_YOUTUBE.md i l'apartat Estat
del CLAUDE.md; pyproject.toml i uv.lock només si l'usuari aprova una dependència nova. Res de src/passimaker.
Condició d'aturada: la del CLAUDE.md. També t'atures si sounddevice no serveix (punt 1) o si la prova a Windows falla
dues vegades pel mateix motiu: anota-ho a docs/sessions/C08.md amb el pas següent.
```

### C09 · Nucli `passimaker.recorder`
- **Fa:** captura en un fil, WAV temporal escrit a mesura, pics per a les ones (memòria circular, vista de tota la
  gravació), mesurador, "comença quan soni", aturada per silenci, retall; disc ple, desconnexió, error del so i durada
  màxima **esborren el fitxer** (G1, G5); neteja de restes en arrencar; trasllat de `safe_target_path` a
  `passimaker.common` (cal el C03 a `main`).
- **Proves:** substitut `FakeCaptureBackend` (tons i silencis), Hypothesis per al retall i el silenci, cada causa
  d'interrupció sense deixar fitxers, prova de no-xarxa, i proves `so` per al PC de l'usuari.
- Prompt: s'escriu en tancar el C08 (depèn de la tecnologia triada).

### C10 · Finestra "Grava el que sona"
- **Fa:** `ui/record_dialog.py` i `ui/wave_view.py` (ones per canal en directe i de tota la gravació, annex §2.4),
  entrada al menú [+ Música ▾] (el crea el C05), orígens amb el micròfon opcional, [● Grava] [■ Atura] [Descarta],
  avís de temps a falta d'1 min, selector de carpeta i nom, conversió amb progrés, "Afegeix al projecte"; en tancar
  mentre es grava, pregunta i esborra (G1). Sense avís legal (G2).
- **Proves:** pytest-qt amb el substitut; rendiment de les ones (repintat < 5 ms per fotograma); textos traduïbles.
- Prompt: s'escriu en tancar el C05 i el C09.

---

## 5. Riscos

Riscos de la gravació (C07–C10): annex `docs/PLA_GRAVACIO.md` §5.

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

**Pendent de la teva part:** obrir dues sessions noves al núvol i enganxar-hi els prompts del C02 i del C04 (fitxes del §4).
