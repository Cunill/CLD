# Registre de canvis

Versions de PassiMaker. La CI genera el ZIP portable `PassiMaker-<versió>-win64` quan es posa l'etiqueta a `main`
(vegeu `docs/sessions/B12.md`).

## 1.3.0 · millores de l'usuari (blocs M07–M13)

> **Compatibilitat:** un `.pmk` desat amb la 1.3.0 **no s'obre amb la 1.2.0** (el format del fitxer és ara la
> versió 2). Els `.pmk` de la 1.2.0 (i anteriors) s'obren bé amb la 1.3.0, amb el mateix aspecte de sempre.

### Nou
- **Quadres negres a l'inici i al final** (M08): el storyboard té dues fitxes negres (2 s per defecte), fixes al
  principi i al final, amb durada pròpia. Es poden esborrar i tornar a posar des d'Edita (*Afegeix negre a l'inici* /
  *al final*). Els projectes antics s'obren sense negres.
- **Barreja les fotos** (M09): un botó (i Visualitza ▸ Barreja les fotos) que canvia l'ordre a l'atzar cada vegada;
  els negres no es mouen i es pot desfer.
- **Sis formats de vídeo** (M10): botó *Format* a la barra d'eines i llista al panell del projecte. Horitzontals
  16:9 (1920×1080), 3:2 (1620×1080) i 4:3 (1440×1080); verticals 9:16 (1080×1920), 2:3 (1080×1620) i 3:4
  (1080×1440). `passimaker-nou --format`.
- **Silenci abans i després de la música** (M13): a *Tota la música* del panell de la cançó, de 0 a 60 s cada un.
- **Marge de la previsualització ajustable** (M11): la línia de sota de la previsualització es veu i s'arrossega;
  el programa recorda la posició i el doble clic hi torna per defecte.
- Guia: apartats nous per a tot això.

### Canviat
- **Ajustar a la música** (M07, decisió 0014): les fotos amb la durada posada a mà no es toquen; la resta es reparteix
  el temps en **0,4–24 s** (abans 1–3 s). Si totes tenen durada a mà, avisa i no fa res. També compta el silenci
  d'abans i de després.
- Format del `.pmk`: versió 2 (negres, proporció i silencis).

### Intern
- yt-dlp 2026.10.26 (PR #89).

## 1.2.0 · música de YouTube i gravació del so (blocs C01–C10, C06)

Publicada com a `v1.2` el 29/10/2026 (https://github.com/Cunill/CLD/releases/tag/v1.2).

### Nou
- **Música de YouTube**: a **[+ Música ▾] → Des de YouTube…** es cerca una cançó pel nom o amb un enllaç, es baixa
  com a MP3 i s'afegeix al passi. És l'únic que necessita internet; abans de fer-la servir hi ha un avís (decisió 0012).
- **Gravar el so de l'ordinador**: **[+ Música ▾] → Grava el que sona…** grava el que sona per la sortida de so
  (Spotify, el navegador…) o per un micròfon, amb les ones de cada canal en directe, "Comença quan soni", aturada per
  silenci, màxim de 30 minuts i MP3 de 192 kbps normalitzat a −1 dBFS (decisió 0013). Sense avís legal.
- Guia: apartats "Música de YouTube" i "Gravar el que sona", i a "Imprevistos" els de "YouTube ha canviat" i
  "No s'ha gravat cap so". "Quant a" cita yt-dlp, Deno i soundcard.
- Un flux setmanal (`actualitzar-ytdlp.yml`) obre una PR quan surt una versió nova de yt-dlp.

### Canviat
- El botó [+ Música] és ara un menú ([+ Música ▾]) amb tres entrades.
- El ZIP porta Deno, `yt-dlp-ejs`, `yt-dlp` i `soundcard` (uns 45 MB més).

### Intern
- M06: la finestra de YouTube fa servir un sol objecte de senyals per finestra (evitava caigudes de PySide).

## 1.1.0 · manteniment M05 (millores de les proves de l'usuari)

### Canviat
- **Durada de cada foto: de 0,4 a 24 s** (abans, d'1 a 3 s). "Ajustar a la música" continua donant 1–3 s per foto.
- El botó de la foto **"🎲 Nou moviment a l'atzar"** (abans "Tornar a sortejar") **no es desactiva mai**: si la foto
  tenia el moviment triat a mà, torna a Automàtic amb un moviment nou. Un sol pas de desfer.
- Menú Edita: "Nou moviment a l'atzar" (abans "Sortejar un altre moviment").
- `passimaker-nou` refusa els fitxers de música sense so, com ja feia la finestra.

### Nou
- **Icona nova** (fotos amb perforacions de pel·lícula), també a la finestra i a la barra de tasques (PR #48).
- **Escoltar el tros**: una línia vermella sobre la forma d'ona mostra per on va la reproducció (segueix el rellotge
  del so, com la previsualització) i desapareix en aturar-se.
- Guia: apartat "Imprevistos".

### Intern
- `photo_from_candidate` (a `passimaker.importer`) i `song_from_file` (a `passimaker.audio`): una sola còpia per a la
  interfície i les ordres de línia.

## 1.0.0 · bloc B16 (poliment)

### Nou
- **Menú Ajuda**: "Guia d'ús" (F1), una guia d'una pàgina en català amb els tres passos (Fotos → Música →
  Exportar), els ajustos habituals, com desar i totes les dreceres de teclat; i "Quant a PassiMaker", amb la
  versió, els components que fa servir i on és el registre d'errors.
- **Fitxer ▸ Sortir** (Ctrl+Q).
- **Estat buit**: sota [Tria fotos…] s'expliquen els tres passos i on és la guia.
- **Consells emergents** als botons de la barra d'eines i als camps dels panells de projecte, foto i cançó.
- **Avís a la barra d'estat quan la previsualització no pot preparar la música** (per exemple, si falta FFmpeg):
  "⚠ La previsualització sona sense música: …". Desapareix quan la música torna a estar a punt.

### Canviat
- **Singulars**: "1 foto · 0:02", "No es troba 1 fitxer.", "1 fitxer no s'ha pogut afegir.", "1 cançó no s'ha
  pogut afegir.", "1 foto ja hi és. La vols afegir igualment?", "S'ha trobat 1 fitxer. Encara en falta 1.", etc.
  Abans deia "1 fotos" o "1 fitxers".
- Versió 1.0.0.

### Sense canvis
- Els valors per defecte són els de `docs/ESPECIFICACIO.md` §1.0: no n'hi ha cap de nou aprovat.

## 0.5.0 · MVP (blocs B0–B15, M01–M04)

Primera versió completa per a ús intern (etiqueta `v0.5-mvp`).

- **Fotos**: importar arrossegant fitxers o carpetes, amb [+ Fotos] o "Afegir una carpeta…"; JPG, PNG, HEIC i
  altres formats; orientació EXIF i perfils de color; ordre per data o per nom; importació progressiva i
  cancel·lable (es conserven les fotos ja llegides).
- **Storyboard**: graella de miniatures amb el número i la durada; seleccionar, reordenar arrossegant o amb
  Ctrl+←/→, eliminar, duplicar, girar 90°; tres mides de miniatura.
- **Moviment de càmera** (Ken Burns) sortejat amb regles d'equilibri i límits de velocitat; intensitat suau,
  mitjana o marcada; moviment fix per foto; encaix automàtic, omplir o fons difuminat/negre.
- **Foses** encadenades entre les fotos, des de negre al principi i cap a negre al final.
- **Música**: diverses cançons en ordre, retall amb forma d'ona i nanses, foses d'entrada i de sortida, volum per
  cançó i general, anivellament (−16 LUFS), [Escoltar el tros], [Ajustar a la música] i "Mantenir ajustat".
- **Previsualització** en temps real amb so, feta pel mateix compositor que l'exportació.
- **Exportar** a MP4 H.264 Full HD (horitzontal 1920×1080 o vertical 1080×1920, 30 fps) amb AAC 192 kbps,
  progrés, temps restant i cancel·lació.
- **Projectes** `.pmk`: desar, obrir, recents, rutes relatives i absolutes, cercar els fitxers que no es troben,
  còpia de recuperació cada 2 minuts (una per finestra), desfer i refer.
- **Robustesa**: registre d'errors a `%LOCALAPPDATA%\PassiMaker\logs` (5 fitxers de 5 MB), missatges en català
  per a les fallades, provat amb 1.000 fotos de 24 MP.
- **Línia d'ordres**: `passimaker-nou` i `passimaker-render`.
- **ZIP portable** per a Windows, sense instal·lació.
