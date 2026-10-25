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
| Projecte | `Project` | `name`, `format_version`, `output_format`, `seed`, `default_duration_s`, `crossfade_s`, `fade_from_black_s`, `fade_to_black_s`, `motion_enabled`, `zoom_amount`, `pan_amount`, `photos: tuple[Photo]`, `music: Music` · mètode `photo_duration(photo)` |
| Foto | `Photo` | `id`, `path`, `relative_path`, `width`, `height` (ja orientades i girades), `exif_orientation`, `capture_time`, `duration_s` (`None` = durada general), `fit: FitMode`, `motion: PhotoMotion`, `rotation: Rotation` (P2), `low_resolution` |
| MovimentFoto | `PhotoMotion` | `mode: MotionMode`, `type: MotionType`, `draw_count`, `start: Window`, `end: Window`, `resolved_fit: ResolvedFit` |
| Finestra | `Window` | `centre_x`, `centre_y` (0–1 sobre el llenç), `scale` (1 = la finestra més gran de la proporció del vídeo que hi cap; >1 = més a prop) |
| Música | `Music` | `master_volume` (0–1), `normalize`, `keep_fitted`, `songs: tuple[Song]` |
| Cançó | `Song` | `id`, `path`, `relative_path`, `original_duration_s`, `trim_start_s`, `trim_end_s` (`None` = fins al final), `fade_in: Fade`, `fade_out: Fade`, `volume` (0–1,5), `loudness_gain_db` (calculat) |
| Fosa | `Fade` | `enabled`, `seconds` |

Enumeracions: `OutputFormat` (HORIZONTAL 1920×1080, VERTICAL 1080×1920; propietat `size`),
`Intensity` (SOFT, MEDIUM, STRONG; preseleccions de `zoom_amount` i `pan_amount`, vegeu `passimaker.motion.INTENSITY_PRESETS`), `FitMode` (AUTO, FILL, BLUR, BLACK), `ResolvedFit` (FILL, BLUR,
BLACK), `MotionMode` (AUTO, MANUAL), `MotionType` (ZOOM_IN, ZOOM_OUT, PAN_LEFT, PAN_RIGHT, PAN_UP,
PAN_DOWN, COMBINED, NONE), `Rotation` (R0, R90, R180, R270).

Valors per defecte i rangs: **només** a `passimaker.model.defaults` (per ajustar-los després de les fites).

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
`SortPhotos`, `SetDefaultDuration`, `SetPhotoDuration`, `SetPhotoFit`, `SetPhotoMotion`,
`RerollMotions`, `RotatePhotos`, `SetProjectSettings`, `AddSongs`, `RemoveSongs`, `MoveSongs`,
`UpdateSong`, `SetMusicSettings`, `FitToMusic`. Són dades; la lògica és al controlador (B1). Les
ordres que afecten el moviment (afegir, duplicar, girar, canviar format o encaix, tornar a sortejar)
fan servir `passimaker.motion` per resoldre l'encaix i sortejar. `RerollMotions(ids)` torna a sortejar aquestes fotos
i, si tenien el moviment fixat a mà, les torna a automàtic (M05); `RerollMotions(None)`, només les automàtiques.

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
| `time_to_frame(t, fps)` / `frame_to_time(n, fps)` | — | conversió |

`Timeline`: `fps`, `total_duration_s`, `total_frames`, `slots: tuple[PhotoSlot]`, `fade_from_black`,
`fade_to_black` (`Interval` o `None`), `audio_plan: AudioPlan`, `music_duration_s`.
`PhotoSlot`: `photo_id`, `index`, `slot_start`, `slot_end` (espai propi, contigus), `visible_start`,
`visible_end`, `fade_in`, `fade_out`.
`AudioPlan`: `segments: tuple[AudioSegment]`, `final_fade`. `AudioSegment`: `song_id`,
`video_start`, `video_end`, `source_start`, `fade_in_s`, `fade_out_s`.
`Visibles`: `layers` (com a màxim 2, de baix a dalt) de `VisibleLayer(photo_id, opacity,
motion_progress)` i `black_level` (0–1).

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

Ordres de línia (`passimaker.cli`): `passimaker-nou <carpeta> [música…] -o <projecte.pmk> [--vertical]
[--ajustar] [--llavor N]` (sense `--llavor`, una llavor a l'atzar que es desa al projecte; decisió 0008) i
`passimaker-render <projecte.pmk> <sortida.mp4> [--sentinella]`.
Codis de sortida: 0 correcte, 1 error, 2 no implementat.

## 12. Desar i obrir (`passimaker.projectio`) · B1

`save_project(projecte, ruta)` (escriptura segura), `open_project(ruta) -> OpenResult(project,
missing_files)`, `relink(projecte, carpeta) -> (projecte, nombre)`, `save_recovery`, `find_recovery`,
`clear_recovery`. Errors: `ProjectFileError`. Extensió: `.pmk`.

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
| `safe_target_path(folder, title)` | — | `Path` lliure `<títol>.mp3`, vàlid a Windows (`<títol> (2).mp3`… si ja existeix); mai un fitxer existent |
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
| `YoutubeBrokenError` | `youtube.broken` | YouTube ha canviat i yt-dlp no funciona (el detall, per al registre) |
| `YoutubeTooLongError` | `youtube.too_long` | més de `defaults.YOUTUBE_MAX_DURATION_S` |
| `YoutubeConsentError` | `youtube.consent` | sense conformitat |
| — | `youtube.invalid_link` | la interfície, quan `parse_link` no reconeix un enllaç enganxat |

Valors (`passimaker.model.defaults`): `YOUTUBE_RESULTS_PER_PAGE = 10`, `YOUTUBE_MAX_DURATION_S = 1200`,
`YOUTUBE_MP3_BITRATE_KBPS = 192`, `YOUTUBE_SIMULTANEOUS_DOWNLOADS = 2`.

Proves: el substitut de yt-dlp (un "backend" injectable, a `tests/fakes`) i la marca `xarxa` per a les proves amb
xarxa real (excloses per defecte i a la CI) es defineixen al C03.
