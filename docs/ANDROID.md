# PassiMaker per a Android: estudi estratègic i pla de desenvolupament

> Versió: 0.1 · Data: 25/10/2026 · Estat: **proposta, pendent de decisió** (no s'ha escrit cap línia de codi)
> Punt de partida: PassiMaker 1.0 per a Windows (`main`, tots els blocs B0–B16 integrats).
> Les decisions que cal prendre són al final (§8).

## 0. Resum

- **Objectiu:** una app Android que faci el mateix que l'escriptori, amb el mateix camí de tres passos
  (**Fotos → Música → Exportar**), i que exporti a MP4 Full HD a 30 fps, horitzontal o vertical, fora de línia.
- **Dues alternatives estudiades:**
  - **A. App nativa (Kotlin + Jetpack Compose + OpenGL ES + Media3).** Es reescriu tot en Kotlin; la lògica
    determinista (línia de temps, sorteig de moviments, format `.pmk`) es porta fil per fil i es verifica amb
    dades de referència generades pel codi Python actual.
  - **B. App híbrida (interfície Kotlin + nucli Python amb Chaquopy).** Es reaprofita el nucli Python dins
    l'app; Kotlin fa la interfície, la descodificació, la previsualització i la codificació.
- **Conclusió principal:** l'esforç de desenvolupament és **pràcticament el mateix** en les dues (≈ 29 sessions
  en l'escenari probable, com la v1.0). La part que B reaprofita (model, línia de temps, moviments, `.pmk`:
  unes 2.800 línies) és la més barata de fer; la cara (interfície, previsualització, descodificació i
  codificació de vídeo) s'ha de refer igualment en Kotlin a totes dues.
- **Recomanació: alternativa A.** Exporta unes 3–6 vegades més de pressa, gasta molta menys bateria i memòria,
  l'APK fa 5 vegades menys i evita una pila (Python a Android) poc habitual. El preu és mantenir dues còpies de
  la lògica; el risc que divergeixin es controla amb les dades de referència compartides (§3.4).
- **Temps estimat (A):** 20 / **29** / 43 sessions (optimista / probable / pessimista) i 18 / **26** / 40 h teves.
  Al ritme suposat al pla de la v1.0 són **8–9 setmanes**; al ritme real que va tenir la v1.0, **2–3 setmanes**.

---

## 1. Punt de partida: què hi ha i què es pot aprofitar

| Mòdul (src/passimaker) | Línies | A (nativa) | B (híbrida) |
|---|---|---|---|
| `model` (dades, controlador, valors per defecte) | 1.082 | Es porta a Kotlin | Es reaprofita |
| `timeline` | 414 | Es porta | Es reaprofita |
| `motion` (sorteig i encaix sense vores) | 807 | Es porta (exacte, §3.4) | Es reaprofita |
| `projectio` (`.pmk`, recuperació) | 476 | Es porta | Es reaprofita (adaptat a URI) |
| `render` (compositor CPU) | 476 | Es refà a la GPU | Es reaprofita només per exportar |
| `audio` (mescla, foses, LUFS) | 641 | Es porta | Es reaprofita la mescla; la descodificació, en Kotlin |
| `images`, `importer`, `thumbs` | 1.782 | Es refà (APIs d'Android) | Es refà en bona part (Photo Picker, HEIC natiu) |
| `ffmpeg` | 1.026 | No cal (codificador del mòbil) | No es pot fer servir (§3.3) |
| `export` | 586 | Es refà (Media3 / MediaCodec) | Es refà en bona part |
| `preview` | 1.086 | Es refà (OpenGL ES) | Es refà (OpenGL ES) |
| `ui` | 5.757 | Es refà (Compose) | Es refà (Compose) |
| **Total** | **14.828** | 0 % de codi, 100 % del disseny | ~25 % del codi |

El que es reaprofita **sempre**, en totes dues: l'especificació (docs/ESPECIFICACIO.md), els contractes, els valors
per defecte, les decisions 0004–0010, les dades de prova i les mesures. És la meitat de la feina de la v1.0.

---

## 2. Abast de la versió Android

**Igual que a l'escriptori:** importar fotos (JPG, PNG, HEIC, WebP), ordre per data o nom, durada per foto,
fosa encadenada, moviment Ken Burns automàtic i manual amb les mateixes regles d'equilibri, encaix
automàtic/omplir/fons difuminat/fons negre, gir, música amb retall, foses i anivellament, previsualització amb so,
exportació a MP4 Full HD 30 fps, desfer, desar i obrir projectes.

**Adaptat al mòbil:**

| Tema | A l'escriptori | A Android |
|---|---|---|
| Triar fotos | Arrossegar carpetes, diàleg de fitxers | Selector de fotos del sistema (Photo Picker), àlbums sencers, i "Comparteix amb PassiMaker" des de la galeria |
| Storyboard | Graella, arrossegar amb el ratolí, Ctrl/Maj | Graella tàctil: tocar = seleccionar, mantenir premut i arrossegar = reordenar, selecció múltiple |
| Propietats | Panell lateral | Full inferior (bottom sheet) amb "Avançat" plegat |
| Exportar | Diàleg de progrés | Servei en primer pla amb notificació de progrés; es pot sortir de l'app. Vídeo a `Movies/PassiMaker` i botó [Comparteix] |
| Fotos que desapareixen | Reenllaçar per ruta | Permís persistent de l'URI; si es perd, "Cercar…" amb el selector |
| Volum | 1.000 fotos de 50 MP | 1.000 admeses; objectiu de fluïdesa: 300 fotos en un mòbil de gamma mitjana |
| Mòbil mínim | — | Android 10 (API 29), 4 GB de RAM, 2020 o posterior (HEIC natiu i codificador H.264 per maquinari) |
| Distribució | ZIP portable | APK signat a GitHub (instal·lació manual, cost 0). Google Play, opcional (25 USD, un sol cop) |

**Fora de l'abast inicial:** tauletes amb disseny propi, 4K, edició sincronitzada entre el PC i el mòbil,
iOS. Obrir al mòbil un `.pmk` fet al PC (i al revés) **sí** que hi entra si es tria (D-A4), amb reenllaç de fotos.

---

## 3. Estudi estratègic

### 3.1 Alternativa A: app nativa

**Pila:** Kotlin · Jetpack Compose · OpenGL ES 3.0 (compositor amb shaders) · Media3 Transformer o
MediaCodec + MediaMuxer (H.264 i AAC per maquinari) · MediaExtractor/MediaCodec (descodificar la música) ·
AudioTrack (so de la previsualització) · ImageDecoder i ExifInterface (fotos, HEIC inclòs) · Gradle ·
proves JUnit 5, Robolectric i proves instrumentades a l'emulador de la CI.

**Com es manté el que ja funciona:**
- Un sol compositor (regla 3) a la GPU, per a previsualització i exportació.
- El sorteig dels moviments es porta exactament (el `random.Random` de Python és un Mersenne Twister amb una
  llavor que surt d'un SHA-256; tots dos es poden reproduir a Kotlin bit a bit).
- Dades de referència compartides (§3.4).

**Avantatges:** exportació ràpida (GPU i codificador de maquinari), poca bateria, poca memòria, APK petit
(15–25 MB), interfície nativa i fluida, eines estàndard que Claude Code coneix bé, sense FFmpeg ni llicència GPL.
**Inconvenients:** dues còpies de la lògica de negoci (Python i Kotlin); el vídeo no és idèntic bit a bit al del PC
(un altre codificador), només visualment equivalent; el comportament dels codificadors varia entre fabricants.

### 3.2 Alternativa B: app híbrida amb el nucli Python

**Pila:** Kotlin + Compose per a la interfície · Chaquopy (Python 3.12 dins l'app; llicència MIT) amb NumPy,
OpenCV i Pillow · el nucli `model`, `timeline`, `motion`, `projectio`, `audio` i `render` de PassiMaker ·
OpenGL ES per a la previsualització · MediaCodec per codificar els fotogrames que genera Python.

**Avantatges:** una sola implementació de la lògica i el sorteig; qualsevol canvi de l'especificació es fa una
vegada; les proves de pytest actuals continuen valent per al nucli.
**Inconvenients:**
- **No es pot fer servir FFmpeg com a l'escriptori.** Android no permet executar binaris arbitraris de manera
  fiable i la biblioteca habitual (ffmpeg-kit) està abandonada des del 2025. Cal codificar amb MediaCodec, és a
  dir, refer `ffmpeg` i `export` en Kotlin.
- **El compositor de NumPy no arriba a temps real al mòbil** (≤ 15 ms a 960×540 en un i7; en un mòbil de gamma
  mitjana i escalfat, 40–60 ms). La previsualització s'ha de fer a la GPU: **dos compositors**, cosa que trenca
  la regla 3 i obliga a comparar-los amb proves.
- Exportar passa cada fotograma de Python a Kotlin (6 MB × 30 per segon): lent i amb molta CPU.
- APK de 80–120 MB, inici de l'app més lent (1–3 s per carregar Python) i més memòria (risc que el sistema mati
  l'app en mòbils de 4 GB amb 1.000 fotos).
- Pila poc habitual: menys documentació i menys fiabilitat de Claude Code amb Chaquopy i Gradle; les versions de
  NumPy i OpenCV disponibles depenen del que publiqui Chaquopy.

### 3.3 Comparació

| Criteri | A. Nativa | B. Híbrida | Millor |
|---|---|---|---|
| Sessions (probable) | 29 | 28 | Empat |
| Codi reaprofitat | 0 % (sí el disseny i les dades de prova) | ~25 % | B |
| Exportar 10 min de vídeo (mòbil de gamma mitjana, estimació) | 3–6 min (0,3–0,6 × la durada) | 20–40 min (2–4 ×) | **A** |
| Bateria per a aquesta exportació (estimació) | 3–6 % | 15–30 % | **A** |
| Memòria màxima (estimació) | 300–500 MB | 700 MB – 1,2 GB | **A** |
| Previsualització fluida | Sí (GPU) | Sí, però amb un segon compositor | A |
| Mida de l'APK | 15–25 MB | 80–120 MB | A |
| Un sol lloc per a la lògica | No (dues còpies, controlades) | Sí | B |
| Fiabilitat de Claude Code amb la pila | Alta | Mitjana | A |
| Risc tècnic principal | Diferències entre codificadors de fabricants | Rendiment i memòria; pila poc habitual | A |
| Manteniment a llarg termini | Cada canvi de lògica, dues vegades (+20–30 % per canvi) | Una vegada, però dues piles d'eines | Empat |

Les xifres de rendiment i bateria són estimacions a partir de les mesures del PC (docs/RENDIMENT.md) i de la
diferència habitual entre CPU i maquinari dedicat; es mesuraran a la fita FA1.

**Alternatives descartades:** PySide6 per a Android (experimental i sense suport de la interfície actual en
pantalles tàctils), Kivy o BeeWare (interfície poc nativa i els mateixos problemes de rendiment que B), Flutter
(un tercer llenguatge sense cap avantatge sobre A per al vídeo), app web o PWA (exportar MP4 fora de línia al
navegador del mòbil és lent i limitat).

### 3.4 Com evitar que les dues versions divergeixin (alternativa A)

1. Una eina nova a `tests/fixtures` genera, amb el codi Python, **casos de referència en JSON**: per a centenars
   de projectes sintètics, la línia de temps, els moviments sortejats i les finestres resultants.
2. Les proves de Kotlin carreguen aquests JSON i exigeixen el mateix resultat (exacte per al sorteig;
   tolerància de 10⁻⁹ per a les finestres).
3. Imatges de referència: el compositor GPU es compara amb el de NumPy amb una tolerància (PSNR ≥ 40 dB).
4. Una regla nova al CLAUDE.md: qualsevol canvi de `model`, `timeline` o `motion` a Python regenera els JSON, i
   la CI d'Android falla fins que Kotlin coincideix.

### 3.5 Recomanació

**Alternativa A.** El que diferencia una app de passis al mòbil és exportar ràpid sense buidar la bateria, i és
exactament on B falla. L'estalvi de B és petit perquè el nucli que reaprofita és la part barata. A més, B
acabaria tenint més de la meitat del codi en Kotlin i dues piles d'eines.
**Quan convindria B:** si es preveu canviar sovint les regles de moviment i durades i no importa que exportar
trigui 2–4 vegades la durada del vídeo.

---

## 4. Pla de desenvolupament (alternativa A)

Mateix mètode que la v1.0: un bloc per sessió, contractes primer, proves alhora que el codi, PR per bloc i
nota a `docs/sessions/ANN.md`. Codi en una carpeta nova `android/` del mateix repositori (D-A3).

### 4.1 Blocs

| Bloc | Contingut | Criteris d'acceptació principals | Depèn de |
|---|---|---|---|
| A0 Fonaments | Projecte Gradle, Compose, CI d'Android a GitHub Actions (Linux, amb emulador), contractes en Kotlin, eina de casos JSON (§3.4) | La CI compila i passa una prova; l'APK de prova s'instal·la a l'emulador | — |
| A1 Model i `.pmk` | Dades immutables, controlador amb desfer, valors per defecte, desar/obrir `.pmk` compatible amb el PC | Un `.pmk` del PC s'obre i es desa igual; desfer/refer | A0 |
| A2 Línia de temps | Port de `timeline` | Coincideix amb els JSON de referència | A1 |
| A3 Moviments i encaix | Port exacte del sorteig i de la garantia sense vores | Coincideix bit a bit amb els JSON; propietats sense vores | A2 |
| A4 Importació | Photo Picker, permisos d'URI, EXIF, HEIC, perfils de color, ordre, duplicats | Mateixos casos límit que §1.1 de l'especificació | A1 |
| A5 Miniatures | Memòria cau a disc (límit 500 MB), miniatures del sistema quan n'hi ha | 300 miniatures en < 10 s a l'emulador | A4 |
| A6 Compositor GPU | Shaders de Ken Burns, fosa, fons difuminat, fons negre; textures intermèdies | PSNR ≥ 40 dB contra les imatges del compositor Python | A3, A5 |
| A7 Àudio | Descodificar (MP3, M4A, FLAC, OGG, WAV), mescla, foses, retall, LUFS | Coincideix amb la mescla Python (tolerància) | A2 |
| A8 Exportació (**FA1**) | Media3/MediaCodec, servei en primer pla, cancel·lar, notificació, `Movies/PassiMaker` | MP4 vàlid de 1080p30 amb so; durada exacta; prova al teu mòbil | A6, A7 |
| A9 Interfície I | Pantalla inicial, storyboard tàctil, selecció, reordenar, eliminar, duplicar | Proves de Compose; 1.000 miniatures sense salts | A5 |
| A10 Interfície II (**FA2**) | Música, propietats de foto i cançó, format, desar/obrir, exportar | El camí de tres passos en < 5 min | A8, A9 |
| A11 Previsualització | GPU + AudioTrack sincronitzats, saltar a una foto | 30 fps estables a 960×540; so continu | A6, A7, A9 |
| A12 Robustesa i rendiment (**FA3**) | Mort del procés, poca memòria, fotos esborrades, recuperació, 1.000 fotos | Mesures a docs/RENDIMENT.md al teu mòbil | A10, A11 |
| A13 Poliment i distribució (**FA4 = v1.0 Android**) | Icona, textos, guia, signatura, APK al flux `publicar.yml` | APK publicat i instal·lat al teu mòbil | A12 |

### 4.2 Fites (proves que fas tu)

| Fita | Què proves | Temps teu |
|---|---|---|
| FA1 (després d'A8) | Instal·lar l'APK de prova, exportar un passi de 30 fotos i mirar-lo. Mesurar temps i bateria | 1 h |
| FA2 (després d'A10) | Fer un passi sencer des del mòbil amb fotos i música teves | 1 h |
| FA3 (després d'A12) | Projecte gran (300 i 1.000 fotos) al teu mòbil | 1 h |
| FA4 (després d'A13) | Versió final; obrir un `.pmk` del PC | 1 h |

---

## 5. Estimació de temps

### 5.1 Per bloc (alternativa A)

| Bloc | Sessions (opt. / prob. / pes.) | Model | Temps teu (h) |
|---|---|---|---|
| A0 Fonaments | 1 / 2 / 2 | Opus | 1,5 |
| A1 Model i `.pmk` | 1 / 1 / 2 | Sonnet | 0,5 |
| A2 Línia de temps | 1 / 1 / 1 | Sonnet | 0,25 |
| A3 Moviments i encaix | 1 / 2 / 2 | Opus | 0,5 |
| A4 Importació | 1 / 2 / 3 | Sonnet | 1,0 |
| A5 Miniatures | 1 / 1 / 2 | Sonnet | 0,25 |
| A6 Compositor GPU | 2 / 3 / 4 | Opus | 1,0 |
| A7 Àudio | 1 / 2 / 3 | opusplan | 0,5 |
| A8 Exportació (FA1) | 2 / 2 / 3 | Opus | 2,0 |
| A9 Interfície I | 2 / 2 / 3 | Sonnet | 1,5 |
| A10 Interfície II (FA2) | 1 / 2 / 3 | Sonnet | 2,0 |
| A11 Previsualització | 2 / 2 / 3 | Opus | 1,0 |
| A12 Robustesa (FA3) | 1 / 2 / 3 | Opus | 2,0 |
| A13 Poliment (FA4) | 1 / 1 / 2 | Sonnet | 1,5 |
| **Subtotal dels blocs** | **18 / 25 / 36** | | **~15** |
| Correccions després de les proves al mòbil | 2 / 4 / 7 | Sonnet | inclòs a sota |
| Preparació (Android SDK, mòbil en mode desenvolupador), revisions i fites | — | — | 3 / 11 / 25 |
| **Total A** | **20 / 29 / 43 sessions** | | **18 / 26 / 40 h** |

**Alternativa B, per comparar:** fonaments amb Chaquopy 2/3/4, pont Kotlin↔Python 1/2/3, importació 1/2/3,
miniatures 1/1/2, adaptació del compositor 0/1/1, previsualització GPU 2/3/4, àudio 1/1/2, exportació per
MediaCodec 2/3/4, interfície I 2/2/3, interfície II 1/2/3, robustesa i rendiment 2/3/4, poliment 1/1/2, correccions
2/4/7. **Total B: 18 / 28 / 42 sessions** i unes 17 / 26 / 40 h teves.

### 5.2 Calendari (alternativa A, escenari probable)

| Ritme | Sessions/setmana | Durada | Data aproximada (si es comença el 2/11/2026) |
|---|---|---|---|
| El suposat al pla de la v1.0 (4 h/setmana) | 3,5 | 8–9 setmanes | Començament de gener del 2027 |
| **El real de la v1.0** (B0–B16 i M01–M04 en 5 dies, 20–24/10/2026) | ~5 al dia | **2–3 setmanes** (limitat per les teves proves al mòbil) | Mitjan o final de novembre del 2026 |

| Setmana (ritme del pla) | Feina | Fita |
|---|---|---|
| S1 | Preparació, A0 | Contractes en Kotlin aprovats |
| S2 | A1, A2, A3 | |
| S3 | A4, A5, A7 | |
| S4 | A6 | |
| S5 | A8 | **FA1: primer vídeo al mòbil** |
| S6 | A9, A10 | **FA2: passi sencer al mòbil** |
| S7 | A11 | |
| S8 | A12 | FA3 |
| S9 | A13 i correccions | **FA4: v1.0 Android** |

### 5.3 Suposicions

1. Una sessió és una finestra d'ús de 5 h dedicada a un bloc (com a la v1.0).
2. El ritme real de la v1.0 va ser molt més ràpid que el previst (29 sessions previstes en 9–10 setmanes;
   fetes en 5 dies). No es pot garantir que es repeteixi: Gradle és més lent que `uv`, la CI d'Android triga
   més i les proves al mòbil depenen de tu.
3. L'escenari pessimista inclou problemes amb el codificador d'algun fabricant (risc RA1) i una segona volta del
   compositor GPU.

---

## 6. Consum

### 6.1 Consum de desenvolupament

| Recurs | Alternativa A (probable) | Alternativa B (probable) | Comentari |
|---|---|---|---|
| Sessions de Claude Code | 29 (≈ 1,0 × la v1.0) | 28 | El consum real de quota depèn del pla; Anthropic no en publica xifres exactes |
| D'aquestes, amb Opus o opusplan | 15 (≈ 50 %) | 15 | Un bloc d'Opus pot gastar el doble que un de Sonnet (suposició del PLA §6.3) |
| Consum relatiu de quota | ≈ 1,1–1,3 × el de la v1.0 | ≈ 1,2–1,4 × | Més context per sessió: Gradle, Kotlin i les dades de referència |
| Minuts de GitHub Actions | 30–40 PR × ~15 min ≈ **500–700 min/mes** (Linux) | ≈ 600–900 min/mes | La CI de Windows actual compta el doble; cal vigilar la quota gratuïta mensual del compte |
| Disc a la sessió del núvol | Android SDK + caché de Gradle: 3–5 GB | 4–6 GB | Pot arribar al límit de disc de la sessió (risc RA4) |
| Diners | 0 € (APK manual). 25 USD si es vol Google Play | Igual | No cal certificat; la clau de signatura és gratuïta |
| Temps teu | 26 h | 26 h | |

### 6.2 Consum al mòbil (objectius, a mesurar a FA1 i FA3)

| Mesura | Objectiu A | Estimació B |
|---|---|---|
| Exportar 10 min de vídeo 1080p30 | ≤ 0,6 × la durada | 2–4 × |
| Bateria per exportar 10 min de vídeo | ≤ 6 % | 15–30 % |
| Memòria màxima amb 1.000 fotos | ≤ 500 MB | 0,7–1,2 GB |
| Mida de l'APK | ≤ 25 MB | 80–120 MB |
| Memòria cau de miniatures | ≤ 500 MB (es pot buidar) | Igual |
| Mida del vídeo | ~10–12 Mbps: uns 80 MB per minut | Igual |
| Escalfament | Sense limitació tèrmica visible en 10 min | Probable limitació a partir de 3–5 min |

---

## 7. Riscos

| # | Risc | Prob. | Impacte | Mesura |
|---|---|---|---|---|
| RA1 | Codificadors de maquinari que es comporten diferent segons el fabricant | Mitjana | Alt | Media3 Transformer (absorbeix diferències), proves a l'emulador i al teu mòbil, codificació per programari com a pla B |
| RA2 | Les dues còpies de la lògica divergeixen (A) | Mitjana | Mitjà | Dades de referència JSON a la CI (§3.4) |
| RA3 | Xarxa de la sessió del núvol sense accés als repositoris de Google (Maven, SDK) | Mitjana | Alt | Comprovar-ho a l'A0 i, si cal, ampliar la política de xarxa de l'entorn |
| RA4 | Espai de disc de la sessió del núvol | Mitjana | Mitjà | Caché de Gradle mínima; netejar construccions |
| RA5 | Sense mòbil real a la CI: errors que només surten al teu mòbil | Alta | Mitjà | Fites curtes FA1–FA4; registre exportable des de l'app |
| RA6 | El sistema mata l'app durant l'exportació | Mitjana | Mitjà | Servei en primer pla, desat continu i recuperació (com al B15) |
| RA7 | Fotos al núvol (Google Fotos) no descarregades | Mitjana | Baix | El Photo Picker les descarrega; progrés i cancel·lació |
| RB1 | (Només B) Rendiment insuficient i memòria | Alta | Alt | Cap de bo: és la raó de recomanar A |

---

## 8. Per decidir

1. **Alternativa:** A, app nativa (recomanada) · B, híbrida amb el nucli Python · no fer la versió Android ara.
2. **Android mínim:** Android 10 (recomanat; HEIC natiu i cobreix ~95 % dels mòbils actuals) · Android 8 (més
   mòbils antics, sense HEIC natiu, +1 sessió).
3. **On va el codi:** carpeta `android/` d'aquest repositori (recomanat; la CI i les dades de referència són
   compartides) · un repositori nou.
4. **Compatibilitat de `.pmk` entre el PC i el mòbil:** sí, amb reenllaç de fotos (recomanat, inclòs a l'A1) · no,
   cada versió amb els seus projectes (−1 sessió).
5. **Distribució:** APK signat a GitHub, instal·lació manual (recomanat, cost 0) · també a Google Play (25 USD i
   1 sessió més).
6. **Quan començar:** després del manteniment v1.1 pendent (recomanat) · ara mateix, en paral·lel.

**Pendent de la teva part:**
- Dir quin mòbil faràs servir per a les proves (model i versió d'Android).
- Quan es decideixi començar: activar les opcions de desenvolupador i la depuració USB al mòbil (t'ho guiaré pas a pas).
