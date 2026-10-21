# 0008 · Exportació: velocitat, llavor dels projectes nous, so i fotos malmeses

- **Data:** 21/10/2026 · **Estat:** acceptada (decisions de l'usuari) · **Aplicada a:** bloc B9

## 1. Velocitat d'exportació
**Exportar pot trigar fins al triple de la durada del vídeo** al PC de referència (abans: "no més que la durada").
L'exportació és el procés que crea el fitxer MP4 i no té res a veure amb la reproducció, que continua essent en
temps real (§1.8).

Es manté l'encoder x264 amb `preset=medium` (§8 de `docs/CONTRACTES.md`): a la CI de Windows l'exportació triga
1,5 vegades la durada del vídeo. Es va descartar passar a `faster` o `veryfast` (més ràpids, qualitat pràcticament
igual; mesures a `docs/sessions/B09.md`). El B15 ho comprova al PC de referència.

## 2. Llavor dels projectes nous
`passimaker-nou` sense `--llavor` tria **una llavor a l'atzar** (0–999.999), la desa al projecte i la mostra. Cada
projecte nou té uns altres moviments; un projecte desat fa sempre el mateix vídeo (regla 5), i `--llavor N` el torna
a fer igual. La interfície (B10) ha de fer el mateix en crear un projecte. Es va descartar la llavor fixa (0).

## 3. So i fotos malmeses (confirmat tal com es va fer)
- Tots els vídeos porten **pista de so**, en silenci si el projecte no té música.
- Una foto **malmesa amb la capçalera bona** (que la importació accepta) surt **grisa** al vídeo, amb un avís; no
  atura l'exportació. La interfície (B11) avisarà abans d'exportar. Les fotos o cançons que **no es troben** sí que
  aturen l'exportació (§1.9).
