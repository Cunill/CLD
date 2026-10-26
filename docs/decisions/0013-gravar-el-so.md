# 0013 · Gravar el so de l'ordinador ("Grava el que sona")

- **Data:** 25/10/2026 · **Estat:** acceptada (decisions G1–G9 de l'usuari del 25/10/2026, annex `docs/PLA_GRAVACIO.md` §0)
- **Aplicada a:** blocs C07–C10 i el C06 conjunt (`docs/PLA_YOUTUBE.md` §4) · versió prevista **1.2.0**
- Especificació: `docs/ESPECIFICACIO.md` §1.7 ter. Contracte: `docs/CONTRACTES.md` §16 i §13.
  Arquitectura i riscos: annex `docs/PLA_GRAVACIO.md` §3 i §5.

## Què es decideix
Una funció nova, "Grava el que sona", per gravar en directe l'àudio que sona a l'ordinador (YouTube al navegador,
Spotify, qualsevol reproductor) i desar-lo en MP3 per fer-lo servir al passi.

| # | Tema | Decisió |
|---|---|---|
| G1 | Gravacions interrompudes | **No es desen mai.** Si la gravació s'acaba per qualsevol cosa que no sigui l'usuari ([■ Atura]) o l'aturada automàtica per silenci, s'esborra tot |
| G2 | Avís legal | **Cap avís** a la funció de gravar (ni casella ni diàleg) |
| G3 | Ones | **Ones del canal que s'està gravant**, en directe, un carril per canal |
| G4 | Versió | **YouTube i gravació junts a la 1.2.0**: un sol bloc d'empaquetat, el C06, que espera el C05 i el C10 |
| G5 | Durada màxima (30 min) | **Compta com a interrompuda**: s'esborra (G1). Un minut abans, el temps es posa en taronja |
| G6 | Orígens | **So de l'ordinador per defecte; micròfon i entrada de línia, opcionals**: surten a la llista i només es graven si l'usuari els tria |
| G7 | Format final | **MP3 de 192 kbps** (48 kHz estèreo), com YouTube |
| G8 | Ordre de treball | **C07 i C08 ara**, en paral·lel amb el YouTube |
| G9 | Incorporació | **Ara**, al pla vigent (`docs/PLA_YOUTUBE.md` §4) |

## 1. Com es grava
- **WASAPI loopback**, la manera estàndard de Windows de llegir el que sona per una sortida: sense controladors ni
  programes externs ("Stereo Mix", VB-Cable). La captura és dins del procés del programa.
- Es grava la sortida que fa servir Windows (per defecte) o la que triï l'usuari. El micròfon i l'entrada de línia
  surten a la mateixa llista, en un grup a part, i **no s'obren mai** si l'usuari no els tria (G6).
- Com a molt dos canals: un origen mono es grava en mono; un de 5.1 o més, en la seva mescla estèreo.
- El programa **no** intenta saltar cap protecció: si una aplicació fa servir el mode exclusiu o protegeix l'àudio, la
  gravació surt en silenci i el programa ho diu ("No s'ha gravat cap so…").

## 2. Xarxa
**Cap canvi respecte de la decisió 0012**: gravar no es connecta enlloc i funciona sense internet. `passimaker.recorder`
no importa cap mòdul de xarxa (hi ha una prova a `tests/unit/test_architecture.py`).

## 3. Sense avís (G2)
La finestra s'obre directament, sense diàleg ni casella. Gravar música amb drets d'autor té els mateixos límits que
descarregar-la, i Spotify, Netflix, Apple Music i altres prohibeixen gravar-ne el contingut a les seves condicions;
aquesta informació és només per a l'usuari (annex §1.1). La guia (C06) es limita a explicar com gravar.

## 4. Gravacions interrompudes (G1, G5)
- Mentre es grava, l'àudio va a un WAV temporal (32 bits flotants) escrit a mesura, a la carpeta temporal, amb el nom
  `passimaker_gravacio_*.wav`. No es guarda a la memòria (30 min ≈ 690 MB).
- **Es desa només** si s'acaba amb [■ Atura] o amb l'aturada automàtica per silenci. Llavors es retalla el silenci de
  l'inici i del final, l'usuari tria carpeta i nom, i es converteix a MP3.
- **Qualsevol altra causa** (sortida desconnectada o canviada, disc ple, error del so, la durada màxima de 30 min,
  [Descarta], tancar la finestra o el programa, un tancament inesperat) **esborra el WAV abans de mostrar el missatge**.
  No es pregunta mai si es vol conservar.
- En obrir el programa s'esborren les restes d'un tancament inesperat: la gravació no es recupera.

## 5. Ones per canal (G3)
Un carril per canal (E i D en estèreo, un de sol en mono), amb l'ona dels últims 10 s que es desplaça, en gris abans de
gravar i en vermell mentre es grava, i un mesurador de nivell per canal. En aturar, l'ona de tota la gravació amb els
silencis que es retallaran ombrejats. Les calcula el nucli al fil de captura (50 columnes per segon i canal) i la
interfície en recull les noves 30 cops per segon (regla 6). No s'hi pot clicar ni editar.

## 6. Format (G7)
MP3 de 192 kbps, 48 kHz estèreo, amb el mateix `passimaker.ffmpeg.convert_to_mp3` del C04: la regla 7 no canvia (el
nostre codi no crida `subprocess` fora de `passimaker.ffmpeg`).

## 6 bis. Volum i normalització (decisió de l'usuari del 26/10/2026, aplicada al C09)
- La prova del C08 ho ha confirmat: **el volum general de Windows i el de cada aplicació (Mesclador) sí que afecten la
  gravació**, perquè la captura (loopback) recull la mescla final, després de tots dos volums.
- Per això, **en desar es normalitza**: si el pic de la part conservada queda per sota de **−1 dBFS**, el programa puja
  el nivell de tota la gravació (el mateix guany per a tots dos canals) fins que el pic arriba a −1 dBFS; **mai més
  amunt**, per no saturar, i una gravació més forta no s'abaixa. Sense pèrdua audible: la captura és digital, en coma
  flotant de 32 bits i sense soroll analògic. Amb el micròfon, pujar el nivell també puja el soroll de fons.
- Valors: `defaults.RECORD_NORMALIZE_ENABLED = True` i `defaults.RECORD_NORMALIZE_PEAK_DBFS = -1.0`.
- El consell de la finestra canvia (C10): ja no diu que el volum no afecta la gravació (vegeu ESPECIFICACIO §1.7 ter).

## 7. Tecnologia de captura (decidida al C08: `soundcard`, G10)
| Opció | Notes |
|---|---|
| **A. sounddevice** (ja és una dependència) | Cap dependència nova. Cal confirmar que el PortAudio que porta exposa les sortides com a entrades WASAPI "[Loopback]". **Es prova primer.** |
| B. `soundcard` (BSD-3) | Loopback documentat; dependència nova. Si A no serveix. |
| C. `PyAudioWPatch` (Apache-2.0) | Fork de PyAudio; dependència nova amb binaris propis. |

**Resultat del C08** (25/10/2026, annex §3.1): **A no serveix** (sounddevice 0.5.6 porta PortAudio 19.7.0, sense
loopback). El C08 proposa **B, `soundcard` 0.4.6** (BSD-3, 44 KB, sense dependències noves), **aprovada per l'usuari el
25/10/2026 (G10)**; l'afegeix el bloc que la faci servir. El nucli amaga la tecnologia darrere del protocol
`CaptureBackend` (CONTRACTES §16), de manera que es pot canviar sense tocar el contracte públic.

## Conseqüències
- Amb `soundcard` (G10), el ZIP gairebé no creix (44 KB).
- La captura real necessita una targeta de so, i els servidors de la CI no en tenen: aquestes proves porten la marca
  `so` (excloses per defecte i, a més, omeses sense `PASSIMAKER_SO=1`) i les fa l'usuari al seu PC. La lògica (silenci,
  retall, WAV, durada màxima, disc ple, desconnexió) es prova a Linux i a la CI amb un substitut (C09).
- Canviar d'auriculars a mitja gravació la fa perdre sencera (G1): la guia ho avisa.
- Una gravació fluixa (volum baix) es puja en desar fins a −1 dBFS (§6 bis): el volum ja no ha de ser alt per força.
