# 0005 · Fotos curtes, foses curtes i moviment ajustable

- **Data:** 20/10/2026 · **Estat:** acceptada (petició de l'usuari durant la revisió de la fita F1)
- **Substitueix** els valors de la decisió 0004.

| Paràmetre | Abans | Ara | Rang ajustable |
|---|---|---|---|
| Durada per foto | 5 s | **2 s** | 1–3 s |
| Fosa encadenada | 1,5 s | **1 s** | 0,5–1,5 s |
| Zoom per foto | 18 % (mitjana) | **9 %** (suau 6 %, marcada 12 %) | 0–20 % |
| Desplaçament per foto | 12 % (mitjana) | **9 %** (suau 6 %, marcada 12 %) | 0–20 % |

- "Tots aquests paràmetres, ajustables": durada (general i per foto) i fosa ja ho eren; el zoom i el
  desplaçament passen a ser dos valors del projecte (`Project.zoom_amount`, `Project.pan_amount`) que
  l'usuari pot ajustar a "Avançat". La intensitat Suau / Mitjana / Marcada és una preselecció d'aquests dos valors.
- Les fotos amb fons difuminat fan el mateix zoom que les altres (abans, el 60 %), perquè el moviment quedi dins el 6–12 %.
- Velocitat màxima: el moviment sencer en 1 s com a mínim (només afecta fotos visibles menys d'1 s).
- L'ajust a la música queda limitat a 1–3 s per foto.
- On: `passimaker.model.defaults` (valors i rangs), `passimaker.model.types.Project`, `passimaker.motion.params`
  (`INTENSITY_PRESETS`, `MotionAmounts`), ESPECIFICACIO §1.3–1.7.
