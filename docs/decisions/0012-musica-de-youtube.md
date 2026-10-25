# 0012 · Música de YouTube

- **Data:** 25/10/2026 · **Estat:** acceptada (decisions de l'usuari del 25/10/2026, `docs/PLA_YOUTUBE.md` §0)
- **Aplicada a:** blocs C01–C06 (`docs/PLA_YOUTUBE.md` §4) · versió prevista **1.2.0**
- **Modifica** el Pas 0 del pla (xarxa: "totalment fora de línia") i les regles 7 i 10 del CLAUDE.md, tal com es diu a
  sota. Especificació: `docs/ESPECIFICACIO.md` §1.7 bis. Contracte: `docs/CONTRACTES.md` §15 i §8.

## Què es decideix
Una funció nova, "Música de YouTube", per cercar cançons a YouTube (o enganxar-ne l'enllaç) i descarregar-les en MP3
per afegir-les al passi.

| # | Tema | Decisió |
|---|---|---|
| 1 | Seguir endavant | **Sí, amb tot el pla** (C01–C06) |
| 2 | Aspectes legals | **Només l'avís**, sense filtre Creative Commons. L'avís té una **casella de conformitat obligatòria** i **cap connexió a internet abans d'acceptar-lo** |
| 3 | Format | **MP3 de 192 kbps** (48 kHz estèreo, la freqüència del mesclador) |
| 4 | Carpeta de destinació | **Es pregunta cada vegada** |
| 5 | Escoltar abans de descarregar | **Botó "Obre a YouTube"**, que obre el navegador (el programa no s'hi connecta) |
| 6 | PR del pla | **No**: el pla es va quedar a la seva branca fins al C01 (ara és a `docs/PLA_YOUTUBE.md`) |
| 7 | Validesa de la conformitat | **Una vegada per cada sessió del programa**: no es desa enlloc i es torna a demanar cada vegada que s'obre PassiMaker |
| 8 | Començar el C01 | **En una sessió nova** |

## 1. Xarxa
- Abans: el programa era totalment fora de línia.
- Ara: es connecta a internet **només** des de la finestra "Música de YouTube" i **mai abans d'acceptar l'avís**. La
  resta del programa continua funcionant igual sense xarxa.
- Com es garanteix (ESPECIFICACIO §1.7 bis):
  1. Una sola porta d'entrada: tota la xarxa passa per `passimaker.youtube`. Les funcions que es poden connectar reben
     un `ConsentToken`, que només crea `consent.grant()` en acceptar l'avís; sense testimoni vàlid llancen
     `YoutubeConsentError` abans de fer res.
  2. `import yt_dlp` només dins de les funcions, mai en carregar el mòdul ni des de `ui/`.
  3. La finestra no fa res sola en obrir-se (cap cerca, miniatura ni comprovació de versió).
  4. Proves: una prova estàtica (cap mòdul fora de `passimaker.youtube` importa `yt_dlp`, `urllib.request`,
     `http.client` ni `socket`; feta al C01) i proves amb la xarxa bloquejada (C03 i C05).

## 2. Dependències (regla 10)
- **yt-dlp** (llicència Unlicense, domini públic), com a biblioteca Python. Entra al C02, quan s'hagi comprovat que
  funciona des del ZIP a Windows; el C01 no afegeix cap dependència.
- **Deno** (entorn JavaScript que yt-dlp necessita per a YouTube des de finals del 2025): **a confirmar al C02**, amb
  com s'empaqueta i quant fa créixer el ZIP (~40 MB comprimits).
- Cerca sense clau d'API (`ytsearchN:` de yt-dlp). La YouTube Data API v3 es descarta: demana una clau de Google i té
  quota diària.
- Miniatures amb `urllib` (biblioteca estàndard), petites (320 px) i només a la memòria.

## 3. Processos (regla 7)
- El nostre codi continua sense cridar `subprocess` fora de `passimaker.ffmpeg`: yt-dlp es fa servir com a biblioteca
  i **no** fa la conversió; baixa l'àudio original i el converteix `passimaker.ffmpeg.convert_to_mp3`.
- yt-dlp sí que llança Deno per dins. Al C02 es comprova que no s'obre cap finestra de consola des del programa sense
  consola; si cal, s'ajusta la configuració (o es descarta Deno) i la prova de la regla 7.

## 4. Aspectes legals
- Les condicions de YouTube no permeten descarregar contingut si YouTube no ofereix un botó de descàrrega, i la
  majoria de cançons tenen drets d'autor (un vídeo publicat es pot silenciar o bloquejar).
- Mesures: l'avís amb la casella de conformitat obligatòria (decisions 2 i 7) i, a la guia (C06), fonts de música
  lliure: Biblioteca d'àudio de YouTube, Free Music Archive i Pixabay Music. Sense filtre Creative Commons.
- **Declinació de responsabilitat** (petició de l'usuari en revisar el C01, 25/10/2026): l'avís diu explícitament
  "PassiMaker i els seus autors declinen qualsevol responsabilitat derivada de l'ús de la música descarregada, i en particular per qualsevol infracció dels drets d'autor o de les condicions de YouTube." Text complet de l'avís: ESPECIFICACIO §1.7 bis.

## 5. Conformitat per sessió del programa
- La casella no està mai marcada d'entrada i [Accepta i continua] està desactivat fins que es marca.
- La conformitat es guarda **només a la memòria** del procés (`passimaker.youtube.consent`): ni `QSettings`, ni
  registre, ni el `.pmk`. La comparteixen totes les finestres obertes; en tancar el programa es perd.
- Es pot retirar abans d'hora ("Retira la conformitat"): tanca la finestra de YouTube i cancel·la les descàrregues.

## 6. Manteniment
YouTube canvia sovint i trenca yt-dlp (diversos cops l'any):
1. Un flux setmanal de GitHub Actions comprova si hi ha una versió nova de yt-dlp i obre una PR que l'actualitza a
   `uv.lock` (la CI la prova com qualsevol altra).
2. Quan l'usuari vegi "YouTube ha canviat…", en una sessió al núvol es fusiona aquesta PR i es publica una versió de
   pedaç (1.2.1, 1.2.2…) amb `publicar.yml`. L'usuari només baixa el ZIP nou.
3. Descartat: que el programa actualitzi yt-dlp sol des d'internet (executaria codi baixat sense revisar i
   complicaria el ZIP portable).

## Conseqüències
- El ZIP creix ~5 MB (yt-dlp) i, si cal Deno, ~40 MB més (es mesura al C02).
- La funció pot deixar de funcionar fins que es publica una versió nova; la resta del programa no se'n ressent.
- Les proves amb xarxa real porten la marca `xarxa` (C03): excloses per defecte i a la CI; les fa l'usuari al seu PC.
