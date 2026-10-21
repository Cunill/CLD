# 0006 · Nom del programa: PassiMaker

- **Data:** 20/10/2026 · **Estat:** acceptada (petició de l'usuari) · **Aplicada a:** bloc de manteniment M01
- **Substitueix** la D1 de la decisió 0003 (nom "Passi", extensió `.passi`).

## Decisió

| Element | Abans | Ara |
|---|---|---|
| Nom visible | Passi | **PassiMaker** |
| Executable i ZIP | `Passi.exe`, `Passi-<versió>-win64.zip` | `PassiMaker.exe`, `PassiMaker-<versió>-win64.zip` |
| Paquet Python i carpeta del codi | `passi`, `src/passi/` | `passimaker`, `src/passimaker/` |
| Ordres | `passi`, `passi-nou`, `passi-render` | `passimaker`, `passimaker-nou`, `passimaker-render` |
| Extensió i format dels projectes | `.passi`, `"format": "passi"` | `.passimaker`, `"format": "passimaker"` |
| Error base | `PassiError` | `PassiMakerError` |
| Variable d'entorn de FFmpeg | `PASSI_FFMPEG` | `PASSIMAKER_FFMPEG` |
| Carpetes d'usuari (B12) | `%APPDATA%\Passi`, `%LOCALAPPDATA%\Passi` | `%APPDATA%\PassiMaker`, `%LOCALAPPDATA%\PassiMaker` |
| Repositori de GitHub | `Cunill/CLD` | sense canvis |

La paraula comuna "passi" ("passi de fotos") no canvia.

## Motiu

El nom recorda el Windows Movie Maker, que és el programa que es vol substituir. Es fa ara, amb només B0–B3 integrats
i cap bloc obert, perquè el canvi toca gairebé tots els fitxers i més endavant xocaria amb les branques obertes.

## Conseqüències

- Cap canvi de comportament: és només un canvi de nom.
- Els fitxers `.passi` deixen de reconèixer-se. No n'hi ha cap de real, perquè el programa encara no té interfície.
- Les sessions obertes abans del M01 es pensen que el codi és a `src/passi/`: s'han d'arxivar i començar de nou des del
  `main` actual.
- Les notes de sessió i les decisions anteriors conserven el que es va decidir, però els camins i els noms de mòdul
  s'han actualitzat perquè les sessions següents trobin els fitxers.

> **Actualització (M03, 21/10/2026):** l'extensió dels projectes ha passat de `.passimaker` a `.pmk`. Vegeu la decisió 0009.
