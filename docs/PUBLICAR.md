# Publicar una versió

Una versió és una etiqueta (`v1.1`) i una versió publicada a GitHub (Releases) amb el ZIP portable adjunt.
Hi ha dues maneres de fer-ho. Fan el mateix.

## Des d'una sessió al núvol (o des de GitHub)
Les sessions al núvol no poden crear etiquetes ni versions publicades: el proxy de GitHub rebutja els `git push`
d'etiquetes i les crides a l'API que les creen (comprovat el 24/10/2026). Sí que poden engegar el flux
`.github/workflows/publicar.yml`, que ho fa amb el permís propi del repositori:

```
gh workflow run publicar.yml -f etiqueta=v1.1 -f commit=main
```

Opcions: `-f titol="PassiMaker 1.1.0"` (si no, el pren del `pyproject.toml`), `-f principal=false` (no la marca com
a versió principal) i `-f prova=true` (ho comprova i construeix el ZIP, però no publica res).
El flux: comprova que l'etiqueta té la forma `v1`, `v1.1` o `v1.1.0` i que encara no existeix, construeix el ZIP a
Windows i el prova, i crea l'etiqueta i la versió publicada amb el ZIP adjunt i les notes generades.

A mà, des de GitHub: *Actions → Publicar una versió → Run workflow*.

## Des d'una sessió local (al PC)
Amb `git` i `gh` amb la sessió iniciada (`gh auth login`), es pot fer directament:

```
git fetch origin
git tag -a v1.1 <commit> -m "PassiMaker 1.1.0"
git push origin v1.1
```

La CI genera el ZIP de l'etiqueta (artefacte `PassiMaker-<versió>-win64`). Per crear també la versió publicada amb el
ZIP adjunt, el més senzill és fer servir el mateix flux: `gh workflow run publicar.yml -f etiqueta=v1.1` (sense crear
l'etiqueta abans).

## Pedaços de yt-dlp (1.2.x)
El flux `.github/workflows/actualitzar-ytdlp.yml` comprova cada dilluns si hi ha un yt-dlp nou i, si n'hi ha, obre una
PR (`manteniment/yt-dlp-<versió>`) i hi llança la CI. Quan l'usuari vegi "YouTube ha canviat": fusionar aquesta PR,
pujar la versió de pedaç (1.2.1, 1.2.2…) a `pyproject.toml`, `src/passimaker/__init__.py` i `uv.lock`, i publicar-la
amb `publicar.yml`. Cal que el repositori permeti als fluxos crear PR (Settings → Actions → General).

## Versions publicades
| Etiqueta | Commit | Versió |
|---|---|---|
| `v0.5-mvp` | `a96edd6` (B15) | 0.5.0, MVP (fita F3) |
| `v1.0` | `289ac83` (tancament del B16; mateix codi que `47d7d34`) | 1.0.0 |
Totes dues creades a mà des de GitHub el 24/10/2026, abans que existís aquest flux.
