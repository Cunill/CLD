# 0011 · Durada de 0,4 a 24 s i "Nou moviment a l'atzar"

- **Data:** 24/10/2026 · **Estat:** acceptada (millores 2–4 de `docs/proves_usuari.md`, de la prova manual de l'usuari)
- **Modifica** la decisió 0005 (rang de la durada) i el §1.5 de l'especificació (botó de tornar a sortejar).

| Què | Abans | Ara |
|---|---|---|
| Durada per foto (general i de cada foto) | 1–3 s | **0,4–24 s** (passos de 0,1 s), `defaults.PHOTO_DURATION_RANGE` |
| "Ajustar a la música" | 1–3 s per foto | ~~igual, 1–3 s~~ **Canviat per la decisió 0014 (M07): 0,4–24 s, el mateix rang** (`defaults.FIT_TO_MUSIC_DURATION_RANGE`) |
| Botó de la foto | "🎲 Tornar a sortejar", desactivat si totes les fotos tenien el moviment fixat a mà | **"🎲 Nou moviment a l'atzar"**, sempre actiu; una foto amb el moviment fixat a mà torna a Automàtic |
| "Tornar a sortejar tots" | només les fotos automàtiques | igual |

- Una foto més curta que la fosa no necessita res més: la línia de temps ja limita la fosa a la meitat de la foto més
  curta (B2). El moviment conserva la velocitat màxima de la decisió 0005 (el moviment sencer en 1 s com a mínim).
- ~~"Ajustar a la música" es queda en 1–3 s per decisió de Claude.~~ Substituït per la decisió 0014 (29/10/2026): l'usuari ho va reclamar
  (millora 7 de `docs/proves_usuari.md`).
