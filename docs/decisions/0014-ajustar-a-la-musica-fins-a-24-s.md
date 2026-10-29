# 0014 · "Ajustar a la música" fins a 24 s per foto

- **Data:** 29/10/2026 · **Estat:** acceptada (petició de l'usuari durant la prova del ZIP 1.2.0, pas 7)
- **Modifica** la decisió 0011 (que mantenia "Ajustar a la música" en 1–3 s) i el §1.7 de l'especificació.

| Què | Abans | Ara |
|---|---|---|
| Durada que "Ajustar a la música" pot donar a cada foto | 1–3 s | **1–24 s** (`defaults.FIT_TO_MUSIC_DURATION_RANGE`), el mateix màxim que la durada posada a mà (decisió 0011) |
| Avís "La música és massa llarga per a aquestes fotos" | si calien més de 3 s per foto | si calen més de 24 s per foto |

- **Per què:** a la prova del ZIP 1.2.0 (29/10/2026), amb quatre cançons i poques fotos, cada foto quedava en 3 s i
  sobraven uns 6 minuts de música. Amb cançons senceres (YouTube i gravacions), el límit de 3 s es queda curt.
- El mínim continua sent 1 s (més curt maregen). Les proporcions entre fotos es mantenen com abans.
