# PassiMaker: ampliació del pla, "Grava el que sona"

> Proposta d'ampliació del pla de la música de YouTube (`docs/PLA_YOUTUBE.md`): gravar en directe l'àudio que sona a
> l'ordinador (YouTube al navegador, Spotify, qualsevol reproductor) i desar-lo en MP3 per fer-lo servir al passi.
> Versió: 0.2 · Data: 25/10/2026 · Estat: **esborrany, pendent d'aprovació** (decisions ja preses al §0)
> **No modifica el pla vigent.** `docs/PLA_YOUTUBE.md` (taula de seguiment §4.1, decisió 0012, CLAUDE.md) no es toca
> fins que l'usuari ho digui; llavors s'hi incorporen els blocs d'aquest document (§6).

---

## 0. Decisions de l'usuari (25/10/2026)

| # | Tema | Decisió |
|---|---|---|
| G1 | Gravacions interrompudes | **No es desen mai.** Si la gravació s'acaba per qualsevol cosa que no sigui l'usuari o el silenci (sortida desconnectada, disc ple, error del so, tancament del programa o de la finestra, tancament inesperat), s'esborra tot (§2.3) |
| G2 | Avís legal | **Cap avís** a la funció de gravar (ni casella ni diàleg) |
| G3 | Ones | **Es mostren les ones del canal que s'està gravant**, en directe, un carril per canal (§2.4) |

---

## 1. Què canvia respecte del pla vigent

| Què | Ara | Amb aquesta ampliació |
|---|---|---|
| Entrades de música | Fitxers i (pla vigent) YouTube | També **gravació en directe** del so de l'ordinador |
| Xarxa | Només la funció de YouTube, després del seu avís | **Cap canvi**: gravar no es connecta enlloc. Funciona sense internet. |
| Dependències | sounddevice (ja hi és, per a la previsualització) | **Probablement cap de nova**: es prova primer amb sounddevice (§3.1). Si no serveix, es proposa `soundcard` (llicència BSD) o `PyAudioWPatch` (MIT); es decideix al C08. |
| Regla 7 (subprocess) | — | Sense canvis: la captura és dins del procés; la conversió a MP3 és el `convert_to_mp3` del C04. |
| Sistema | Només Windows | Igual. La captura del so del sistema es fa amb **WASAPI loopback**, la manera estàndard de Windows (sense controladors ni programes externs com "Stereo Mix" o VB-Cable). |

### 1.1 Aspectes legals (important)

- Gravar música amb drets d'autor té els mateixos límits que descarregar-la (pla vigent §1.1): fer-la servir en un
  vídeo pot necessitar llicència.
- **Spotify** prohibeix expressament a les seves condicions gravar o "extreure" el contingut. Netflix, Apple Music i
  altres, igual.
- **Decisió G2: el programa no mostra cap avís** en gravar. Aquesta informació és només per a l'usuari, en aquest
  pla. La guia (C11) es limita a explicar com gravar.
- El programa **no** intenta saltar cap protecció: si una aplicació fa servir el mode exclusiu o protegeix l'àudio, la
  gravació surt en silenci i el programa ho avisa (§2.3).

---

## 2. Especificació funcional

### 2.1 Recorregut

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Franja de música → [+ Música ▾] → **"Grava el que sona…"** | S'obre la finestra "Grava el que sona" (no modal), directament, sense cap avís (G2). |
| 2 | Tria l'origen (per defecte: **la sortida de so que fa servir Windows**, p. ex. "Altaveus" o els auriculars Bluetooth) | Les **ones** (§2.4) i el mesurador de nivell mostren en directe si arriba so, **abans de gravar** (no es desa res). |
| 3 | Posa en marxa la cançó a Spotify, al navegador… i prem **[● Grava]** | Comença a gravar: les ones canvien de color (vermell = s'està gravant), temps transcorregut, mesurador, espai lliure al disc. Opció "Comença quan soni" (§2.2): espera el primer so. |
| 4 | **[■ Atura]** (o s'atura sol després de N segons de silenci, si està activat) | Mostra l'ona sencera de la gravació amb els silencis que es retallaran ombrejats. Retalla el silenci de l'inici i del final, demana on desar-lo (decisió 4 del pla vigent: es pregunta cada vegada) i el nom (proposa "Gravació 25-10-2026 18.30"). Converteix a MP3 192 kbps. |
| 5 | Casella **"Afegeix al projecte en acabar"** (marcada per defecte) | La cançó s'afegeix a la franja amb `AddSongs` (es pot desfer). |
| — | [Descarta] | Esborra la gravació sense desar-la (amb confirmació si dura més de 10 s). |
| — | Tancar la finestra o el programa mentre es grava | Pregunta "La gravació s'esborrarà. Vols aturar-la i sortir?". Si es confirma, s'esborra (G1). |

### 2.2 Comportament i valors per defecte

| Paràmetre | Per defecte | Notes (valors a `defaults.py`) |
|---|---|---|
| Origen | Sortida de so per defecte de Windows | Llista de les sortides (loopback). Opcional: també entrades (micròfon, entrada de línia), vegeu "Per decidir" 3. |
| "Comença quan soni" | Activat | Comença a desar quan el nivell supera −50 dBFS. `RECORD_START_THRESHOLD_DBFS` |
| Aturada automàtica per silenci | Activada, 5 s | 1–60 s. `RECORD_SILENCE_STOP_S`. Útil per gravar una sola cançó. |
| Retallar silenci inicial i final | Activat | Llindar −50 dBFS, conserva 0,2 s de marge. `RECORD_TRIM_*` |
| Durada màxima | 30 min | Protegeix el disc si s'oblida aturar-la. `RECORD_MAX_DURATION_S` |
| Format intern | WAV de 32 bits flotants a la carpeta temporal, escrit **a mesura que es grava** | No a la memòria: 30 min ≈ 690 MB. Es considera temporal fins que l'usuari atura i desa: qualsevol interrupció l'esborra (G1). En obrir el programa s'esborren les restes d'un tancament inesperat (`passimaker_gravacio_*.wav` de la carpeta temporal). |
| Format final | MP3 192 kbps, 48 kHz estèreo | El mateix `convert_to_mp3` del C04; el WAV temporal s'esborra en acabar. |
| Freqüència | La de la sortida de Windows (44,1 o 48 kHz) | `convert_to_mp3` la passa a 48 kHz. |
| Espai lliure mínim | 1 GB | Si en queda menys, no comença, i atura la gravació si s'hi arriba. |

**Consell a la finestra** (text fix, traduïble): "Tanca o silencia les altres aplicacions: es grava tot el que sona a
l'ordinador, també els avisos. El volum de Windows no afecta la gravació." (l'últim punt es confirma al C08).

### 2.3 Errors i avisos (en català, traduïbles)

| Situació | Missatge |
|---|---|
| No hi ha cap sortida de so | "No s'ha trobat cap sortida de so per gravar." |
| La sortida canvia o es desconnecta mentre es grava (p. ex. auriculars Bluetooth) | "S'ha desconnectat la sortida de so i la gravació s'ha descartat." |
| Silenci durant tota la gravació | "No s'ha gravat cap so. Comprova que la música sona per la sortida triada; algunes aplicacions no deixen gravar el seu so." |
| Disc ple o gairebé ple | "No queda prou espai al disc per continuar gravant. La gravació s'ha descartat." |
| Durada màxima | "S'ha arribat al màxim de 30 minuts i la gravació s'ha aturat." |
| Error del sistema de so | "No s'ha pogut gravar el so de l'ordinador. La gravació s'ha descartat." (+ detall al registre) |
| Tancament inesperat del programa | Res en tornar a obrir-lo: la gravació no es recupera i el fitxer temporal s'esborra (G1). |

**Interrompuda vs. acabada (G1).** Es desa només si s'acaba per **[■ Atura]**, per l'**aturada automàtica per silenci**
o (pendent, "Per decidir" 2) per la **durada màxima**. Totes les altres causes esborren el fitxer temporal abans de
mostrar el missatge; no es pregunta mai si es vol conservar.

### 2.4 Ones del canal en gravació (G3)

```
┌─ Grava el que sona ─────────────────────────────────────────────────────┐
│ Origen: [Altaveus (Realtek) — per defecte ▾]                            │
│  E ▁▂▅▇█▆▃▂▁▂▄▆█▇▅▃▂▁▁▂▃▅▇▆▄▂▁▁▂▄▆▇█▆▄▂▁   ▏ -6 dB ████████░░          │
│  D ▁▂▄▇█▇▄▂▁▂▃▆█▆▅▃▁▁▁▂▄▅▇▆▃▂▁▁▂▃▆▇█▇▄▂▁   ▏ -7 dB ███████░░░          │
│    ◀──────────────── últims 10 s ────────────────▶                       │
│ ● 02:14   ·   Lliure: 112 GB                                            │
│ ☑ Comença quan soni  ☑ Atura't després de 5 s de silenci                │
│                                  [Descarta]   [■ Atura]                  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Un carril per canal** de l'origen que s'està gravant: esquerre (E) i dret (D) en estèreo; un de sol si l'origen és
  mono. Si l'origen té més canals (p. ex. 5.1), es mostren els dos que es desaran (la mescla estèreo).
- **Ona en directe que es desplaça** (els últims 10 s, `defaults.RECORD_WAVE_WINDOW_S`), amb el pic de cada columna
  (mínim i màxim). Es veu **abans de gravar** (gris, per comprovar que arriba so) i **mentre es grava** (vermell).
- Al costat de cada carril, el **mesurador de nivell** del canal en dBFS, amb marca de saturació (0 dBFS) que es
  queda encesa 2 s.
- **En aturar**, l'ona de **tota la gravació** comprimida a l'amplada de la finestra, amb els silencis de l'inici i del
  final que es retallaran ombrejats.
- Rendiment (regla 6): el nucli calcula els pics al fil de captura (50 columnes per segon i canal, `float32`) i els
  deixa en una memòria circular; la interfície en recull els nous 30 cops per segon i només repinta. Una gravació de
  30 min són 90.000 columnes per canal (< 1 MB).
- **Les ones no fan res més**: no s'hi pot clicar ni seleccionar (editar l'ona continua fora d'abast, §2.5).

### 2.5 Fora d'aquesta ampliació

Gravar una sola aplicació (només Spotify i no la resta: Windows ho permet des del Windows 10 2004, però és molt més
complex; es pot estudiar després), editar l'ona, separar automàticament les cançons d'una llista, gravar vídeo.

---

## 3. Arquitectura

```
ui/record_dialog.py  (Qt)   ── origen, [● Grava] [■ Atura], sense avís (G2)
ui/wave_view.py     (Qt)   ── ones per canal (QPainter), en directe i de tota la gravació (§2.4)
   │  fil de treball (regla 6); ones i mesurador s'actualitzen 30 cops/s amb un QTimer
   ▼
passimaker.recorder  (nucli, sense Qt)  ── mòdul nou
   ├─ devices.py    llista d'orígens (sortides loopback i, si s'aprova, entrades)
   ├─ capture.py    Recorder: start / stop / level / elapsed; backend injectable (protocol CaptureBackend)
   ├─ wavwriter.py  WAV temporal escrit a mesura; s'esborra en qualsevol interrupció (G1)
   ├─ peaks.py      pics per columna i canal, memòria circular segura entre fils (pur, NumPy)
   ├─ silence.py    detecció d'inici, aturada per silenci i retall (pur, NumPy)
   └─ types.py      Device, RecordingResult, errors
   │
   ▼
passimaker.ffmpeg.convert_to_mp3  (C04, ja fet)  →  model: AddSongs
```

- **Peces compartides amb YouTube:** el menú [+ Música ▾], `convert_to_mp3` i `safe_target_path` (avui a `passimaker.youtube.files`; es proposa moure'l a un lloc comú, p. ex.
  `passimaker.common.files`, al C07: és un canvi de contracte).
- **Res de xarxa:** la prova estàtica d'imports de xarxa (C01) ja impedeix que `recorder` en faci.
- **Proves:** un `FakeCaptureBackend` a `tests/fakes` que lliura blocs de tons i silencis; la lògica (silenci, retall,
  WAV, durada màxima, disc ple, desconnexió) es prova a Linux i a la CI. La captura real necessita una targeta de so:
  els servidors de la CI de GitHub no en tenen, així que porta una marca nova, `so`, exclosa per defecte, i la fa
  l'usuari al seu PC.

### 3.1 Tecnologia de captura (es decideix al C08)

| Opció | Com | Pros | Contres |
|---|---|---|---|
| **A. sounddevice** (ja és una dependència) | PortAudio amb WASAPI: les versions recents de PortAudio mostren cada sortida també com a entrada "[Loopback]" | Cap dependència nova; ja empaquetat i provat al ZIP | A confirmar que la versió de PortAudio que porta sounddevice 0.5.x té el loopback activat (l'API de Python no en diu res) |
| B. `soundcard` (BSD-3, cffi) | `get_microphone(id=altaveu, include_loopback=True)` | Loopback documentat i senzill | Dependència nova; menys mantinguda; cal provar-la a PyInstaller |
| C. `PyAudioWPatch` (MIT) | Fork de PyAudio amb loopback WASAPI | Pensat exactament per a això | Dependència nova amb binaris propis; duplica PortAudio |

Recomanació: provar **A** primer; si no funciona, **B**. Qualsevol dependència nova es proposa abans (regla 10).

### 3.2 Contracte proposat (CONTRACTES §16, nou)

| Operació | Rep | Retorna |
|---|---|---|
| `list_sources(include_inputs)` | — | `tuple[AudioSource, ...]` (la per defecte, primera) |
| `Recorder(source, temp_dir, settings, backend=…)` | — | objecte de gravació |
| `Recorder.start()` / `stop()` / `discard()` | — | `stop()` → `RecordingResult(wav_path, duration_s, trimmed_start_s, trimmed_end_s, stop_reason)`; una interrupció no retorna resultat: esborra el fitxer i llança l'error (G1) |
| `Recorder.level_dbfs` / `elapsed_s` / `state` | — | propietats de lectura, segures des d'un altre fil |
| `Recorder.peaks_since(n)` | índex de la darrera columna rebuda | `(columnes noves, nou índex)`: matriu `float32` (columnes, canals, 2) amb mínim i màxim; segura des d'un altre fil (§2.4) |
| `Recorder.overview(amplada)` | píxels | pics de tota la gravació reduïts a `amplada` columnes |
| `Monitor(source, backend=…)` | — | ones i nivell **sense gravar** (no escriu res al disc): `start()`, `stop()`, `peaks_since`, `level_dbfs` |
| `trim_silence(wav, llindar, marge)` | — | `(inici_s, final_s)` (pur) |

`AudioSource`: `id`, `name`, `kind` (OUTPUT_LOOPBACK, INPUT), `is_default`, `sample_rate`, `channels`.
`StopReason` (gravacions desades): USER, SILENCE, MAX_DURATION (si es confirma, "Per decidir" 2). Interrupcions (no es
desen, G1), com a errors que hereten de `PassiMakerError`: `RecorderDeviceLostError`, `RecorderDiskFullError`,
`RecorderDeviceError`; i `RecorderNoDeviceError` (no es pot començar).

---

## 4. Blocs (continuen la numeració del pla vigent)

| Bloc | Nom | Mòduls | Mida | Depèn de | En paral·lel amb | Model | On |
|---|---|---|---|---|---|---|---|
| C07 | Decisió 0013, contracte i especificació | documentació, esquelet de `recorder` | Petit | aprovació d'aquesta ampliació | C03, C05 (pla vigent) | Sonnet | Núvol |
| C08 | Prova de viabilitat de la captura a Windows | script de prova, paquet | Petit | C07 | C03, C05, C09 (la part de silenci i WAV) | Opus | Núvol + **local** |
| C09 | Nucli `passimaker.recorder` | `recorder` (nou) | Mitjà | C07, C08 | C05 | Opus | Núvol |
| C10 | Finestra "Grava el que sona" | `ui` | Gran (ones) | C09 i **C05** (comparteixen el menú [+ Música ▾]) | — | Sonnet | Núvol |
| C11 | Empaquetat, guia i versió | paquet, `ui/help.py`, documentació | Petit | C10 (i C06 si es publica alhora, "Per decidir" 1) | — | Sonnet | Núvol + **local** |

```
pla vigent:  C03 ──▶ C05 ──▶ C06
                       │
ampliació:   C07 ──▶ C08 ──▶ C09 ──▶ C10 ──▶ C11
```

### 4.1 Seguiment: estimació (format del §4.1 del pla vigent)

| Bloc | Depèn de | En paral·lel amb | Sessions estimades (opt. / prob. / pes.) | Temps teu estimat (h) | Estat |
|---|---|---|---|---|---|
| C07 Decisió i contracte | aprovació | C03, C05 | 1 / 1 / 1 | 0,5 | 📝 proposta |
| C08 Prova de viabilitat | C07 | C03, C05 | 1 / 1 / 2 | 1,0 | 📝 proposta |
| C09 Nucli `recorder` | C07, C08 | C05 | 1 / 2 / 2 | 0,5 | 📝 proposta |
| C10 Finestra de gravació | C09, C05 | — | 1 / 2 / 2 | 1,0 | 📝 proposta |
| C11 Empaquetat i versió | C10 (i C06) | — | 1 / 1 / 1 | 0,75 | 📝 proposta |
| **Subtotal** | | | **5 / 7 / 9** | **3,75** | |
| Correccions després de la prova de l'usuari | C11 | — | 0 / 1 / 2 | inclòs a sota | |
| Revisió de les PR i prova final | — | — | — | 1 / 2 / 4 | |
| **Total de l'ampliació** | | | **5 / 8 / 11 sessions** | **5 / 6 / 8 h** | |

Amb el pla vigent (8 sessions probables, 3 de fetes fins ara a `main` més el C03 en curs), el conjunt queda en
**16 sessions probables**. Fent el C07–C09 en paral·lel amb el C03–C05, el calendari s'allarga només unes **4
sessions** (C10, que pot necessitar-ne 2, C11 i correccions).

### Fitxes

**C07 · Decisió, contracte i especificació.** Decisió 0013 (gravació del so del sistema, sense xarxa, aspectes legals,
sense avís (G2), gravacions interrompudes no desades (G1), ones (G3), tecnologia a decidir al C08); ESPECIFICACIO (apartat nou, el §2 d'aquest document);
CONTRACTES §16 i el trasllat de `safe_target_path`; valors a `defaults.py`; esquelet de `src/passimaker/recorder/`;
marca `so` a `pyproject.toml`; prova d'arquitectura (sense Qt ni xarxa). Cap dependència nova.

**C08 · Prova de viabilitat (spike).** Un `ProvaGravacio.exe` (com el `ProvaYoutube` del C02) que llista les sortides,
grava 20 s de la sortida per defecte i escriu un informe. Comprova: (1) si sounddevice veu les sortides "[Loopback]" i
grava (si no, `soundcard`); (2) Spotify d'escriptori, YouTube a Chrome/Edge i el Reproductor multimèdia de Windows;
(3) auriculars Bluetooth i canvi de sortida a mitges; (4) si el volum de Windows i el de cada aplicació afecten la
gravació; (5) que no demana permís de micròfon ni l'avisa l'antivirus; (6) latència i blocs perduts en 10 min.
L'usuari l'executa al seu PC (un pas cada vegada). Acceptació: informe a `docs/sessions/C08.md` amb la recomanació.

**C09 · Nucli `passimaker.recorder`.** Captura en un fil, WAV temporal escrit a mesura, pics per a les ones
(memòria circular, vista de tota la gravació), mesurador, "comença quan soni", aturada per silenci, retall, durada
màxima; disc ple, desconnexió i errors **esborren el fitxer** (G1); neteja de restes en arrencar; descartar. Proves amb el
substitut (Hypothesis per al retall i el silenci), prova de no-xarxa, i proves `so` per al PC de l'usuari.

**C10 · Finestra "Grava el que sona".** Origen, **ones per canal** (`ui/wave_view.py`, en directe i de tota la
gravació) i mesurador, temps, [● Grava] [■ Atura] [Descarta], opcions, sense avís (G2), selector de carpeta i nom, conversió amb progrés, "Afegeix
al projecte". En tancar la finestra o el programa mentre es grava, pregunta i esborra (G1). pytest-qt amb el substitut.

**C11 · Empaquetat, guia i versió.** ZIP (i dependència nova si el C08 la tria), apartat a la guia (com gravar, consells,
sense apartat legal, G2) i a "Imprevistos" ("No s'ha gravat cap so"), CHANGELOG, versió. Prova de l'usuari: gravar una cançó de
Spotify i una de YouTube, afegir-les a un passi i exportar.

---

## 5. Riscos

| Risc | Probabilitat | Impacte | Mitigació |
|---|---|---|---|
| sounddevice no exposa el loopback | Mitjana | Cal una dependència nova | C08 prova A i B; B és petita i amb llicència permissiva |
| Es graven també avisos i altres sons | Alta | Gravació bruta | Consell a la finestra; mesurador abans de gravar; retall de silencis |
| Una aplicació fa servir el mode exclusiu o protegeix l'àudio | Baixa | Gravació en silenci | Avís "No s'ha gravat cap so" amb l'explicació |
| Canvi de sortida a mitges (Bluetooth) | Mitjana | Es perd la gravació sencera (G1) | Avís clar (§2.3); consell a la guia: no canviar d'auriculars mentre es grava |
| Qualitat: la música ja ve comprimida (Spotify ~160–320 kbps, YouTube ~130 kbps) i es torna a comprimir en MP3 | Segura | Pèrdua petita, inaudible en un passi | MP3 192 kbps; opció de desar en WAV si es vol ("Per decidir" 4) |
| Aspectes legals (condicions de Spotify, drets d'autor) | Mitjana | Reclamació si el vídeo es publica | Cap dins del programa (G2); responsabilitat de l'usuari (§1.1) |
| Les ones alenteixen la interfície | Baixa | Finestra poc fluida | Pics calculats al fil de captura; repintat de només les columnes noves; prova de rendiment al C10 |

---

## 6. Com s'incorporarà al pla vigent (quan ho diguis)

1. `docs/PLA_YOUTUBE.md`: el títol passa a "Música de YouTube i gravació"; s'hi afegeixen els blocs C07–C11 a la taula
   del §4 i a la de seguiment del §4.1 (amb les columnes de consum), el diagrama de tandes i els riscos; o bé es deixa
   aquest document com a annex enllaçat des del §4.
2. Decisió 0013 (al C07, no abans).
3. CLAUDE.md, apartat Estat: una línia.

---

## Per decidir

1. **Versió:** (a) publicar YouTube i gravació junts a la 1.2.0 (un sol C06+C11; el YouTube surt més tard);
   (b) YouTube a la 1.2.0 i la gravació a la 1.3.0 (recomanat: no endarrereix el que ja està a mig fer).
2. **Durada màxima (30 min):** (a) compta com a acabada i es desa (recomanat: s'atura neta i l'usuari sap el límit);
   (b) compta com a interrompuda i s'esborra.
3. **Orígens:** (a) només el so de l'ordinador (loopback); (b) també el micròfon i l'entrada de línia (gairebé el
   mateix codi; útil per gravar una veu o un tocadiscos; recomanat).
4. **Format final:** (a) MP3 192 kbps, com YouTube (recomanat); (b) a triar entre MP3 i WAV (sense pèrdua, 10 vegades
   més gran).
5. **Ordre de treball:** (a) començar el C07 i el C08 ara, en paral·lel amb el C03–C05 (recomanat);
   (b) esperar que el YouTube estigui acabat.
6. **Incorporar aquesta ampliació al pla vigent:** (a) ara; (b) més endavant, quan ho diguis.

**Pendent de la teva part:** respondre els punts anteriors.
