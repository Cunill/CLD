# PassiMaker: contractes entre mòduls

> Font de veritat de les interfícies entre blocs. Desenvolupa el §2.3 de `docs/PLA.md`.
> El codi fa servir noms en anglès; aquí es dona la correspondència amb els noms del pla.
> Qualsevol canvi en aquest document s'ha de proposar i aprovar abans (vegeu CLAUDE.md).
> Les definicions en codi (tipus i signatures) són a `src/passimaker/**` i en són l'expressió exacta.

## 0. Convencions comunes (`passimaker.common`)

| Nom al codi | Significat |
|---|---|
| `RGBImage` | Imatge NumPy de forma (alçada, amplada, 3), `uint8`, sRGB |
| `AudioBlock` | Mostres NumPy de forma (fotogrames, 2), `float32` entre −1 i 1, 48 kHz estèreo |
| `ProgressCallback` | `progrés(fet, total)`; pot cridar-se des d'un fil de treball |
| `CancelToken` | Senyal de cancel·lació compartit (`cancel()`, `cancelled`) |
| `PassiMakerError(message_key, detail)` | Error base. `message_key` és la clau del missatge en català (`passimaker.i18n`) |

Unitats: temps en segons (`float`); a l'exportació, fotogrames enters a 30 fps. Finestres de moviment
normalitzades (0–1) respecte del llenç.

## 1. Model (`passimaker.model`) · blocs B1 (implementació) i tots (ús)

Totes les estructures són **immutables** (`frozen dataclass`, llistes com a `tuple`). Només el
controlador crea versions noves del projecte.

| Pla | Codi | Camps (codi) |
|---|---|---|
| Projecte | `Project` | `name`, `format_version`, `output_format`, `seed`, `default_duration_s`, `crossfade_s`, `fade_from_black_s`, `fade_to_black_s`, `motion_enabled`, `zoom_amount`, `pan_amount`, `slides: tuple[Photo \| BlackSlide]` (M08: la fitxa negra d'inici opcional, les fotos i la de final opcional), `music: Music` · derivats (no es passen en crear-lo): `photos: tuple[Photo]` (les fotos de `slides`), `black_start`, `black_end` (`BlackSlide` o `None`) · mètode `photo_duration(slide)` (la pròpia o la general) |
| Fitxa negra | `BlackSlide` (M08) | `position: BlackSlidePosition` (START, END), `duration_s` (per defecte `BLACK_SLIDE_DURATION_S`, rang `PHOTO_DURATION_RANGE`) · propietat `id`: `BLACK_START_ID` (`"black:start"`) o `BLACK_END_ID` (`"black:end"`) |
| Foto | `Photo` | `id`, `path`, `relative_path`, `width`, `height` (ja orientades i girades), `exif_orientation`, `capture_time`, `duration_s` (`None` = durada general), `fit: FitMode`, `motion: PhotoMotion`, `rotation: Rotation` (P2), `low_resolution` |
| MovimentFoto | `PhotoMotion` | `mode: MotionMode`, `type: MotionType`, `draw_count`, `start: Window`, `end: Window`, `resolved_fit: ResolvedFit` |
| Finestra | `Window` | `centre_x`, `centre_y` (0–1 sobre el llenç), `scale` (1 = la finestra més gran de la proporció del vídeo que hi cap; >1 = més a prop) |
| Música | `Music` | `master_volume` (0–1), `normalize`, `keep_fitted`, `silence_start_s` i `silence_end_s` (M13: segons de silenci abans de la primera cançó i després de la música fins al final del vídeo; per defecte `MUSIC_SILENCE_S` = 0, rang `MUSIC_SILENCE_RANGE` 0–60 s en passos de 0,5 s), `songs: tuple[Song]` |
| Cançó | `Song` | `id`, `path`, `relative_path`, `original_duration_s`, `trim_start_s`, `trim_end_s` (`None` = fins al final), `fade_in: Fade`, `fade_out: Fade`, `volume` (0–1,5), `loudness_gain_db` (calculat) |
| Fosa | `Fade` | `enabled`, `seconds` |

Enumeracions: `OutputFormat` (M10: tres proporcions, horitzontals i verticals, costat curt de 1080 px: HORIZONTAL
16:9 1920×1080, HORIZONTAL_3_2 1620×1080, HORIZONTAL_4_3 1440×1080, VERTICAL 9:16 1080×1920, VERTICAL_2_3 1080×1620,
VERTICAL_3_4 1080×1440; propietats `size` (amplada, alçada; parells), `is_vertical` i `label` ("16:9", "3:2"…)),
`Intensity` (SOFT, MEDIUM, STRONG; preseleccions de `zoom_amount` i `pan_amount`, vegeu `passimaker.motion.INTENSITY_PRESETS`), `FitMode` (AUTO, FILL, BLUR, BLACK), `ResolvedFit` (FILL, BLUR,
BLACK), `MotionMode` (AUTO, MANUAL), `MotionType` (ZOOM_IN, ZOOM_OUT, PAN_LEFT, PAN_RIGHT, PAN_UP,
PAN_DOWN, COMBINED, NONE), `Rotation` (R0, R90, R180, R270).

Valors per defecte i rangs: **només** a `passimaker.model.defaults` (per ajustar-los després de les fites).

`new_project(**camps)` (M08): un projecte nou amb les dues fitxes negres; el fan servir el programa en obrir-se i
`passimaker-nou`. `Project()` no en té (així són els `.pmk` antics). `Slide = Photo | BlackSlide`.

### Controlador (`ProjectController`)

| Operació | Rep | Retorna / efecte |
|---|---|---|
| `execute(ordre)` | una ordre de `passimaker.model.commands` | Aplica l'ordre, limita els valors als rangs, desa l'estat anterior per desfer, avisa els observadors. Retorna el conjunt de `Change`. |
| `undo()` / `redo()` | — | Restaura l'estat anterior / següent (P1). Retorna `Change`. |
| `subscribe(observador)` | funció `(changes) -> None` | Funció per donar-se de baixa |
| `replace_project(projecte)` | projecte obert o recuperat | Buida l'historial i la marca de canvis |
| `mark_saved()` | — | Esborra la marca de canvis sense desar |
| `project`, `has_unsaved_changes`, `can_undo`, `can_redo` | — | Propietats de lectura |

`Change`: PHOTOS, TIMING, MOTION, MUSIC, SETTINGS, SAVED_STATE.

Ordres (`passimaker.model.commands`): `AddPhotos`, `RemovePhotos`, `MovePhotos`, `DuplicatePhotos`,
`SortPhotos`, `ShufflePhotos` (M09), `SetDefaultDuration`, `SetPhotoDuration`, `SetPhotoFit`, `SetPhotoMotion`,
`RerollMotions`, `RotatePhotos`, `SetProjectSettings`, `AddSongs`, `RemoveSongs`, `MoveSongs`,
`UpdateSong`, `SetMusicSettings` (M13: també `silence_start_s` i `silence_end_s`; el controlador els limita al rang i, amb
"Mantenir ajustat", torna a ajustar), `FitToMusic`, `AddBlackSlide(position)` (M08). Són dades; la lògica és al controlador (B1). Les
ordres que afecten el moviment (afegir, duplicar, girar, canviar format o encaix, tornar a sortejar)
fan servir `passimaker.motion` per resoldre l'encaix i sortejar. `RerollMotions(ids)` torna a sortejar aquestes fotos
i, si tenien el moviment fixat a mà, les torna a automàtic (M05); `RerollMotions(None)`, només les automàtiques.
`ShufflePhotos()` (M09, sense camps) barreja les fotos amb `random.Random` de clau `"<seed>:<ids en l'ordre actual>"`: determinista
(mateix projecte, mateix resultat), un ordre diferent de l'actual a cada pas, sense camps nous al `.pmk`; amb menys de dues
fotos no fa res. Fitxes negres (M08): els índexs d'`AddPhotos` i `MovePhotos` compten només les fotos, i cap ordre de fotos no mou les
fitxes negres de l'inici i del final. `RemovePhotos` també treu les fitxes negres que hi hagi als identificadors i
`SetPhotoDuration` també els canvia la durada (`None`: `BLACK_SLIDE_DURATION_S`); la resta d'ordres de fotos les
ignoren. `AddBlackSlide` la torna a posar amb la durada per defecte (si ja hi és, no fa res). "Ajustar a la música"
no les toca i en resta la durada de la música.

## 2. Importació (`passimaker.importer`) · B4

| Operació | Rep | Retorna |
|---|---|---|
| `import_paths(rutes, existing, include_subfolders, progress, cancel)` | fitxers i carpetes | `ImportResult(candidates, failures, duplicates, subfolder_photo_count, cancelled)` |
| `sort_candidates(candidats, by_date)` | `by_date=None` aplica la regla automàtica del §1.1 | llista ordenada |
| `photo_from_candidate(candidat, id, format)` | un `PhotoCandidate` (M05) | `Photo` nova amb els valors per defecte (marca de baixa resolució del §1.1); la fan servir la interfície i les ordres de línia |

`PhotoCandidate`: `path`, `width`, `height` (orientades), `exif_orientation`, `capture_time`,
`file_time`, `color_profile`. `FailedFile(path, reason)` amb `ImportFailure` (UNSUPPORTED, RAW,
CORRUPT, TOO_SMALL, NOT_FOUND).

## 3. Imatges (`passimaker.images`) · B4

`ImageSource` (protocol):

| Operació | Rep | Retorna |
|---|---|---|
| `get_image(foto, min_long_side)` | foto, costat llarg mínim | `RGBImage` orientada (EXIF + gir manual), sRGB, costat llarg ≥ mínim (o la mida original si és més petita) i no més del doble, **de només lectura** (la comparteix la memòria cau: qui la vulgui modificar n'ha de fer una còpia). Error: `ImageDecodeError`. |
| `prefetch(fotos, min_long_side)` | — | Torna de seguida; descodifica en segon pla |

Implementació: `CachedImageSource(memory_budget_bytes=768 MB, workers=2)`.

## 4. Miniatures i intermedis (`passimaker.thumbs`) · B5

`ThumbnailService(cache_dir, image_source, disk_limit_bytes=2 GB)`:
`request_thumbnail(foto, Priority, callback)` (resposta `callback(photo_id, imatge|None)` des d'un fil),
`get_intermediate(foto) -> RGBImage` (1.600 px, bloquejant), `cancel_pending()`, `close()`.
Mides: `THUMBNAIL_SIZE = 256`, `INTERMEDIATE_SIZE = 1600`.

## 5. Línia de temps (`passimaker.timeline`) · B2

| Operació | Rep | Retorna |
|---|---|---|
| `compute_timeline(projecte, fps=30)` | projecte | `Timeline` |
| `query(línia, t)` | instant | `Visibles` |
| `fit_to_music(durades, objectiu_s, límits)` | — | `FitResult(durations, warning, achieved_total_s)` |
| `build_audio_plan(cançons, total_s, fps, silence_start_s=0, silence_end_s=0)` (M13) | — | `AudioPlan`: la música comença a `silence_start_s` i acaba com a molt a `total_s − silence_end_s` (la fosa final, si cal, acaba just allà); amb tots dos a 0, el pla d'abans |
| `time_to_frame(t, fps)` / `frame_to_time(n, fps)` | — | conversió |

`Timeline`: `fps`, `total_duration_s`, `total_frames`, `slots: tuple[PhotoSlot]`, `fade_from_black`,
`fade_to_black` (`Interval` o `None`), `audio_plan: AudioPlan`, `music_duration_s` (només les cançons, sense els silencis).
"Ajustar a la música" del model fa servir l'objectiu `model.editing.music_span(music)` = silenci abans + cançons +
silenci després (0 sense cançons) (M13); la barra d'estat compara el passi amb el mateix valor.
`PhotoSlot`: `photo_id`, `index`, `slot_start`, `slot_end` (espai propi, contigus), `visible_start`,
`visible_end`, `fade_in`, `fade_out`, `black` (M08: la franja d'una fitxa negra; `photo_id` és el seu `id`). Les fitxes
negres ocupen la seva franja com una foto, amb les foses encadenades i la regla de seguretat de sempre.
`AudioPlan`: `segments: tuple[AudioSegment]`, `final_fade`. `AudioSegment`: `song_id`,
`video_start`, `video_end`, `source_start`, `fade_in_s`, `fade_out_s`.
`Visibles`: `layers` (com a màxim 2, de baix a dalt) de `VisibleLayer(photo_id, opacity,
motion_progress, black)` i `black_level` (0–1).

## 6. Moviments i encaix (`passimaker.motion`) · B3

| Operació | Rep | Retorna |
|---|---|---|
| `resolve_fit(amplada, alçada, format, preferència)` | — | `FitDecision(fit, canvas_width, canvas_height)` |
| `draw_motions(peticions, llavor, quantitats, which)` | `MotionRequest` per foto | `dict[photo_id, PhotoMotion]` de **totes** les peticions |
| `rebuild_motions(peticions, llavor, quantitats)` | `MotionRequest` amb `current` | Recalcula les finestres mantenint el tipus (canvi de format, encaix, gir, durada o intensitat) |
| `window_at(moviment, progrés)` | progrés 0–1 | `Window` (sempre dins el llenç) |
| `window_rect(finestra, fit, format)` | — | `(esquerra, dalt, dreta, baix)` en píxels del llenç (per al compositor) |
| `base_window(amplada_llenç, alçada_llenç, format)` | — | mida normalitzada de la finestra d'escala 1 |
| `is_inside(finestra, base)` | — | la finestra és dins el llenç |

`MotionRequest`: `photo_id`, `width`, `height` (orientades i girades), `visible_duration_s`, `fit:
FitDecision`, `output_format`, `mode`, `manual_type`, `draw_count`, `current: PhotoMotion | None`.

`which`: `None` = primer sorteig de totes les fotos; un conjunt d'ids = tornar a sortejar aquestes
(el moviment nou és diferent de l'actual); les altres es mantenen i compten com a veïnes.
El controlador incrementa `draw_count` abans de tornar a sortejar.

Geometria: el centre de la finestra s'interpola linealment i l'escala geomètricament; si els
dos extrems són dins el llenç, tots els instants intermedis també ho són. `PAN_LEFT` vol dir que
la finestra (la càmera) es mou cap a l'esquerra.

`quantitats`: `MotionAmounts(zoom, pan)` amb els valors del projecte (`Project.zoom_amount`, `pan_amount`),
o bé una `Intensity` (preselecció).

Paràmetres (un sol lloc, `passimaker.motion.params`): `FILL_RATIO_RANGE`, `BASE_PROBABILITIES`,
`RULE_COMPENSATION`, `INTENSITY_PRESETS`, `FULL_MOTION_MIN_S`, `BLUR_INTENSITY_FACTOR`, `MAX_UPSCALE`, `NO_MOTION_BELOW`,
`FOCAL_POINT`, etc.

## 7. Compositor (`passimaker.render`) · B6

`Compositor(projecte, línia, image_source, intermediate=None)`:
`frame_at(t, amplada, alçada, sentinel=False) -> RGBImage`, `invalidate(photo_ids|None)`.
`SENTINEL_COLOR = (255, 0, 255)`: en mode sentinella, tot el que queda fora de la imatge es pinta
d'aquest color. Les dades de prova no contenen mai píxels semblants al magenta
(`tests/fixtures/generate.py`, `MAX_MAGENTA_EXCESS`).
Una capa `black` (fitxa negra, M08) es pinta negra, sense imatge, moviment ni encaix, i sense demanar res a
`image_source`; en una fosa encadenada, la foto es barreja amb negre. En mode sentinella no és "fora de la imatge".

## 8. Pont FFmpeg (`passimaker.ffmpeg`) · B7

| Operació | Retorna |
|---|---|
| `locate()` | `FfmpegPaths(ffmpeg, ffprobe)`. Ordre de cerca: variable `PASSIMAKER_FFMPEG`, carpeta del programa, `vendor/ffmpeg/bin`, `PATH`. |
| `probe(fitxer)` | `MediaInfo(duration_s, has_audio, sample_rate, channels, has_video, width, height)` |
| `decode_audio(fitxer, destí, inici, final)` | `PcmFile(path, frames)`: float32 estèreo 48 kHz |
| `measure_loudness(fitxer)` | `Loudness(integrated_lufs, true_peak_dbfs)` |
| `open_encoder(destí, amplada, alçada, wav, settings)` | `VideoWriter` amb `write(imatge)`, `close()`, `abort()` |
| `extract_frames(vídeo, instants)` | llista de `RGBImage` (proves) |
| `waveform(fitxer, punts)` | pics 0–1 |

`EncoderSettings`: 30 fps, CRF 18, preset `medium`, perfil `high`, AAC 192 kbps. Errors: `FfmpegError`.
Afegit al C01 (decisió 0012; implementació al C04): `convert_to_mp3(origen, destí, bitrate_kbps, tags, progress=None,
cancel=None) -> None` converteix qualsevol àudio a MP3 (libmp3lame, `bitrate_kbps` constant, 48 kHz estèreo, etiquetes
ID3 de `Mp3Tags(title, artist, comment)`). Escriu a un fitxer temporal al costat del destí i el reanomena en acabar: si
falla o es cancel·la, el destí no es crea. Errors: `FfmpegError` amb les claus `ffmpeg.*`.

## 9. Àudio (`passimaker.audio`) · B8

`prepare(projecte, pla_àudio, cache_dir) -> AudioSource`.
`song_from_file(ruta, id) -> Song` (M05): cançó nova amb els valors per defecte; `FfmpegError` si no es pot llegir, amb
`ffmpeg.no_audio` si no té so. La fan servir la interfície i les ordres de línia.
`AudioSource` (protocol): `duration_s`, `read(t_s, frames) -> AudioBlock` (zeros fora de rang; prou
ràpid per al temps real), `render_wav(destí, progress, cancel)` (WAV PCM 16 bits, per trossos).

## 10. Previsualització (`passimaker.preview`) · B13 (Qt permès)

`Player(compositor, línia, àudio, output=None)`: `play()`, `pause()`, `seek(t)`, `seek_photo(i)`,
`refresh()`; senyals `frame_ready(QImage, t)` i `state_changed(reproduint, t, índex_foto)`.
`Clock.now()` i `AudioOutput.start(source, from_s) -> Clock` / `stop()` permeten simular el temps.
Mida màxima: `PREVIEW_MAX_SIZE = (960, 540)`.
Afegit al B13 (aprovat en tancar-lo): paràmetres de nom `clock_factory` (rellotge intern) i `size` al constructor
(`output=None` = dispositiu de so per defecte); `set_scene(compositor, línia, àudio, at=None)` (el projecte ha
canviat: mateixa posició o `at`; si l'àudio és el mateix objecte, el so no es talla), `set_size(amplada, alçada)`,
`toggle()`, `close()`, `wait_idle()` i les propietats `playing`, `position`, `photo_index` i `timeline`.
Protocol `FrameSource` (el que el reproductor necessita del compositor) i funcions `photo_start(línia, i)` (primera
imatge on la foto es veu sencera), `photo_index_at(línia, t)` i `same_place(antiga, nova, t)`.

## 11. Exportació (`passimaker.export`) · B9

`export_project(projecte, destí, progress, cancel, sentinel=False) -> ExportResult(status,
reason_key, duration_s, size_bytes)`. `ExportStatus`: DONE, CANCELLED, ERROR.
`progress(fracció 0–1, segons_restants | None)`, des del fil que exporta, com a molt cada 0,1 s; la fracció mai no
recula. Cancel·lar atura l'exportació en menys de 2 s. El vídeo s'escriu com a `<nom>.mp4.part` i es reanomena en
acabar: si no acaba bé, no queda cap fitxer. L'ordinador no entra en repòs mentre s'exporta.
`missing_files(projecte) -> tuple[Path]`: fotos i cançons que no es troben (si n'hi ha, no s'exporta).
Claus d'error (`reason_key`): `export.no_photos`, `export.missing_files`, `export.disk_full`, `export.write_error`,
`export.failed` i les `ffmpeg.*` del §8. `cache_root()`: carpeta de les memòries cau (`%LOCALAPPDATA%\PassiMaker\cache`
a Windows; la variable `PASSIMAKER_CACHE` la substitueix); l'àudio va a `cache_root() / "audio"` i les miniatures
(B5) han d'anar a `cache_root() / "thumbs"`.

Ordres de línia (`passimaker.cli`): `passimaker-nou <carpeta> [música…] -o <projecte.pmk>
[--format 16:9|3:2|4:3|9:16|2:3|3:4] [--vertical] [--ajustar] [--llavor N]` (`--vertical` = `--format 9:16`; si no
coincideixen, error) (sense `--llavor`, una llavor a l'atzar que es desa al projecte; decisió 0008) i
`passimaker-render <projecte.pmk> <sortida.mp4> [--sentinella]`.
Codis de sortida: 0 correcte, 1 error, 2 no implementat.

## 12. Desar i obrir (`passimaker.projectio`) · B1

`save_project(projecte, ruta)` (escriptura segura), `open_project(ruta) -> OpenResult(project,
missing_files)`, `relink(projecte, carpeta) -> (projecte, nombre)`, `save_recovery`, `find_recovery`,
`clear_recovery`. Errors: `ProjectFileError`. Extensió: `.pmk`.
`format_version` 2 (M08): `project` porta `black_start` i `black_end`, cadascun `{"duration_s": s}` o `null`. Un
fitxer de la versió 1 (sense aquests camps) s'obre sense fitxes negres i es desa en versió 2.
`output_format` (M10, també versió 2): `"horizontal_16_9"`, `"horizontal_3_2"`, `"horizontal_4_3"`, `"vertical_9_16"`,
`"vertical_2_3"` o `"vertical_3_4"`. Els valors dels fitxers anteriors, `"horizontal"` i `"vertical"`, s'obren com a
16:9 i 9:16 i es desen amb el nom nou.
M13 (sense canviar de versió, perquè el format 2 encara no s'havia publicat): `music` porta `silence_start_s` i
`silence_end_s` (segons); si no hi són (fitxers d'abans), valen 0, i si són fora del rang, es limiten.

## 13. Interfície (`passimaker.ui`) · B10, B11, B14, B16

Punt d'entrada `passimaker = passimaker.ui.app:main(argv) -> int`. Només parla amb el controlador, la
importació, les miniatures, el compositor, el reproductor, l'exportació i `projectio`. Textos amb
`tr()`; els missatges dels errors del nucli es tradueixen amb `passimaker.i18n.message(clau)`.
Ampliat al B14 (aprovat per l'usuari el 23/10/2026; resol també el pendent del B11): la interfície pot fer servir
`passimaker.timeline` (línia de temps, avís d'ajustar a la música i `build_audio_plan`), `passimaker.audio`
(`prepare`, per escoltar un tros d'una cançó tal com sonarà) i `passimaker.ffmpeg` (`probe` per a la durada de les
cançons i `waveform` per a la forma d'ona), sempre fora del fil de la interfície quan triguin.
Ampliat al C01 (decisió 0012): la interfície pot fer servir `passimaker.youtube` (§15) i
`passimaker.ffmpeg.convert_to_mp3`, sempre fora del fil de la interfície. No importa `yt_dlp` ni cap mòdul de xarxa;
[Obre a YouTube] fa servir `QDesktopServices.openUrl` (obre el navegador, el programa no s'hi connecta).
Ampliat al C07 (decisió 0013): la interfície pot fer servir `passimaker.recorder` (§16): `list_sources`, `Monitor` i
`Recorder` (es creen i s'aturen fora del fil de la interfície; les propietats i `peaks_since` es llegeixen des d'un
`QTimer`, `defaults.RECORD_WAVE_REFRESH_HZ` cops per segon) i `remove_leftovers` en obrir el programa.

## 14. Substituts per a les proves (`tests/fakes`)

| Substitut | Fa el paper de |
|---|---|
| `SyntheticImageSource` | `ImageSource` (imatges sintètiques de només lectura amb la proporció de la foto; registra les peticions) |
| `ToneAudioSource` | `AudioSource` (to pur) |
| `SimulatedClock` | `Clock` |
| `fixed_timeline`, `fixed_query` | `compute_timeline`, `query` (versió simplificada) |
| `fixed_motion`, `fixed_window_at` | `draw_motions`, `window_at` (moviments fixos) |

Dades de prova: `tests/fixtures/generate.py` (fixture de pytest `fixture_files`).

## 15. Música de YouTube (`passimaker.youtube`) · C01 (contracte), C03 (implementació)

L'únic mòdul que pot obrir connexions de xarxa (decisió 0012; hi ha una prova). Sense Qt. `import yt_dlp` només dins
de les funcions que el fan servir, mai en carregar el mòdul.

| Operació | Rep | Retorna |
|---|---|---|
| `parse_link(text)` | text enganxat | `video_id: str` (11 caràcters) o `None`. Pur, sense xarxa. Admet `youtube.com/watch?v=…` (també `m.` i `music.`), `youtu.be/…`, `/shorts/…`, `/embed/…` i `/live/…`, amb paràmetres extra o sense l'esquema |
| `watch_url(video_id)` | — | `https://www.youtube.com/watch?v=<id>` |
| `search(token, query, limit=10, offset=0, cancel=None)` | — | `tuple[SearchResult, ...]` (com a molt `limit`; `offset` per a [Més resultats]) |
| `resolve(token, video_id, cancel=None)` | — | `SearchResult` |
| `fetch_thumbnail(token, url, cancel=None)` | — | `bytes` de la imatge (la interfície la descodifica) |
| `download_audio(token, video_id, temp_dir, progress=None, cancel=None)` | — | `Path` de l'àudio original (M4A/WebM, sense postprocés), dins de `temp_dir`. Cancel·lar no deixa cap fitxer. |
| `safe_target_path(folder, title)` | — | `Path` lliure `<títol>.mp3`, vàlid a Windows (`<títol> (2).mp3`… si ja existeix); mai un fitxer existent. Des del C09 és a `passimaker.common.files` (compartit amb la gravació); `passimaker.youtube` el continua exportant, amb `YouTube` per a un títol buit |
| `consent.grant()` / `consent.current()` / `consent.revoke()` | — | `ConsentToken` / `ConsentToken` o `None` / — |
| `consent.is_valid(token)` / `consent.require(token)` | — | `bool` / llança `YoutubeConsentError` |

**Conformitat.** `ConsentToken` només el crea `consent.grant()` (cridat en acceptar l'avís, ESPECIFICACIO §1.7 bis).
L'estat és només a la memòria del procés, compartit per totes les finestres, i no es desa enlloc. Mentre dura la
conformitat, `grant()` retorna el mateix testimoni; `revoke()` invalida tots els testimonis donats fins llavors. Les
funcions que es poden connectar (`search`, `resolve`, `fetch_thumbnail`, `download_audio`) criden `require(token)`
abans de res: sense un testimoni vàlid, `YoutubeConsentError` i cap intent de connexió.

`SearchResult`: `video_id`, `title`, `channel`, `duration_s` (`float | None`), `thumbnail_url`, `is_live`, `url`.

Errors (hereten de `YoutubeError`, que hereta de `PassiMakerError`):

| Error | Clau (`passimaker.i18n`) | Quan |
|---|---|---|
| `YoutubeOfflineError` | `youtube.offline` | sense connexió |
| `YoutubeUnavailableError` | `youtube.unavailable` · `youtube.live` | privat, esborrat o amb restriccions · directe en curs |
| `YoutubeBrokenError` | `youtube.broken` | YouTube ha canviat i yt-dlp no funciona (el detall, per al registre); també qualsevol error que no es reconeix |
| `YoutubeBlockedError` | `youtube.blocked` | YouTube no deixa descarregar des d'aquesta xarxa ("confirma que no ets un robot", HTTP 429, límit de peticions, captcha) · C03, decisió de l'usuari del 25/10/2026 |
| `YoutubeTooLongError` | `youtube.too_long` | més de `defaults.YOUTUBE_MAX_DURATION_S` |
| `YoutubeConsentError` | `youtube.consent` | sense conformitat |
| — | `youtube.invalid_link` | la interfície, quan `parse_link` no reconeix un enllaç enganxat |

Valors (`passimaker.model.defaults`): `YOUTUBE_RESULTS_PER_PAGE = 10`, `YOUTUBE_MAX_DURATION_S = 1200`,
`YOUTUBE_MP3_BITRATE_KBPS = 192`, `YOUTUBE_SIMULTANEOUS_DOWNLOADS = 2`.

**Backend** (C03). `search`, `resolve`, `fetch_thumbnail` i `download_audio` accepten un paràmetre opcional
(només per nom) `backend: YoutubeBackend`; sense, fan servir `YtDlpBackend` (yt-dlp com a biblioteca, el servidor
intermediari del sistema i el Deno del paquet; yt-dlp no fa cap conversió ni fa servir FFmpeg; format
`bestaudio[audio_channels<=?2]/bestaudio` per baixar, l'estèreo abans que el 5.1; per llegir les dades d'un vídeo,
el mateix amb `/best` al final, perquè un directe, que no té cap format només d'àudio, arribi a `ERROR_LIVE`). El protocol
`YoutubeBackend` té `extract_info(url, *, flat)`, `download(info, folder, hook)` i `fetch(url, max_bytes)`; els errors
que en surten els tradueix `youtube.errors.translate` (vegeu la taula d'errors). El substitut de proves és
`tests/fakes/youtube.py` (`FakeYoutubeBackend`).

**Cancel·lació** (C03). Les quatre funcions llancen `concurrent.futures.CancelledError` si el `CancelToken` s'activa
(la baixada s'atura al bloc de dades següent). `download_audio` no deixa cap fitxer en cancel·lar o fallar.

**Detalls** (C03).
- `search`: només vídeos (sense canals ni llistes); consulta buida → `()`; com a molt `MAX_SEARCH_RESULTS = 100`
  (`offset + limit`); `limit < 1` o `offset < 0` → `ValueError`.
- `resolve` i `search` retornen també els directes (`is_live`) i els vídeos massa llargs: la interfície els mostra en
  gris. `download_audio` els rebutja abans de baixar res (`ERROR_LIVE`, `YoutubeTooLongError`).
- `SearchResult.thumbnail_url` és sempre `https://i.ytimg.com/vi/<id>/mqdefault.jpg` (320×180).
  `fetch_thumbnail` només va a `https` de `ytimg.com`, `ggpht.com` o `googleusercontent.com` (si no, `ValueError`) i
  com a molt 2 MB.
- `download_audio`: el fitxer és dins d'una carpeta nova `youtube_…` de `temp_dir`; progrés en bytes, que no recula i
  acaba a `(total, total)`. Un error d'escriptura local (disc ple, sense permís) surt com l'`OSError` original, no com a
  error de YouTube.
- `safe_target_path` (C09: **ara a `passimaker.common.files`**, `safe_target_path(folder, title, *, fallback="Cançó")`,
  perquè la gravació també el fa servir; `passimaker.youtube.safe_target_path(folder, title)` hi crida amb
  `fallback="YouTube"`): treu `< > : " / \ | ? *` i els caràcters de control, els punts i espais del final, i posa `_`
  davant dels noms reservats (`CON`, `NUL`, `COM1`…, també `con.txt`); com a molt 150 unitats UTF-16 i 200 bytes UTF-8,
  menys si la carpeta és molt llarga (perquè la ruta càpiga en 259 caràcters), però mai menys de 20; títol buit →
  `<fallback>.mp3` (`YouTube.mp3` des de `passimaker.youtube`).
- Un enllaç o `video_id` mal format a `resolve` o `download_audio` → `ValueError` (error de programació: la interfície
  passa sempre el que retorna `parse_link`).

**Proves amb xarxa real**: marca `xarxa`, excloses per defecte; a més s'ometen si no hi ha `PASSIMAKER_XARXA=1`
(la CI fa `-m "not perf"`). Només al PC de l'usuari: `uv run pytest -m xarxa` amb la variable.

## 16. Grava el que sona (`passimaker.recorder`) · C07 (contracte), C09 (implementació)

Grava el so que sona per una sortida de Windows (WASAPI loopback) o, només si l'usuari la tria, una entrada (micròfon,
línia). Decisió 0013, ESPECIFICACIO §1.7 ter, annex `docs/PLA_GRAVACIO.md` §3. Sense Qt i **sense xarxa** (hi ha una
prova). La tecnologia de captura queda darrere de `CaptureBackend` (C08: sounddevice no serveix; `soundcard` 0.4.6,
aprovada per l'usuari, G10), implementada al C09 (`SoundcardBackend`).

| Operació | Rep | Retorna |
|---|---|---|
| `list_sources(*, backend=None)` | — | `tuple[AudioSource, ...]`: primer les sortides (la per defecte, primera), després les entrades; `()` si no n'hi ha cap |
| `Monitor(source, *, backend=None)` | — | ones i nivell **sense gravar** (no escriu res al disc): `start()`, `stop()`, `level_dbfs`, `peaks_since(n)`, `error` |
| `Recorder(source, temp_dir, settings=None, *, backend=None)` | `RecordingSettings` (sense: els valors de `defaults.py`) | objecte de gravació |
| `Recorder.start()` | — | Comença (WAITING amb "Comença quan soni", si no RECORDING). `RecorderDiskFullError(ERROR_NO_SPACE)` amb menys de `min_free_bytes` lliures; `RecorderNoDeviceError` o `RecorderDeviceError` si no es pot obrir l'origen |
| `Recorder.stop()` | — | `RecordingResult(wav_path, duration_s, trimmed_start_s, trimmed_end_s, stop_reason, gain_db)`, ja retallat i normalitzat. Si estava INTERRUPTED, llança `Recorder.error`; si no s'ha gravat cap so (res per sobre de `trim_threshold_dbfs`), esborra el WAV i llança `RecorderSilentError`. Reescriu el WAV si cal retallar o normalitzar: fora del fil de la interfície (regla 6) |
| `Recorder.discard()` | — | Atura i ho esborra tot ([Descarta], tancar la finestra o el programa) |
| `Recorder.state` / `error` / `elapsed_s` / `level_dbfs` | — | propietats de lectura, segures des d'un altre fil. `elapsed_s` = segons desats (0 en WAITING). `level_dbfs` = un valor per canal gravat, en dBFS (−inf en silenci digital) |
| `Recorder.peaks_since(n)` / `Monitor.peaks_since(n)` | índex de la darrera columna rebuda (0 la primera vegada) | `(columnes noves, nou índex)`: `PeakColumns`, matriu `float32` (columnes, canals, 2) amb el mínim i el màxim de cada columna (`defaults.RECORD_PEAK_COLUMNS_PER_S` per segon); el `Monitor` només guarda els últims `RECORD_WAVE_WINDOW_S` |
| `Recorder.overview(amplada)` | píxels | `PeakColumns` de tota la gravació reduïda a `amplada` columnes (en aturar), abans de retallar i normalitzar (`RecordingResult` diu què s'ha retallat i el guany); conserva el mínim i el màxim de cada tram |
| `trim_silence(samples, sample_rate, threshold_dbfs, margin_s)` | `(fotogrames, canals)` o `(fotogrames,)`: l'àudio o una envolupant dels pics (`sample_rate` = columnes per segon) | `(inici_s, final_s)` de la part que es conserva, amb `margin_s` abans del primer so i després de l'últim, dins de la gravació; `None` si tot és per sota del llindar. Pur |
| `remove_leftovers(temp_dir)` | — | nombre de WAV temporals (`TEMP_PREFIX` = `passimaker_gravacio_`) esborrats; en obrir el programa (G1). Un WAV que no es pot esborrar (a Windows, el d'un altre PassiMaker que grava) es deixa |

**Normalització en desar** (decisió de l'usuari del 26/10/2026, `docs/sessions/C08.md`; C09). A `stop()`, després de
retallar: si el pic de la part conservada (el més alt de tots els canals) és per sota de `normalize_peak_dbfs`
(`defaults.RECORD_NORMALIZE_PEAK_DBFS = -1`), tota la gravació es multiplica pel mateix guany fins que el pic hi arriba;
**mai més amunt**, i una gravació més forta no s'abaixa mai. `RecordingResult.gain_db` diu el guany (0 si no s'ha tocat).
`RecordingSettings.normalize` (`defaults.RECORD_NORMALIZE_ENABLED = True`) l'activa.

**Desar o esborrar (G1, G5).** Una gravació es desa només si acaba amb `stop()` (`StopReason.USER`) o amb l'aturada
automàtica per silenci (estat FINISHED; `stop()` retorna `StopReason.SILENCE`). Qualsevol altra causa (desconnexió, disc
ple, durada màxima, error del so, `discard()`) esborra el WAV **abans** que l'error sigui visible: estat INTERRUPTED,
`error` amb la causa, i `stop()` la llança. El WAV d'un `RecordingResult` és de qui el rep: el converteix a MP3
(`ffmpeg.convert_to_mp3`, `defaults.RECORD_MP3_BITRATE_KBPS`) i l'esborra.

**Detalls (C09).** Amb "Comença quan soni", en arribar el primer so (`start_threshold_dbfs`) es desa també l'àudio dels
`trim_margin_s` d'abans (perquè el retall en pugui conservar el marge); el temps d'espera no compta per a
`max_duration_s`. L'aturada automàtica per silenci només actua després d'haver sentit algun so (`silence_threshold_dbfs`).
`start()` dues vegades, o `stop()` abans de `start()` o després de `stop()`/`discard()`, és un error de programació
(`RuntimeError`); `discard()` es pot cridar sempre (després de `stop()` no toca el WAV retornat). `stop()` i `discard()`
esperen el fil de captura com a molt 5 s; si no s'atura, el fil esborra el WAV quan acaba i `stop()` llança
`RecorderDeviceError`.

`AudioSource`: `id` (text opac del backend), `name`, `kind: SourceKind` (OUTPUT_LOOPBACK, INPUT), `is_default`,
`sample_rate`, `channels`; propietat `recorded_channels` (1 per a un origen mono, si no 2: un 5.1 es grava en estèreo).
`StopReason`: USER, SILENCE. `RecorderState`: IDLE, WAITING, RECORDING, FINISHED, INTERRUPTED, CLOSED.
`RecordingSettings`: `start_when_sound`, `start_threshold_dbfs`, `silence_stop`, `silence_stop_s`,
`silence_threshold_dbfs`, `trim`, `trim_threshold_dbfs`, `trim_margin_s`, `max_duration_s`, `min_free_bytes`,
`peak_columns_per_s`, `normalize`, `normalize_peak_dbfs` (C09).

**Backend** (protocols a `passimaker.recorder.backend`, ajustats al C09 segons el C08). `CaptureBackend`:
`list_sources()`, `open(source) -> CaptureStream` (des del fil de captura: COM hi viu; `RecorderNoDeviceError`,
`RecorderMicrophoneDeniedError` o `RecorderDeviceError`) i `default_output_id() -> str | None` (nou al C09). `CaptureStream`
(només des del fil que l'ha obert): `sample_rate`, `channels` (1 o 2), `read(timeout_s) -> AudioFrames | None` (`float32`
(fotogrames, canals); `None` si no ha arribat res; el silenci són blocs de zeros), `discontinuities()` (substitueix
`dropped_frames()`: WASAPI avisa de les discontinuïtats, no de les mostres perdudes) i `close()`; llança
`RecorderDeviceLostError` o `RecorderDeviceError`. Implementació real: `SoundcardBackend` (`soundcard` 0.4.6, importat
només dins dels mètodes): demana 48 kHz (WASAPI converteix la freqüència i mescla el 5.1 en estèreo), blocs de
`defaults.RECORD_BLOCK_S`, `CoInitializeEx(COINIT_MULTITHREADED)` al fil que crida (i fins a `close()` per al flux),
compta i anota al registre les discontinuïtats sense aturar res, i obre el dispositiu pel seu `id` exacte (mai la
cerca aproximada per nom de `soundcard`). Substitut de proves: `FakeCaptureBackend` a `tests/fakes/recorder.py`, amb tons,
silencis, discontinuïtats, canvi de sortida, desconnexió i errors.

**Canvi de sortida (C08).** WASAPI no dona cap error si Windows canvia la sortida per defecte a mitja gravació: la
captura continua, en silenci, de la sortida antiga. Si l'origen és la sortida per defecte en començar, el fil de captura
consulta `default_output_id()` cada `defaults.RECORD_DEVICE_POLL_S` (1 s d'àudio) i, si ha canviat, ho tracta com a
`RecorderDeviceLostError`. Amb la mateixa freqüència comprova l'espai lliure (`RecorderDiskFullError`). Una altra sortida
o una entrada no es vigila així (les seves fallades arriben com a errors del so).

Errors (hereten de `RecorderError`, que hereta de `PassiMakerError`):

| Error | Clau (`passimaker.i18n`) | Quan |
|---|---|---|
| `RecorderNoDeviceError` | `recorder.no_device` | no hi ha cap sortida de so, o l'origen triat ja no hi és |
| `RecorderDeviceLostError` | `recorder.device_lost` | la sortida canvia o es desconnecta mentre es grava |
| `RecorderSilentError` | `recorder.silent` | `stop()` sense cap so per sobre del llindar |
| `RecorderDiskFullError` | `recorder.disk_full` · `recorder.no_space` | menys de `RECORD_MIN_FREE_BYTES` gravant · en començar |
| `RecorderMaxDurationError` | `recorder.max_duration` | `RECORD_MAX_DURATION_S` (G5) |
| `RecorderDeviceError` | `recorder.device_error` | qualsevol altra fallada del so (el detall, per al registre) |
| `RecorderMicrophoneDeniedError` | `recorder.microphone_denied` | Windows no deixa fer servir el micròfon a les aplicacions d'escriptori (`0x80070005`, C08); el missatge diu on s'activa (C09) |

Valors (`passimaker.model.defaults`): `RECORD_START_WHEN_SOUND`, `RECORD_START_THRESHOLD_DBFS = -50`,
`RECORD_SILENCE_STOP_ENABLED`, `RECORD_SILENCE_STOP_S = 5` (`RECORD_SILENCE_STOP_RANGE` 1–60),
`RECORD_SILENCE_THRESHOLD_DBFS = -50`, `RECORD_TRIM_ENABLED`, `RECORD_TRIM_THRESHOLD_DBFS = -50`,
`RECORD_TRIM_MARGIN_S = 0.2`, `RECORD_MAX_DURATION_S = 1800`, `RECORD_MAX_WARNING_S = 60`, `RECORD_MIN_FREE_BYTES` (1 GB),
`RECORD_MP3_BITRATE_KBPS = 192`, `RECORD_WAVE_WINDOW_S = 10`, `RECORD_PEAK_COLUMNS_PER_S = 50`,
`RECORD_WAVE_REFRESH_HZ = 30`, `RECORD_CLIP_HOLD_S = 2`, `RECORD_DISCARD_CONFIRM_S = 10`; i del C09:
`RECORD_NORMALIZE_ENABLED = True`, `RECORD_NORMALIZE_PEAK_DBFS = -1`, `RECORD_BLOCK_S = 0.05`, `RECORD_DEVICE_POLL_S = 1`,
`RECORD_OPEN_TIMEOUT_S = 10`.

**Proves amb una targeta de so real**: marca `so`, excloses per defecte; a més s'han d'ometre si no hi ha
`PASSIMAKER_SO=1` (la CI fa `-m "not perf"`). Només al PC de l'usuari: `uv run pytest -m so` amb la variable.
