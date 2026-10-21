# 0009 · Extensió dels projectes: .pmk

- **Data:** 21/10/2026 · **Estat:** acceptada (petició de l'usuari) · **Aplicada a:** bloc de manteniment M03
- **Substitueix** l'extensió de la decisió 0006 (`.passimaker`).

## Decisió

| Element | Abans | Ara |
|---|---|---|
| Extensió dels projectes | `.passimaker` | **`.pmk`** |
| Còpia de recuperació | `recuperacio.passimaker` | `recuperacio.pmk` |
| Temporals (`.gitignore`) | `*.passimaker.*.tmp` | `*.pmk.*.tmp` |

No canvien el nom del programa (PassiMaker), el paquet (`passimaker`), les ordres ni el format intern del fitxer
(`"format": "passimaker"`).

## Motiu
Una extensió curta és més fàcil de llegir i d'escriure. Es fa ara, abans de la interfície, quan només hi ha fitxers
de prova.

## Conseqüències
- Els fitxers `.passimaker` deixen de reconèixer-se. Només n'hi havia de prova; es poden tornar a crear amb
  `passimaker-nou` o canviar-los l'extensió a mà, perquè el contingut és el mateix.
- No s'ha comprovat si altres programes fan servir `.pmk`. No afecta mentre PassiMaker no s'associï amb els fitxers
  (proposta P6, fora del pla).
