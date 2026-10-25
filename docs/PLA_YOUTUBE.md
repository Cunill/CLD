# PassiMaker: pla de la funció "Música de YouTube"

> Proposta de funcionalitat nova: cercar cançons a YouTube i descarregar-les en MP3, des de la cerca o amb l'enllaç
> directe, per afegir-les al passi.
> Versió del pla: 0.1 · Data: 25/10/2026 · Estat: **pendent d'aprovació** (vegeu "Per decidir" al final)
> Versió del programa prevista: **1.2.0**

---

## 1. Què canvia respecte del pla original

Aquesta funció xoca amb tres decisions preses i amb dues regles del CLAUDE.md. Cal aprovar-ho abans de programar res
(decisió nova **0012**).

| Què | Ara | Amb aquesta funció |
|---|---|---|
| Xarxa (PLA, Pas 0) | Totalment fora de línia | Connexió a internet **només** quan l'usuari obre "Música de YouTube". La resta del programa continua funcionant sense xarxa. |
| Regla 10 (dependències) | — | Dependència nova: **yt-dlp** (llicència Unlicense, domini públic). Probablement també **Deno** (entorn JavaScript que yt-dlp necessita per a YouTube des de finals del 2025; es confirma al Y1). |
| Regla 7 (subprocess) | Només `passimaker.ffmpeg` llança processos | yt-dlp llança Deno per dins. El nostre codi no crida subprocess; cal comprovar que no s'obren finestres de consola i, si cal, ajustar la prova de la regla 7 (Y1). |
| Mida del ZIP | ~150 MB (FFmpeg + Qt) | +~5 MB (yt-dlp) i, si cal Deno, +~40 MB comprimits |
| Manteniment | Versió estable, sense actualitzacions obligatòries | YouTube canvia sovint i trenca yt-dlp cada poques setmanes o mesos: cal publicar versions noves de PassiMaker amb yt-dlp actualitzat (§6). |

### 1.1 Aspectes legals (important)

- Les **Condicions del servei de YouTube** prohibeixen descarregar contingut si YouTube no ofereix un botó de
  descàrrega. Fer-ho no és un delicte per si mateix, però incompleix el contracte d'ús de YouTube.
- La majoria de cançons de YouTube tenen **drets d'autor**. Fer-les servir en un vídeo, encara que sigui d'ús intern de
  l'estudi, pot necessitar llicència; si el vídeo es publica (YouTube, Instagram…), la plataforma el pot silenciar o
  bloquejar.
- Proposta per reduir el risc (es decideix al punt 2 de "Per decidir"):
  1. Avís clar la primera vegada que s'obre la funció ("Descarrega només música que tinguis dret a fer servir"), amb
     una casella "No ho tornis a mostrar".
  2. Casella **"Només Creative Commons"** a la cerca, marcada per defecte (YouTube té aquest filtre).
  3. A la guia, un apartat amb fonts de música lliure: Biblioteca d'àudio de YouTube (descàrrega oficial des de YouTube
     Studio), Free Music Archive, Pixabay Music.

---

## 2. Especificació funcional

### 2.1 Recorregut

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Franja de música → [+ Música ▾] → **"Des de YouTube…"** | S'obre el diàleg "Música de YouTube" (no modal: es pot continuar treballant). La primera vegada, l'avís del §1.1. |
| 2a | Escriu "Ludovico Einaudi Nuvole Bianche" i prem Retorn | Llista de 10 resultats: miniatura, títol, canal, durada. Es poden carregar 10 més ("Més resultats"). |
| 2b | O bé enganxa un enllaç (`youtube.com/watch?v=…`, `youtu.be/…`, `music.youtube.com/…`, `shorts/…`) | El camp el reconeix sol i mostra un únic resultat amb les dades del vídeo. |
| 3 | Selecciona un o diversos resultats i prem **[Descarrega en MP3]** | Cada fila mostra el progrés (descarregant → convertint → fet). Es pot cancel·lar cada descàrrega. |
| 4 | Casella **"Afegeix al projecte en acabar"** (marcada per defecte) | En acabar, la cançó s'afegeix a la franja de música amb l'ordre `AddSongs` (desfer funciona com sempre). |
| 5 | [Mostrar a la carpeta] | Obre la carpeta on s'ha desat l'MP3. |

### 2.2 Comportament i valors per defecte

| Paràmetre | Per defecte | Notes |
|---|---|---|
| Resultats per pàgina | 10 | `defaults.YOUTUBE_RESULTS_PER_PAGE` |
| Filtre Creative Commons | Activat (si s'aprova) | `defaults.YOUTUBE_CREATIVE_COMMONS_ONLY` |
| Durada màxima acceptada | 20 min | Evita descarregar per error mescles d'hores. `defaults.YOUTUBE_MAX_DURATION_S`. Els resultats més llargs surten en gris amb el motiu. |
| Format | MP3, 192 kbps, 48 kHz estèreo | `defaults.YOUTUBE_MP3_BITRATE_KBPS`. 48 kHz perquè és la freqüència del mesclador (CONTRACTES §0). |
| Carpeta de destinació | `Documents\PassiMaker\Música` | Es pot canviar al diàleg; es recorda entre sessions. |
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

Llistes de reproducció senceres, vídeo (només àudio), altres webs que yt-dlp admet, escoltar la cançó abans de
descarregar-la (es pot afegir després: obrir l'enllaç al navegador és trivial i ja seria útil; vegeu "Per decidir").

---

## 3. Arquitectura

```
ui/youtube_dialog.py  (Qt)                       ── regla 1: Qt només a ui/
   │  QThreadPool / fils de treball                ── regla 6
   ▼
passimaker.youtube  (nucli, sense Qt)  ── mòdul nou
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
| `search(consulta, limit, offset, creative_commons, cancel)` | — | `tuple[SearchResult, ...]` |
| `resolve(video_id, cancel)` | — | `SearchResult` |
| `download_audio(video_id, carpeta_temp, progress, cancel)` | — | `Path` del fitxer d'àudio original |
| `ffmpeg.convert_to_mp3(origen, destí, kbps, metadades, progress, cancel)` | — | `None` (escriu a un fitxer temporal i el reanomena en acabar) |
| `safe_target_path(carpeta, títol)` | — | `Path` lliure, vàlid a Windows |

`SearchResult`: `video_id`, `title`, `channel`, `duration_s` (`float | None`), `thumbnail_url`, `is_live`,
`url`. Errors (hereten de `PassiMakerError`): `YoutubeOfflineError`, `YoutubeUnavailableError`,
`YoutubeBrokenError`, `YoutubeTooLongError`.

---

## 4. Blocs de desenvolupament

Mateix protocol que la resta (CLAUDE.md): un bloc per sessió, branca `bloc/YNN-nom`, nota a `docs/sessions/YNN.md`.

| Bloc | Nom | Mida | Depèn de | On |
|---|---|---|---|---|
| Y0 | Decisió 0012, contracte i especificació | Petit (0,5 s.) | aprovació | Núvol |
| Y1 | Prova de viabilitat a Windows | Petit (0,5 s.) | Y0 | Núvol + **local** |
| Y2 | Nucli `passimaker.youtube` | Mitjà (1 s.) | Y1 | Núvol |
| Y3 | Conversió a MP3 al pont FFmpeg | Petit (0,5 s.) | Y0 (en paral·lel amb Y2) | Núvol |
| Y4 | Diàleg "Música de YouTube" | Gran (1,5 s.) | Y2, Y3 | Núvol |
| Y5 | Empaquetat, guia i versió 1.2.0 | Mitjà (1 s.) | Y4 | Núvol + **local** |

**Total: ~5 sessions ≈ 5 setmanes** a 4 h/setmana (més la prova de l'usuari).

### Y0 · Decisió, contracte i especificació
- **Fa:** `docs/decisions/0012-musica-de-youtube.md` (xarxa, dependències, regla 7, aspectes legals, manteniment);
  CONTRACTES §15 i ampliació del §8 (`convert_to_mp3`); ESPECIFICACIO §1.7 bis (el §2 d'aquest pla); valors nous a
  `defaults.py`; tipus i signatures sense implementació a `src/passimaker/youtube/`.
- **Acceptació:** documents aprovats per l'usuari; ruff i pyright nets; la prova de "Qt fora del nucli" cobreix el
  mòdul nou.

### Y1 · Prova de viabilitat (spike)
Bloc curt per eliminar els riscos grossos abans d'invertir-hi més.
- **Fa:** una branca amb un script mínim que, des del ZIP de PyInstaller a Windows, cerca, baixa un àudio i el
  converteix. Comprova: (1) si yt-dlp necessita Deno i com s'empaqueta; (2) que no s'obre cap finestra de consola des
  d'una aplicació sense consola; (3) que l'antivirus (Windows Defender) no bloqueja res; (4) que funciona darrere de la
  xarxa de l'estudi (servidor intermediari?); (5) mida final del ZIP.
- **Local:** l'usuari executa el ZIP de prova al seu PC (un pas cada vegada).
- **Acceptació:** informe a `docs/sessions/Y01.md` amb el resultat de cada punt i la recomanació final (seguir, canviar
  d'enfocament o abandonar).

### Y2 · Nucli `passimaker.youtube`
- **Fa:** `links.py`, `search.py`, `download.py`, `files.py` amb el backend injectable i el substitut de proves.
  Cancel·lació i progrés amb `CancelToken` i `ProgressCallback`. Traducció dels errors de yt-dlp als errors propis.
- **Proves:** enllaços (Hypothesis: formats vàlids i no vàlids, paràmetres extra com `&t=30s`, `&list=…`), noms de
  fitxer (caràcters reservats de Windows, noms reservats com `CON`, longitud, duplicats), cancel·lació, durada màxima,
  directes, errors. Una prova `xarxa` amb un vídeo Creative Commons estable.
- **Acceptació:** cobertura de totes les files de la taula d'errors del §2.3; cap import de PySide6; pyright estricte.

### Y3 · Conversió a MP3
- **Fa:** `passimaker.ffmpeg.convert_to_mp3` (libmp3lame, 48 kHz, estèreo, etiquetes ID3, progrés, cancel·lació,
  escriptura atòmica). Comprova que l'FFmpeg 7.1.1 fixat porta libmp3lame (la build GPL sí).
- **Proves:** amb els tons de `tests/fixtures` (WAV, M4A): durada conservada (±50 ms), 48 kHz, etiquetes llegibles,
  rutes amb accents i emojis, cancel·lació a mitges sense deixar fitxers.

### Y4 · Diàleg "Música de YouTube"
- **Fa:** `ui/youtube_dialog.py` i l'entrada al menú de [+ Música]. Camp únic de cerca/enllaç, llista de resultats
  amb miniatures, cua de descàrregues amb progrés per fila, carpeta de destinació, casella "Afegeix al projecte", avís
  legal la primera vegada. Tot fora del fil de la interfície. En tancar el diàleg amb descàrregues actives, pregunta.
- **Proves:** pytest-qt amb el backend substitut: cerca, enllaç, selecció múltiple, cancel·lació, error de xarxa,
  afegir al projecte (comprova l'ordre `AddSongs` al controlador), textos traduïbles.
- **Acceptació:** cap operació de més de 50 ms al fil de la interfície; el programa sense xarxa s'obre i funciona igual.

### Y5 · Empaquetat, guia i versió
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
| Problema legal (condicions de YouTube, drets d'autor) | Mitjana | Reclamació o vídeo silenciat si es publica | §1.1: avís, filtre Creative Commons, fonts de música lliure |
| L'antivirus marca Deno o yt-dlp | Baixa–mitjana | El ZIP no s'executa | Es comprova al Y1 |
| Finestres de consola en llançar Deno | Mitjana | Molèstia visual | Es comprova al Y1; si passa, s'ajusta la configuració o es descarta Deno |
| El ZIP creix massa | Baixa | Descàrrega més lenta | Es mesura al Y1 |

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

1. **Seguir endavant?** (a) Sí, amb aquest pla; (b) sí, però començant només per la prova de viabilitat (Y1) i decidir
   després; (c) no: només afegir a la guia on trobar música lliure.
2. **Aspectes legals:** (a) avís + filtre "Només Creative Commons" marcat per defecte (recomanat); (b) només l'avís;
   (c) res.
3. **Format de sortida:** (a) MP3 de 192 kbps (recomanat: bona qualitat, fitxers petits); (b) MP3 de 320 kbps;
   (c) desar l'àudio original (M4A) sense convertir-lo, que no perd qualitat i el programa ja el llegeix.
4. **Carpeta de destinació per defecte:** (a) `Documents\PassiMaker\Música` (recomanat); (b) la carpeta del projecte
   obert; (c) preguntar-ho cada vegada.
5. **Escoltar abans de descarregar:** (a) botó "Obre a YouTube" que obre el navegador (recomanat, gairebé gratuït);
   (b) res.
6. **PR d'aquest pla:** (a) obrir una PR amb aquest document perquè quedi a `main`; (b) deixar-lo només a la branca.

**Pendent de la teva part:** respondre els punts anteriors. Si tries seguir, el pas següent és el bloc Y0 al núvol.
