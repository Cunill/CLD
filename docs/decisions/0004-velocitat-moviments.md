# 0004 · Moviments més ràpids (fita F1)

- **Data:** 20/10/2026 · **Estat:** substituïda per la 0005 (petició de l'usuari després de veure el vídeo de mostra: "augmenta la velocitat")
- **Decisió:** totes les intensitats, un 50 % més d'amplitud i de velocitat màxima.

Valors per a una foto amb la durada per defecte (visible 6,5 s):

| | Suau | Mitjana (per defecte) | Marcada |
|---|---|---|---|
| Zoom en 6,5 s | 6 → 9 % | 12 → 18 % | 20 → 28 % |
| → velocitat del zoom | 0,9 → 1,4 %/s | 1,8 → 2,8 %/s | 3,1 → 4,3 %/s |
| Desplaçament en 6,5 s | 4 → 6 % | 8 → 12 % | 13 → 18 % |
| → velocitat del desplaçament | 0,6 → 0,9 %/s | 1,2 → 1,8 %/s | 2,0 → 2,8 %/s |
| Velocitat màxima del zoom | 2 → 3 %/s | 3,5 → 5 %/s | 5 → 7,5 %/s |
| Velocitat màxima del desplaçament | 1,5 → 2,5 %/s | 2,5 → 4 %/s | 4 → 6 %/s |

- **On:** `src/passimaker/motion/params.py` (`INTENSITY_PARAMS`) i ESPECIFICACIO §1.5.
- **Nota:** en fotos de menys de ~3.000 px d'amplada el zoom continua limitat per `MAX_UPSCALE` (no ampliar més d'1,5×).
