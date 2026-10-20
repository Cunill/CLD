# 0004 · Moviments més ràpids (fita F1)

- **Data:** 20/10/2026 · **Estat:** acceptada (petició de l'usuari després de veure el vídeo de mostra: "augmenta la velocitat")
- **Decisió:** totes les intensitats, un 50 % més d'amplitud i de velocitat màxima.

| | Suau | Mitjana (per defecte) | Marcada |
|---|---|---|---|
| Zoom per foto | 6 → 9 % | 12 → 18 % | 20 → 28 % |
| Desplaçament per foto | 4 → 6 % | 8 → 12 % | 13 → 18 % |
| Velocitat màxima del zoom | 2 → 3 %/s | 3,5 → 5 %/s | 5 → 7,5 %/s |
| Velocitat màxima del desplaçament | 1,5 → 2,5 %/s | 2,5 → 4 %/s | 4 → 6 %/s |

- **On:** `src/passi/motion/params.py` (`INTENSITY_PARAMS`) i ESPECIFICACIO §1.5.
- **Nota:** en fotos de menys de ~3.000 px d'amplada el zoom continua limitat per `MAX_UPSCALE` (no ampliar més d'1,5×).
