# Passi: contractes entre mòduls

> Font de veritat de les interfícies entre blocs. Desenvolupa el §2.3 de `docs/PLA.md`.
> El codi fa servir noms en anglès; aquí es dona la correspondència amb els noms del pla.
> Qualsevol canvi en aquest document s'ha de proposar i aprovar abans (vegeu CLAUDE.md).
> Les definicions en codi (tipus i signatures) són a `src/passi/**` i en són l'expressió exacta.

## 0. Convencions comunes (`passi.common`)

| Nom al codi | Significat |
|---|---|
| `RGBImage` | Imatge NumPy de forma (alçada, amplada, 3), `uint8`, sRGB |
| `AudioBlock` | Mostres NumPy de forma (fotogrames, 2), `float32` entre −1 i 1, 48 kHz estèreo |
| `ProgressCallback` | `progrés(fet, total)`; pot cridar-se des d'un fil de treball |
| `CancelToken` | Senyal de cancel·lació compartit (`cancel()`, `cancelled`) |
| `PassiError(message_key, detail)` | Error base. `message_key` és la clau del missatge en català (`passi.i18n`) |

Unitats: temps en segons (`float`); a l'exportació, fotogrames enters a 30 fps. Finestres de moviment
normalitzades (0–1) respecte del llenç.

## 1. Model (`passi.model`) · blocs B1 (implementació) i tots (ús)

Totes les estructures són **immutables** (`frozen dataclass`, llistes com a `tuple`). Només el
controlador crea versions noves del projecte.

| Pla | Codi | Camps (codi) |
|---|---|---|
| Projecte | `Project` | `name`, `format_version`, `output_format`, `seed`, `default_duration_s`, `crossfade_s`, `fade_from_black_s`, `fade_to_black_s`, `motion_enabled`, `intensity`, `photos: tuple[Photo]`, `music: Music` · mètode `photo_duration(photo)` |
| Foto | `Photo` | `id`, `path`, `relative_path`, `width`, `height` (ja orientades i girades), `exif_orientation`, `capture_time`, `duration_s` (`None` = durada general), `fit: FitMode`, `motion: PhotoMotion`, `rotation: Rotation` (P2), `low_resolution` |
| MovimentFoto | `PhotoMotion` | `mode: MotionMode`, `type: MotionType`, `draw_count`, `start: Window`, `end: Window`, `resolved_fit: ResolvedFit` |
| Finestra | `Window` | `centre_x`, `centre_y` (0–1 sobre el llenç), `scale` (1 = la finestra més gran de la proporció del vídeo que hi cap; >1 = més a prop) |
| Música | `Music` | `master_volume` (0–1), `normalize`, `keep_fitted`, `songs: tuple[Song]` |
| Cançó | `Song` | `id`, `path`, `relative_path`, `original_duration_s`, `trim_start_s`, `trim_end_s` (`None` = fins al final), `fade_in: Fade`, `fade_out: Fade`, `volume` (0–1,5), `loudness_gain_db` (calculat) |
| Fosa | `Fade` | `enabled`, `seconds` |

Enumeracions: `OutputFormat` (HORIZONTAL 1920×1080, VERTICAL 1080×1920; propietat `size`),
`Intensity` (SOFT, MEDIUM, STRONG), `FitMode` (AUTO, FILL, BLUR, BLACK), `ResolvedFit` (FILL, BLUR,
BLACK), `MotionMode` (AUTO, MANUAL), `MotionType` (ZOOM_IN, ZOOM_OUT, PAN_LEFT, PAN_RIGHT, PAN_UP,
PAN_DOWN, COMBINED, NONE), `Rotation` (R0, R90, R180, R270).

Valors per defecte i rangs: **només** a `passi.model.defaults` (per ajustar-los després de les fites).

### Controlador (`ProjectController`)

| Operació | Rep | Retorna / efecte |
|---|---|---|
| `execute(ordre)` | una ordre de `passi.model.commands` | Aplica l'ordre, limita els valors als rangs, desa l'estat anterior per desfer, avisa els observadors. Retorna el conjunt de `Change`. |
| `undo()` / `redo()` | — | Restaura l'estat anterior / següent (P1). Retorna `Change`. |
| `subscribe(observador)` | funció `(changes) -> None` | Funció per donar-se de baixa |
| `replace_project(projecte)` | projecte obert o recuperat | Buida l'historial i la marca de canvis |
| `mark_saved()` | — | Esborra la marca de canvis sense desar |
| `project`, `has_unsaved_changes`, `can_undo`, `can_redo` | — | Propietats de lectura |

`Change`: PHOTOS, TIMING, MOTION, MUSIC, SETTINGS, SAVED_STATE.

Ordres (`passi.model.commands`): `AddPhotos`, `RemovePhotos`, `MovePhotos`, `DuplicatePhotos`,
`SortPhotos`, `SetDefaultDuration`, `SetPhotoDuration`, `SetPhotoFit`, `SetPhotoMotion`,
`RerollMotions`, `RotatePhotos`, `SetProjectSettings`, `AddSongs`, `RemoveSongs`, `MoveSongs`,
`UpdateSong`, `SetMusicSettings`, `FitToMusic`. Són dades; la lògica és al controlador (B1). Les
ordres que afecten el moviment (afegir, duplicar, girar, canviar format o encaix, tornar a sortejar)
fan servir `passi.motion` per resoldre l'encaix i sortejar.

## 2. Importació (`passi.importer`) · B4

| Operació | Rep | Retorna |
|---|---|---|
| `import_paths(rutes, existing, include_subfolders, progress, cancel)` | fitxers i carpetes | `ImportResult(candidates, failures, duplicates, subfolder_photo_count, cancelled)` |
| `sort_candidates(candidats, by_date)` | `by_date=None` aplica la regla automàtica del §1.1 | llista ordenada |

`PhotoCandidate`: `path`, `width`, `height` (orientades), `exif_orientation`, `capture_time`,
`file_time`, `color_profile`. `FailedFile(path, reason)` amb `ImportFailure` (UNSUPPORTED, RAW,
CORRUPT, TOO_SMALL, NOT_FOUND).

## 3. Imatges (`passi.images`) · B4

`ImageSource` (protocol):

| Operació | Rep | Retorna |
|---|---|---|
| `get_image(foto, min_long_side)` | foto, costat llarg mínim | `RGBImage` orientada (EXIF + gir manual), sRGB, costat llarg ≥ mínim (o la mida original si és més petita) i no més del doble. Error: `ImageDecodeError`. |
| `prefetch(fotos, min_long_side)` | — | Torna de seguida; descodifica en segon pla |

Implementació: `CachedImageSource(memory_budget_bytes=768 MB, workers=2)`.

## 4. Miniatures i intermedis (`passi.thumbs`) · B5

`ThumbnailService(cache_dir, image_source, disk_limit_bytes=2 GB)`:
`request_thumbnail(foto, Priority, callback)` (resposta `callback(photo_id, imatge|None)` des d'un fil),
`get_intermediate(foto) -> RGBImage` (1.600 px, bloquejant), `cancel_pending()`, `close()`.
Mides: `THUMBNAIL_SIZE = 256`, `INTERMEDIATE_SIZE = 1600`.

## 5. Línia de temps (`passi.timeline`) · B2

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

## 6. Moviments i encaix (`passi.motion`) · B3

| Operació | Rep | Retorna |
|---|---|---|
| `resolve_fit(amplada, alçada, format, preferència)` | — | `FitDecision(fit, canvas_width, canvas_height)` |
| `draw_motions(peticions, llavor, intensitat, which)` | `MotionRequest` per foto | `dict[photo_id, PhotoMotion]` |
| `window_at(moviment, progrés)` | progrés 0–1 | `Window` (sempre dins el llenç) |

Paràmetres (un sol lloc): `FILL_RATIO_RANGE`, `BASE_PROBABILITIES`, `INTENSITY_PARAMS`,
`BLUR_INTENSITY_FACTOR`, `MAX_UPSCALE`.

## 7. Compositor (`passi.render`) · B6

`Compositor(projecte, línia, image_source, intermediate=None)`:
`frame_at(t, amplada, alçada, sentinel=False) -> RGBImage`, `invalidate(photo_ids|None)`.
`SENTINEL_COLOR = (255, 0, 255)`: en mode sentinella, tot el que queda fora de la imatge es pinta
d'aquest color. Les dades de prova no contenen mai píxels semblants al magenta
(`tests/fixtures/generate.py`, `MAX_MAGENTA_EXCESS`).

## 8. Pont FFmpeg (`passi.ffmpeg`) · B7

| Operació | Retorna |
|---|---|
| `locate()` | `FfmpegPaths(ffmpeg, ffprobe)`. Ordre de cerca: variable `PASSI_FFMPEG`, carpeta del programa, `vendor/ffmpeg/bin`, `PATH`. |
| `probe(fitxer)` | `MediaInfo(duration_s, has_audio, sample_rate, channels, has_video, width, height)` |
| `decode_audio(fitxer, destí, inici, final)` | `PcmFile(path, frames)`: float32 estèreo 48 kHz |
| `measure_loudness(fitxer)` | `Loudness(integrated_lufs, true_peak_dbfs)` |
| `open_encoder(destí, amplada, alçada, wav, settings)` | `VideoWriter` amb `write(imatge)`, `close()`, `abort()` |
| `extract_frames(vídeo, instants)` | llista de `RGBImage` (proves) |
| `waveform(fitxer, punts)` | pics 0–1 |

`EncoderSettings`: 30 fps, CRF 18, preset `medium`, perfil `high`, AAC 192 kbps. Errors: `FfmpegError`.

## 9. Àudio (`passi.audio`) · B8

`prepare(projecte, pla_àudio, cache_dir) -> AudioSource`.
`AudioSource` (protocol): `duration_s`, `read(t_s, frames) -> AudioBlock` (zeros fora de rang; prou
ràpid per al temps real), `render_wav(destí, progress, cancel)` (WAV PCM 16 bits, per trossos).

## 10. Previsualització (`passi.preview`) · B13 (Qt permès)

`Player(compositor, línia, àudio, output=None)`: `play()`, `pause()`, `seek(t)`, `seek_photo(i)`,
`refresh()`; senyals `frame_ready(QImage, t)` i `state_changed(reproduint, t, índex_foto)`.
`Clock.now()` i `AudioOutput.start(source, from_s) -> Clock` / `stop()` permeten simular el temps.
Mida màxima: `PREVIEW_MAX_SIZE = (960, 540)`.

## 11. Exportació (`passi.export`) · B9

`export_project(projecte, destí, progress, cancel, sentinel=False) -> ExportResult(status,
reason_key, duration_s, size_bytes)`. `ExportStatus`: DONE, CANCELLED, ERROR.
`progress(fracció 0–1, segons_restants | None)`.

Ordres de línia (`passi.cli`): `passi-nou <carpeta> [música…] -o <projecte.passi> [--vertical]
[--ajustar] [--llavor N]` i `passi-render <projecte.passi> <sortida.mp4> [--sentinella]`.
Codis de sortida: 0 correcte, 1 error, 2 no implementat.

## 12. Desar i obrir (`passi.projectio`) · B1

`save_project(projecte, ruta)` (escriptura segura), `open_project(ruta) -> OpenResult(project,
missing_files)`, `relink(projecte, carpeta) -> (projecte, nombre)`, `save_recovery`, `find_recovery`,
`clear_recovery`. Errors: `ProjectFileError`. Extensió: `.passi`.

## 13. Interfície (`passi.ui`) · B10, B11, B14, B16

Punt d'entrada `passi = passi.ui.app:main(argv) -> int`. Només parla amb el controlador, la
importació, les miniatures, el compositor, el reproductor, l'exportació i `projectio`. Textos amb
`tr()`; els missatges dels errors del nucli es tradueixen amb `passi.i18n.message(clau)`.

## 14. Substituts per a les proves (`tests/fakes`)

| Substitut | Fa el paper de |
|---|---|
| `SyntheticImageSource` | `ImageSource` (imatges sintètiques amb la proporció de la foto; registra les peticions) |
| `ToneAudioSource` | `AudioSource` (to pur) |
| `SimulatedClock` | `Clock` |
| `fixed_timeline`, `fixed_query` | `compute_timeline`, `query` (versió simplificada) |
| `fixed_motion`, `fixed_window_at` | `draw_motions`, `window_at` (moviments fixos) |

Dades de prova: `tests/fixtures/generate.py` (fixture de pytest `fixture_files`).
