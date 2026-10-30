# 0014 · "Ajustar a la música": durades fetes a mà fixes i 0,4–24 s

- **Data:** 30/10/2026 · **Estat:** acceptada (decisió 5 de `docs/PLA_1_3.md`, millora 7 de `docs/proves_usuari.md`)
- **Aplicada a:** bloc M07 · versió prevista **1.3.0**
- **Modifica** la decisió 0005 i la nota de la 0011 sobre "Ajustar a la música" (1–3 s).
- Especificació: `docs/ESPECIFICACIO.md` §1.7 ("Ajustar a la música").

| Què | Abans | Ara |
|---|---|---|
| Fotos amb la durada posada a mà | s'escalaven amb les altres i quedaven limitades a 1–3 s (una foto a 10 s acabava en 3 s) | **no es toquen**: se'n resta el total de la durada de la música |
| Rang de les fotos lliures | 1–3 s | **0,4–24 s**, el mateix que a mà (`defaults.FIT_TO_MUSIC_DURATION_RANGE = PHOTO_DURATION_RANGE`) |
| Llindar d'avís de "massa fotos" | 1 s (`FIT_TO_MUSIC_MIN_DURATION_WARNING_S`) | el mínim del rang, 0,4 s |
| Totes les fotos a mà | s'escalaven igualment | **no canvia res** i surt un avís amb un sol botó [D'acord] |
| Les fixes ja duren tant com la música o més | s'escalaven igualment | **no canvia res** i surt un avís amb un sol botó [D'acord] |

## Com
- `timeline.fit_to_music(durations, target_s, limits, fixed)`: `fixed[i]` marca una durada que no canvia. La resta es
  reparteix amb les proporcions i els límits de sempre. Si no hi ha res a ajustar, torna les durades iguals,
  `warning=True` i `FitResult.blocked` (`FitBlock.ALL_FIXED` o `FitBlock.FIXED_TOO_LONG`).
- `model.editing.fixed_durations`: un element és fix si té `duration_s` posat; només es mira aquest camp, de manera que
  qualsevol element amb durada pròpia (les fitxes negres del M08) també es manté, sense saber quina mena d'element és.
  Les fotos "per defecte" s'ajusten: totes valen el mateix, que passa a ser la durada per defecte del projecte i
  continuen sense marca de "durada pròpia".
- "Mantenir ajustat" fa servir les mateixes regles; si no hi ha res a ajustar, no fa res i no avisa.
- Avisos (`ui/duration_status.py`, `ui/dialogs.py`): `FitProblem.ALL_FIXED` i `FIXED_TOO_LONG` (`blocks`); en els altres
  dos, el temps per foto és el que queda de música després de les fixes.

## Fets a comprovar
- El moviment i la fosa ja suporten 0,4 s (decisió 0011; el B2 limita la fosa a la meitat de la foto més curta; prova
  nova a `tests/unit/timeline/test_fit.py`).
- Cap text de la interfície parla d'1–3 s.
