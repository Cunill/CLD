# PassiMaker: especificació funcional

> Extreta del Pas 1 de `docs/PLA.md` (pla aprovat el 20/10/2026). És la referència de comportament i
> de valors per defecte per a tots els blocs. Els números de secció (§1.x) són els mateixos que al pla.
> Les decisions D1–D11 del Pas 5 s'han acceptat tal com estaven proposades (vegeu `docs/decisions/`):
> les propostes P1 (desfer/refer) i P2 (girar una foto 90°) formen part de l'abast.

### 1.0 Principis d'ús

- El camí normal té tres passos: **Fotos → Música → Exportar**. Tota la resta té valors per defecte pensats perquè el resultat quedi bé sense tocar res.
- Les opcions d'una foto o d'una cançó només apareixen quan se selecciona (panell de propietats). Les opcions poc habituals queden plegades a "Avançat".
- La finestra no es bloqueja mai mentre el programa treballa (importar, fer miniatures, analitzar la música). L'única excepció és l'exportació, que mostra un diàleg amb progrés.
- No es modifica mai cap fitxer original.

**Recorregut de referència (objectiu: menys de 5 minuts)**

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Obre `PassiMaker.exe` | Pantalla buida amb el missatge "Arrossega aquí les fotos o la carpeta" i el botó [Tria fotos…] |
| 2 | Arrossega una carpeta amb 60 fotos | Les miniatures apareixen a poc a poc, ordenades per data. Cada foto ja té durada, encaix i moviment. |
| 3 | [+ Música] i tria 2 cançons | Les cançons surten a la franja de música. La barra d'estat avisa si la música i les fotos no duren el mateix. |
| 4 | [Ajustar a la música] (opcional) | Les durades de les fotos canvien perquè el passi acabi alhora que la música. |
| 5 | ▶ | Previsualització en temps real amb so |
| 6 | [Exportar vídeo] → nom | Barra de progrés. En acabar: [Obrir el vídeo] / [Mostrar a la carpeta] |

**Disposició de la finestra**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [+ Fotos] [+ Música] [Ajustar a la música]  Format:[Horitzontal▾]  [Exportar vídeo] │
├──────────────────────────────────┬───────────────────────────────────────────┤
│  PREVISUALITZACIÓ                │  STORYBOARD (graella de miniatures)       │
│                                  │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐            │
│                                  │  │ 1│ │ 2│ │ 3│ │ 4│ │ 5│ │ 6│            │
│  |◀  ▶  ▶|   01:12 / 04:30       │  5,0s 5,0s 7,0s● 5,0s 5,0s 5,0s           │
│  ────────●───────────────        │  ...                                      │
├──────────────────────────────────┤                                           │
│  PROPIETATS (projecte / foto / cançó seleccionada)                           │
├──────────────────────────────────┴───────────────────────────────────────────┤
│  MÚSICA:  [1. Cançó A  3:12 ◢◣]  [2. Cançó B  2:40 ◢◣]   [+]                 │
├──────────────────────────────────────────────────────────────────────────────┤
│  124 fotos · 4:30  ·  Música 5:52  ⚠ La música dura 1:22 més [Ajustar]        │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Valors per defecte globals**

| Paràmetre | Per defecte | Rang |
|---|---|---|
| Durada per foto | 2,0 s | 1–3 s (en passos de 0,1 s) |
| Fosa encadenada | 1,0 s | 0,5–1,5 s |
| Fosa des de negre a l'inici | 1,0 s | 0–5 s (Avançat) |
| Fosa a negre al final | 2,0 s | 0–5 s (Avançat) |
| Moviment de càmera | Activat, automàtic | — |
| Intensitat del moviment | Mitjana | Suau / Mitjana / Marcada (preselecció dels dos valors següents) |
| Zoom per foto | 9 % | 0–20 % (Avançat; suau 6 %, mitjana 9 %, marcada 12 %) |
| Desplaçament per foto | 9 % | 0–20 % (Avançat; suau 6 %, mitjana 9 %, marcada 12 %) |
| Encaix | Automàtic | Automàtic / Omplir / Fons difuminat / Fons negre |
| Fosa d'entrada de cada cançó | Activada, 1,0 s | 0–10 s (en passos de 0,5 s) |
| Fosa de sortida de cada cançó | Activada, 3,0 s | 0–10 s |
| Fosa final si la música és més llarga | 3,0 s | Fixa |
| Volum general | 100 % | 0–100 % |
| Volum de cada cançó | 100 % | 0–150 % |
| Anivellament entre cançons | Activat (−16 LUFS) | Sí / no (Avançat) |
| Format | Horitzontal 1920×1080, 30 fps | Horitzontal / Vertical 1080×1920 |
| Codificació | H.264 High, CRF 18 · AAC 192 kbps, 48 kHz | Fixa |

### 1.1 Importar fotos

**Comportament**
- Es poden afegir fotos de tres maneres: arrossegant fitxers o carpetes a qualsevol lloc de la finestra, amb el botó [+ Fotos] (selecció múltiple) o amb el menú "Afegir una carpeta…".
- Si s'afegeix una carpeta, s'importen les fotos que conté. Si té subcarpetes amb fotos, el programa pregunta un sol cop: "Vols incloure també les subcarpetes (N fotos més)?".
- Formats: JPG/JPEG, PNG i HEIC/HEIF. L'HEIC és viable fora de línia amb una llibreria inclosa al programa. A més, i sense cost addicional, també BMP, TIFF, WebP i GIF (primer fotograma). Els fitxers RAW de càmera no s'admeten, i el programa ho diu clarament.
- L'orientació EXIF (els 8 valors) s'aplica sempre: a les miniatures, a la previsualització i al vídeo.
- Els perfils de color (Display P3 dels iPhone, Adobe RGB) es converteixen a sRGB perquè els colors no surtin apagats.
- Ordre:
  - Si com a mínim el 80 % de les fotos tenen data de captura EXIF, s'ordenen per data. Les que no en tenen, per la data del fitxer.
  - Si no, per nom en ordre natural ("IMG_2" abans que "IMG_10").
  - Les fotos noves van al final, o al punt on es deixen anar si s'arrosseguen sobre el storyboard.
  - El menú "Ordenar per data / per nom" les torna a ordenar totes.
- En importar-la, cada foto rep la durada general, l'encaix automàtic i un moviment sortejat.
- La importació és progressiva i es pot cancel·lar.

**Casos límit**

| Cas | Comportament |
|---|---|
| Fitxer corrupte o format no admès | No s'afegeix. Al final surt un resum: "2 fitxers no s'han pogut afegir [Veure quins]". |
| Foto que ja és al projecte | Una sola pregunta per a tota la importació: "3 fotos ja hi són. Les vols afegir igualment?" (per defecte, no). |
| Foto petita (costat curt < 540 px en 1080p) | S'importa amb una icona de "baixa resolució". El moviment es redueix o s'anul·la perquè no es vegi pixelada. |
| Foto minúscula (< 64 px) | No s'afegeix, amb un missatge. |
| Foto enorme (50–100 MP) | S'afegeix. Només es descodifica a la mida necessària. |
| Panoràmica (p. ex. 3:1) o vertical | Encaix automàtic amb fons difuminat (vegeu 1.6). |
| PNG amb transparència | Es compon sobre negre. |
| CMYK, 16 bits, escala de grisos | Es converteixen a RGB de 8 bits. |
| Més de 1.000 fotos | S'admeten, amb l'avís "Més de 1.000 fotos: el programa pot anar més lent". |
| Fitxers de OneDrive "només en línia" | Es descarreguen en llegir-los. La importació mostra el progrés i es pot cancel·lar. |

**Com ho veu l'usuari:** les miniatures apareixen una darrere l'altra, amb el comptador "Important 340 de 1.000…" i un botó [Cancel·lar].

### 1.2 Storyboard

**Comportament**
- Les miniatures formen una graella que s'adapta a l'amplada (com al Movie Maker 2012), en l'ordre del passi. Sota cada miniatura hi ha el número d'ordre i la durada ("2,0 s"). Unes icones petites indiquen el tipus de moviment, si té una durada personalitzada, si és de baixa resolució o si no es troba el fitxer.
- Selecció simple, múltiple (Ctrl, Maj) i de totes (Ctrl+A).
- Per reordenar, s'arrosseguen una o diverses fotos. Una línia vertical indica on aniran. Amb el teclat: Ctrl+← i Ctrl+→.
- Per eliminar: tecla Supr, botó o menú contextual. Només es demana confirmació si se n'eliminen 5 o més, perquè no hi ha "desfer" (vegeu la proposta P1).
- Per duplicar: Ctrl+D o menú contextual. La còpia va just després de l'original, amb la mateixa durada i el mateix encaix però amb un moviment nou i diferent.
- Mida de les miniatures: petita, mitjana o gran.
- En fer clic sobre una miniatura, la previsualització salta a l'inici d'aquella foto i el panell de propietats en mostra els ajustos.

**Casos límit:**
- 0 fotos: estat buit amb instruccions.
- 1 foto: el passi és vàlid.
- 1.000 fotos: el desplaçament és fluid (només es dibuixen les miniatures visibles) i les miniatures es carreguen començant per les que es veuen.
- Foto no trobada: miniatura grisa amb una icona i l'opció "Cercar…".

### 1.3 Durada per foto

- La durada general és de 2,0 s (de 1 a 3 s, en passos de 0,1 s). Si es canvia, afecta totes les fotos que no tenen una durada personalitzada.
- Per a una foto, o per a les fotos seleccionades, hi ha el camp "Durada" al panell de propietats. Si es modifica, la foto queda marcada com a personalitzada (amb una icona) i apareix el botó [Restablir a la general].
- La durada és l'espai que ocupa la foto a la línia de temps, des de la meitat de la fosa anterior fins a la meitat de la següent. Així, la durada total del passi és exactament la suma de les durades de totes les fotos.
- La barra d'estat mostra sempre el total ("124 fotos · 10:20").
- Cas límit: si una foto dura menys que dues foses, la fosa d'aquella foto s'escurça automàticament (vegeu 1.4).

### 1.4 Transició de fosa

- Hi ha una fosa encadenada entre cada parella de fotos consecutives, amb una durada global d'1,0 s (de 0,5 a 1,5 s). No hi ha cap altre tipus de transició.
- A l'inici hi ha una fosa des de negre (1,0 s) i al final una fosa cap a negre (2,0 s). Totes dues es poden ajustar a "Avançat" (de 0 a 5 s).
- La fosa queda centrada en el canvi de foto: comença 0,5 s abans i acaba 0,5 s després. Durant la fosa, les dues fotos continuen movent-se; el moviment no s'atura mai.
- Regla de seguretat: la fosa entre dues fotos no pot durar més de la meitat de la més curta. Així, cada foto té un moment en què es veu sencera.
- Casos límit:
  - 1 sola foto: només hi ha la fosa d'entrada i la de sortida.
  - Passi més curt que les foses d'inici i final sumades: les dues foses s'escurcen proporcionalment.

### 1.5 Moviment de càmera (efecte Ken Burns)

**Tipus de moviment**

| Tipus | Descripció |
|---|---|
| Apropar | Zoom endavant cap a un punt proper al centre, una mica més amunt, que és on solen ser les cares |
| Allunyar | Zoom enrere des d'un punt proper al centre |
| Desplaçar ← → ↑ ↓ | Desplaçament horitzontal o vertical amb un zoom fix lleuger, que deixa marge per moure's |
| Combinat | Zoom (endavant o enrere) amb un desplaçament suau en diagonal |
| Cap | Foto estàtica |

**Quantitat de moviment** (decisió 0005, 20/10/2026: ajustable per l'usuari)

Cada foto fa tot el seu moviment durant el temps que és visible. Amb els valors per defecte (2 s per
foto i fosa d'1 s) són **3 s** (la primera i l'última foto, 2,5 s).

| | Suau | Mitjana (per defecte) | Marcada | Ajust manual (Avançat) |
|---|---|---|---|---|
| Zoom per foto | 6 % | 9 % | 12 % | 0–20 % |
| Desplaçament per foto (en % del costat visible) | 6 % | 9 % | 12 % | 0–20 % |
| → velocitat amb fotos de 2 s (3 s visibles) | 2 %/s | 3 %/s | 4 %/s | |

- El selector "Intensitat" (Suau / Mitjana / Marcada) posa els dos valors alhora. A "Avançat" es poden
  ajustar per separat; si no coincideixen amb cap preselecció, el selector mostra "Personalitzada".
- Amb 0 % en tots dos valors, les fotos queden quietes (equivalent a desactivar el moviment).
- Exemple (mitjana): en una foto de 2 s amb zoom, la imatge creix un 9 % en 3 s, és a dir, un 3 % cada segon.
- Una foto visible menys d'1 s (cas límit) fa només la part proporcional del moviment.

- El moviment és lineal i continu durant tot el temps que la foto és visible, foses incloses, sense acceleracions ni aturades. El zoom es calcula perquè la velocitat aparent sigui constant.
- Si una foto és molt curta, el moviment es redueix perquè no sigui brusc. Si és molt llarga, simplement va més lent.

**Mode automàtic aleatori (per defecte)**
- Probabilitats de partida: Apropar 30 %, Allunyar 25 %, Desplaçar 25 %, Combinat 20 %.
- Regles d'equilibri:
  1. No es repeteix mai el mateix tipus i la mateixa direcció en dues fotos seguides.
  2. No hi pot haver més de 2 fotos seguides de la mateixa família (zoom o desplaçament).
  3. En qualsevol grup de 6 fotos consecutives, la diferència entre fotos que s'apropen i fotos que s'allunyen no supera 2.
  4. La primera foto s'apropa suaument i l'última s'allunya, que és l'inici i el final clàssics.
  5. Els desplaçaments van, sempre que es pot, en la direcció en què la foto té més marge (per exemple, en vertical per a una foto 4:3 dins un vídeo 16:9).
- Els resultats són reproduïbles. El projecte desa una llavor i cada foto un comptador de sorteigs, de manera que el mateix projecte dona sempre el mateix vídeo. El moviment resultant també es desa al projecte, i per això afegir o reordenar fotos no canvia el moviment de les altres.
- Reordenar no torna a sortejar els moviments, perquè els que ja s'han vist no canviïn. Si en reordenar queden dos moviments iguals seguits, no es corregeix sol; [Tornar a sortejar tots] ho arregla.

**Control manual**
- Al panell de la foto hi ha "Moviment: [Automàtic ▾]", amb les opcions Apropar, Allunyar, Desplaçar (4 direccions), Combinat i Cap. Si se'n tria una, el moviment queda fixat (mode manual).
- El botó [🎲 Tornar a sortejar] torna a sortejar la foto o les fotos seleccionades.
- [Tornar a sortejar tots] torna a sortejar totes les fotos en mode automàtic i respecta les que s'han fixat a mà. Al menú hi ha [Restablir tots a automàtic].
- També hi ha un interruptor global "Moviment de càmera" (activat per defecte) i el selector d'intensitat.

**Garantia que no es veuran vores**
- La part que es veu és sempre una finestra amb la proporció del vídeo que queda tota dins la imatge, o dins del llenç amb fons difuminat. Es comprova a l'inici, al final i en els instants intermedis. Si un moviment no ho compleix, s'ajusta abans d'acceptar-lo.
- Fotos de baixa resolució: el zoom es limita perquè la foto no s'ampliï més d'1,5 vegades la seva resolució original. Si la foto fa menys del 50 % de la resolució del vídeo, el moviment passa automàticament a "Cap".

### 1.6 Fotos verticals i proporcions diferents

**Proposta: encaix automàtic mixt**
- **Omplir** si la proporció de la foto s'acosta a la del vídeo (relació entre 0,70 i 1,43, que inclou 4:3, 3:2, 16:9 i 16:10). Es retalla el mínim possible i la part retallada serveix de marge per al moviment.
- **Encaixar amb fons difuminat** si la proporció és molt diferent: fotos verticals en un vídeo horitzontal, horitzontals en un vídeo vertical, quadrades i panoràmiques. La foto es veu sencera i el fons és la mateixa foto ampliada, molt desenfocada i enfosquida un 30 %. El moviment s'aplica al conjunt (foto i fons), només de tipus zoom.
- **Per què:**
  - Retallar una foto vertical per a un vídeo horitzontal en fa perdre més del 60 % (per exemple, caps tallats).
  - Les franges negres semblen justament les zones buides que volem evitar.
  - El fons difuminat és el que es fa servir avui a mòbils i televisió.
- Per a cada foto es pot forçar una opció: Automàtic, Omplir, Encaixar amb fons difuminat o Encaixar amb fons negre.
- En format vertical (9:16) s'apliquen les mateixes regles, a l'inrevés.
- Casos límit:
  - Panoràmica 4:1 en mode "Omplir": es veu la franja central, amb un desplaçament lateral limitat per la velocitat màxima.
  - Foto quadrada en un vídeo horitzontal: fons difuminat.
  - Foto vertical 3:4 en un vídeo vertical: Omplir.

### 1.7 Música

**Comportament**
- Sota el storyboard hi ha la franja "Música", amb les cançons en ordre: nom, durada real (després del retall) i indicadors de fosa. Les cançons s'afegeixen amb [+ Música] o arrossegant fitxers d'àudio a la finestra. Es poden eliminar i reordenar arrossegant-les.
- Formats: MP3, WAV, M4A/AAC, FLAC, OGG, WMA i OPUS.
- Les cançons sonen una darrere l'altra des del principi del vídeo, sense trepitjar-se.
- Ajustos de cada cançó (panell de propietats):
  - Fosa d'entrada: ☑ activada, 1,0 s (de 0 a 10 s, en passos de 0,5 s).
  - Fosa de sortida: ☑ activada, 3,0 s (de 0 a 10 s).
  - Retall: "Comença a" i "Acaba a", amb una barra que mostra la forma d'ona i té dues nanses, i un botó per escoltar el tros triat.
  - Volum: 100 % (de 0 a 150 %).
- Volum general: 100 % (de 0 a 100 %).
- Anivellament automàtic (activat per defecte, a "Avançat"): iguala el volum percebut de totes les cançons (−16 LUFS) perquè no n'hi hagi cap de molt més forta que les altres.
- Encara que les foses estiguin desactivades, cada tall té una fosa de 10 ms, que no se sent però evita els espetecs.
- Les foses segueixen una corba logarítmica, que a l'oïda sona més natural que una de lineal.

**Ajustar a la música**
- El botó [Ajustar a la música] torna a calcular les durades perquè el passi duri exactament el mateix que la música (la suma de les cançons, ja retallades). Es mantenen les proporcions: una foto de 10 s continua durant el doble que una de 5 s.
- Cada foto ha de durar entre 1 i 3 s. Si caldria menys d'1 s per foto, surt l'avís "Hi ha massa fotos per a aquesta música: cada foto duraria 0,6 s. Afegeix música o treu fotos."; si en caldria més de 3 s, "La música és massa llarga per a aquestes fotos: afegeix-ne o retalla la música." En tots dos casos, [Aplicar igualment] (amb el límit d'1 o 3 s) i [Cancel·lar].
- Casella "Mantenir ajustat" (desactivada per defecte): si s'activa, el passi es torna a ajustar sol cada vegada que s'afegeixen fotos o cançons.

**Quan la música i les fotos no duren el mateix**

| Situació | Comportament per defecte | Com ho veu l'usuari |
|---|---|---|
| La música dura més que el passi | La música es talla amb una fosa de volum de 3 s que acaba just amb la fosa a negre del vídeo | Avís discret a la barra d'estat: "La música dura 1:22 més. [Ajustar a la música]" |
| La música dura menys que el passi | Després de l'última cançó (amb la seva fosa de sortida) hi ha silenci | "La música s'acaba 0:45 abans. [Ajustar a la música]" |
| No hi ha música | Vídeo amb una pista d'àudio en silenci, perquè sigui més compatible amb els televisors | — |

**Casos límit:**
- Cançó corrupta o protegida (DRM): es marca en vermell, amb un missatge, i no entra a la mescla.
- Cançó més curta que les seves dues foses: cada fosa es redueix al 40 % de la durada de la cançó.
- Retall amb l'inici després del final: no es permet.
- Àudio mono, 5.1 o amb freqüències de mostreig diferents: es converteix a estèreo de 48 kHz.
- Música de més d'una hora: s'admet.

### 1.8 Previsualització

- Panell amb la imatge del passi i aquests controls: ▶/❚❚ (barra espaiadora), foto anterior i següent (← →), barra de temps clicable i temps actual / total.
- Es reprodueix en temps real i amb so, a resolució reduïda (fins a 960×540, o 540×960 en vertical). La imatge és exactament la mateixa que s'exportarà, perquè la fa el mateix motor.
- En fer clic sobre una miniatura, la previsualització salta a l'inici d'aquella foto (i, si s'estava reproduint, continua des d'allà).
- Qualsevol canvi (durada, moviment, encaix, música) es veu a l'instant. En pausa, la imatge es torna a dibuixar.
- Casos límit:
  - Ordinador lent: se salten imatges, però el so no es talla mai i la imatge no queda endarrerida.
  - 1.000 fotos: la reproducció comença des de qualsevol punt en menys de mig segon.
  - Projecte sense música: es fa servir un rellotge intern.

### 1.9 Exportar

- [Exportar vídeo] obre el diàleg de desar, amb el nom del projecte i la carpeta Vídeos ja proposats. No hi ha cap altra opció: el format (horitzontal o vertical) és el del projecte.
- Vídeo: MP4, H.264 perfil High, 1920×1080 o 1080×1920, 30 fps, qualitat alta constant (CRF 18), espai de color BT.709.
- Àudio: AAC a 192 kbps, 48 kHz, estèreo.
- El fitxer es pot començar a reproduir abans d'haver-se descarregat del tot (opció faststart).
- Diàleg de progrés: barra, percentatge, temps restant estimat i [Cancel·lar]. Si es cancel·la, l'exportació s'atura en menys de 2 s i el fitxer a mig fer s'esborra.
- Durant l'exportació no es pot editar (finestra modal) i l'ordinador no entra en repòs.
- En acabar, surt "Vídeo desat (4:30, 245 MB)" amb [Obrir el vídeo] i [Mostrar a la carpeta].
- Objectiu de velocitat: al PC de referència, exportar no ha de trigar més que la durada del vídeo.
- Casos límit:
  - Disc ple: abans de començar es comprova si hi ha prou espai (estimat). Si el disc s'omple durant l'exportació, surt un missatge clar i s'esborra el fitxer a mig fer.
  - Ja existeix un fitxer amb aquest nom: es demana si es vol substituir.
  - Fotos o cançons que no es troben: no s'exporta i se'n mostra la llista.
  - Rutes amb accents o molt llargues: s'admeten.
  - El vídeo s'escriu amb un nom provisional i es reanomena en acabar.

### 1.10 Desar i obrir projectes

- El projecte es desa en un fitxer `.passimaker` (text estructurat i llegible) amb tots els ajustos i les rutes de les fotos i les cançons. Els fitxers originals no es copien.
- Desar (Ctrl+S), Desar com a…, Obrir (Ctrl+O) i llista de projectes recents a la pantalla inicial. El títol de la finestra mostra el nom del projecte, amb un asterisc si hi ha canvis sense desar. En tancar, el programa pregunta si es volen desar.
- Cada 2 minuts es fa una còpia de recuperació, fora de la carpeta del projecte. Si el programa es tanca de cop, en tornar-lo a obrir ofereix recuperar el projecte.
- Les rutes es desen de dues maneres: relatives al fitxer del projecte i absolutes. Si es mou tota la carpeta (projecte i fotos), el projecte continua funcionant.
- Fitxers que no es troben: "No es troben 12 fitxers. [Cercar en una carpeta…]". El programa els torna a enllaçar automàticament pel nom.
- El format porta un número de versió. Si s'obre un projecte fet amb una versió més nova del programa, surt un missatge clar en lloc d'una fallada.
- Casos límit:
  - Fitxer de projecte malmès: surt un missatge i, si hi ha còpia de recuperació, s'ofereix.
  - Projecte obert des d'una memòria USB amb una altra lletra d'unitat: funciona gràcies a les rutes relatives.

### 1.11 Format del vídeo

- Ajust del projecte "Format: Horitzontal 16:9 / Vertical 9:16" (per defecte, horitzontal), a la barra d'eines.
- Si es canvia, el programa torna a calcular l'encaix automàtic i el moviment de totes les fotos, mantenint el tipus de moviment triat. La previsualització canvia de forma.

### 1.12 Propostes separades (fora del pla)

| # | Proposta | Per què | Impacte | Recomanació |
|---|---|---|---|---|
| P1 | Desfer / Refer (Ctrl+Z) | El Movie Maker en tenia, i un usuari sense experiència ho espera | +1 sessió si s'inclou des del principi. El model ja es dissenya amb "ordres" per facilitar-ho. | **Incloure-la** |
| P2 | Girar una foto 90° a mà | Fotos escanejades o amb l'EXIF incorrecte | +0,5 sessions | **Incloure-la** |
| P3 | Títol inicial i crèdits finals senzills | El Movie Maker en tenia i s'usaven molt en els passis | +2 o 3 sessions | Per a la v1.1 |
| P4 | Punt d'interès o detecció de cares per orientar el zoom | Millora la qualitat del moviment automàtic | +2 sessions | Per a la v1.1 |
| P5 | "Desar el projecte amb les fotos" en una carpeta | Per portar el projecte a un altre ordinador | +1 sessió | Opcional |
| P6 | Instal·lador amb associació de fitxers `.passimaker` | Doble clic per obrir projectes | +1 sessió (i un certificat opcional de 200–400 €/any) | No, de moment |

### 1.13 Propostes incorporades a l'abast (decisió D2)

**P1 · Desfer / Refer**
- Ctrl+Z desfà i Ctrl+Y (o Ctrl+Maj+Z) refà. També al menú Edita i amb dos botons a la barra d'eines.
- Cobreix totes les edicions del projecte: afegir, eliminar, moure i duplicar fotos; durades; moviments; encaix; girar; música i ajustos. No cobreix desar, obrir ni exportar.
- Historial de 100 passos. Obrir o recuperar un projecte buida l'historial.
- Es manté la confirmació en eliminar 5 fotos o més (§1.2). Pendent de decidir: amb el desfer, es podria treure o pujar el llindar (vegeu docs/sessions/B00.md).
- Implementació: el controlador (B1) desa instantànies del projecte, que és immutable; la interfície (B10, B11) hi afegeix els menús i les dreceres.

**P2 · Girar una foto 90°**
- Menú contextual i botons al panell de la foto: "Girar a l'esquerra" (Ctrl+Maj+R) i "Girar a la dreta" (Ctrl+R). Funciona també amb diverses fotos seleccionades.
- El gir s'aplica després de l'orientació EXIF i es desa al projecte (no es modifica mai el fitxer original).
- En girar una foto es recalculen l'encaix automàtic i el moviment (la proporció canvia).
- Implementació: la font d'imatges (B4) aplica el gir; la interfície (B10) hi afegeix les accions.
