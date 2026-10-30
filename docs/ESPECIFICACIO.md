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
| Durada per foto | 2,0 s | 0,4–24 s (en passos de 0,1 s; M05). "Ajustar a la música" fa servir el mateix rang (decisió 0014, M07) |
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
- La importació és progressiva i es pot cancel·lar. En cancel·lar, s'afegeixen les fotos que ja s'havien llegit (decisió 0010).

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
- Per eliminar: tecla Supr, botó o menú contextual. Només es demana confirmació si se n'eliminen 5 o més. Es manté encara que hi hagi "desfer" (P1, decisió 0007).
- Per duplicar: Ctrl+D o menú contextual. La còpia va just després de l'original, amb la mateixa durada i el mateix encaix però amb un moviment nou i diferent.
- Mida de les miniatures: petita, mitjana o gran.
- En fer clic sobre una miniatura, la previsualització salta a l'inici d'aquella foto i el panell de propietats en mostra els ajustos.
- **Fitxes negres (M08, decisió 1 de docs/PLA_1_3.md):** un projecte nou té una fitxa negra a l'inici i una al final
  del tauler, cadascuna amb la seva durada (2,0 s; de 0,4 a 24 s, com una foto). Són un quadre negre amb el text "Negre"
  i la durada, sense miniatura, número ni icones. Es queden sempre la primera i l'última: afegir, moure, ordenar o
  duplicar fotos no les desplaça, no es poden arrossegar i les fotos que s'hi deixen anar a fora entren just a dins.
  Es poden seleccionar i esborrar (Supr, com una foto) i tornar a afegir amb Edita ▸ "Afegeix negre a l'inici" /
  "Afegeix negre al final" (desactivat si ja hi és). Al panell de propietats només tenen la durada. Desfer/refer, com
  sempre. El recompte de fotos de la barra d'estat no les compta; la durada total, sí.

**Casos límit:**
- 0 fotos: estat buit amb instruccions (també si només hi ha les fitxes negres).
- 1 foto: el passi és vàlid.
- 1.000 fotos: el desplaçament és fluid (només es dibuixen les miniatures visibles) i les miniatures es carreguen començant per les que es veuen.
- Foto no trobada: miniatura grisa amb una icona i l'opció "Cercar…".

### 1.3 Durada per foto

- La durada general és de 2,0 s (de 0,4 a 24 s, en passos de 0,1 s; M05). Una foto més curta que la fosa la té
  escurçada (la fosa no passa mai de la meitat de la foto més curta). Si es canvia, afecta totes les fotos que no tenen una durada personalitzada.
- Per a una foto, o per a les fotos seleccionades, hi ha el camp "Durada" al panell de propietats. Si es modifica, la foto queda marcada com a personalitzada (amb una icona) i apareix el botó [Restablir a la general].
- La durada és l'espai que ocupa la foto a la línia de temps, des de la meitat de la fosa anterior fins a la meitat de la següent. Així, la durada total del passi és exactament la suma de les durades de totes les fotos.
- La barra d'estat mostra sempre el total ("124 fotos · 10:20"), amb les fitxes negres incloses (M08).
- Cas límit: si una foto dura menys que dues foses, la fosa d'aquella foto s'escurça automàticament (vegeu 1.4).

### 1.4 Transició de fosa

- Hi ha una fosa encadenada entre cada parella de fotos consecutives, amb una durada global d'1,0 s (de 0,5 a 1,5 s). No hi ha cap altre tipus de transició.
- A l'inici hi ha una fosa des de negre (1,0 s) i al final una fosa cap a negre (2,0 s). Totes dues es poden ajustar a "Avançat" (de 0 a 5 s).
- La fosa queda centrada en el canvi de foto: comença 0,5 s abans i acaba 0,5 s després. Durant la fosa, les dues fotos continuen movent-se; el moviment no s'atura mai.
- Regla de seguretat: la fosa entre dues fotos no pot durar més de la meitat de la més curta. Així, cada foto té un moment en què es veu sencera.
- Les fitxes negres (§1.2, M08) fan la fosa encadenada de sempre amb la foto del costat (que és, de fet, una fosa
  des del negre o cap al negre), amb la mateixa regla de seguretat. La fosa des de negre i cap a negre del projecte
  continuen a l'inici i al final del passi; sobre una fitxa negra no es veuen. La música comença a l'inici del passi,
  també durant la fitxa negra.
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
- El botó [🎲 Nou moviment a l'atzar] tria un moviment nou per a la foto o les fotos seleccionades. Funciona sempre:
  si una foto tenia el moviment fixat a mà, torna a Automàtic (M05).
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
- Formats: MP3, WAV, M4A/AAC, FLAC, OGG, WMA i OPUS. També es poden descarregar de YouTube (§1.7 bis) o gravar-les del so de l'ordinador (§1.7 ter).
- Les cançons sonen una darrere l'altra des del principi del vídeo, sense trepitjar-se.
- **Silenci abans i després de la música** (M13, millora 6): al panell de la cançó, apartat "Tota la música", "Silenci
  abans" i "Silenci després" (per defecte 0 s; de 0 a 60 s, en passos de 0,5 s). Són de tota la música, no de cada
  cançó, i es poden desfer. La primera cançó comença X segons després del principi del vídeo, i la música s'acaba com a
  molt Y segons abans del final (si no hi cap, la fosa final de 3 s acaba just allà). Són independents de les fitxes
  negres: amb una fitxa negra de 2 s i X = 5 s, la música comença al segon 5.
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
- El botó [Ajustar a la música] torna a calcular les durades perquè el passi duri exactament el mateix que la música (la suma de les cançons, ja retallades) (decisió 0014), més el silenci d'abans i el de després (M13).
- **Les fotos amb la durada posada a mà no es toquen**: se'n resta el total de la durada de la música i la resta es reparteix entre les altres fotos (les que fan servir la durada per defecte, que passa a valer el que toqui). Qualsevol element amb una durada pròpia, com les fitxes negres, també es manté.
- Cada foto lliure pot durar entre 0,4 i 24 s (el mateix rang que a mà). Si caldria menys de 0,4 s per foto, surt l'avís "Hi ha massa fotos per a aquesta música: cada foto duraria 0,3 s. Afegeix música o treu fotos."; si en caldria més de 24 s, "La música és massa llarga per a aquestes fotos: afegeix-ne o retalla la música." En tots dos casos, [Aplicar igualment] (amb el límit de 0,4 o 24 s) i [Cancel·lar]. El temps per foto que surt a l'avís és el que queda de música després de les fotos fixes.
- Si **totes** les fotos tenen la durada posada a mà, o les fixes ja duren tant com la música o més, no es canvia res: surt un avís ("Totes les fotos tenen la durada posada a mà, així que no hi ha res a ajustar…" o "Les fotos amb la durada posada a mà ja duren tant com la música o més…") amb un sol botó [D'acord].
- Casella "Mantenir ajustat" (desactivada per defecte): si s'activa, el passi es torna a ajustar sol cada vegada que s'afegeixen fotos o cançons, o es canvien els silencis (M13) (amb les mateixes regles; si no hi ha res a ajustar, no fa res i no avisa).

**Quan la música i les fotos no duren el mateix**

| Situació | Comportament per defecte | Com ho veu l'usuari |
|---|---|---|
| La música dura més que el passi | La música es talla amb una fosa de volum de 3 s que acaba just amb la fosa a negre del vídeo (o, amb silenci després, Y segons abans del final) | Avís discret a la barra d'estat: "La música dura 1:22 més. [Ajustar a la música]" |
| La música dura menys que el passi | Després de l'última cançó (amb la seva fosa de sortida) hi ha silenci (la barra d'estat compta els silencis d'abans i de després amb la música) | "La música s'acaba 0:45 abans. [Ajustar a la música]" |
| No hi ha música | Vídeo amb una pista d'àudio en silenci, perquè sigui més compatible amb els televisors | — |

**Casos límit:**
- Cançó corrupta o protegida (DRM): es marca en vermell, amb un missatge, i no entra a la mescla.
  El seu lloc queda en silenci i les cançons següents no s'avancen (D12, decisió 0007).
- Cançó més curta que les seves dues foses: cada fosa es redueix al 40 % de la durada de la cançó.
- Retall amb l'inici després del final: no es permet.
- Àudio mono, 5.1 o amb freqüències de mostreig diferents: es converteix a estèreo de 48 kHz.
- Música de més d'una hora: s'admet.

### 1.7 bis Música de YouTube (decisió 0012, versió 1.2.0)

Cercar cançons a YouTube, o enganxar-ne l'enllaç, i descarregar-les en MP3 per afegir-les al passi. És l'única part
del programa que es connecta a internet; la resta funciona igual sense xarxa.

**Avís de conformitat**
- En triar [+ Música ▾] → "Des de YouTube…" s'obre primer un diàleg modal, "Abans de fer servir YouTube":
  - "Aquesta funció es connecta a internet per cercar i descarregar àudio de YouTube."
  - "Les condicions de YouTube no permeten descarregar contingut si YouTube no ofereix un botó de descàrrega."
  - "La majoria de cançons tenen drets d'autor. Descarrega i fes servir només música que tinguis dret a fer servir."
  - "Ets responsable de l'ús que en facis."
  - "PassiMaker i els seus autors declinen qualsevol responsabilitat derivada de l'ús de la música descarregada, i en particular per qualsevol infracció dels drets d'autor o de les condicions de YouTube."
  - Casella "☐ He llegit l'avís, n'accepto les condicions i hi estic conforme" i botons [Cancel·la] i [Accepta i continua].
- La casella no està mai marcada d'entrada; [Accepta i continua] està desactivat fins que es marca.
- [Cancel·la], Esc o tancar la finestra: no s'obre la funció i no es desa res.
- La conformitat val per a la sessió del programa: es guarda només a la memòria i no es desa enlloc (ni la
  configuració, ni el registre, ni el `.pmk`). Mentre PassiMaker és obert, l'avís no torna a sortir; en tancar-lo es
  perd. La comparteixen totes les finestres obertes.
- Enllaç "Retira la conformitat" a la finestra de YouTube: la tanca i cancel·la les descàrregues en curs.
- **Cap connexió abans d'acceptar**, ni tan sols per comprovar si hi ha internet. La finestra de YouTube tampoc no fa
  res sola en obrir-se (cap cerca, miniatura ni comprovació de versió): la primera connexió és la primera cerca o
  enllaç que demana l'usuari.

**Recorregut**

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Franja de música → [+ Música ▾] → "Des de YouTube…" | S'obre el diàleg "Música de YouTube" (no modal: es pot continuar treballant). Si encara no s'ha acceptat l'avís en aquesta sessió del programa, abans surt l'avís. |
| 2a | Escriu una cerca ("Ludovico Einaudi Nuvole Bianche") i prem Retorn | Llista de 10 resultats: miniatura, títol, canal, durada. [Més resultats] en carrega 10 més. |
| 2b | O bé enganxa un enllaç (`youtube.com/watch?v=…`, `youtu.be/…`, `music.youtube.com/…`, `shorts/…`) | El camp el reconeix sol i mostra un únic resultat amb les dades del vídeo. |
| 3 | Selecciona un o diversos resultats i prem [Descarrega en MP3] | Primer es tria la carpeta. Després cada fila mostra el progrés (descarregant → convertint → fet) i es pot cancel·lar cada descàrrega. |
| 4 | Casella "Afegeix al projecte en acabar" (marcada per defecte) | En acabar, la cançó s'afegeix a la franja de música (Ctrl+Z la treu, com sempre). |
| 5 | [Mostrar a la carpeta] | Obre la carpeta on s'ha desat l'MP3. |
| — | [Obre a YouTube], a cada resultat | Obre el vídeo al navegador per escoltar-lo abans de descarregar-lo (el programa no s'hi connecta). |

Si es tanca el diàleg amb descàrregues en curs, pregunta si s'han de cancel·lar.

**Valors per defecte**

| Paràmetre | Per defecte | Notes |
|---|---|---|
| Resultats per pàgina | 10 | `defaults.YOUTUBE_RESULTS_PER_PAGE` |
| Durada màxima | 20 min | Evita descarregar per error mescles d'hores. `defaults.YOUTUBE_MAX_DURATION_S`. Els resultats més llargs surten en gris, amb el motiu. |
| Format | MP3, 192 kbps, 48 kHz estèreo | `defaults.YOUTUBE_MP3_BITRATE_KBPS`; 48 kHz com el mesclador |
| Carpeta de destinació | Es pregunta cada vegada | Un cop per a tota la selecció, en prémer [Descarrega en MP3]. Proposa sempre la carpeta Baixades, sense recordar la darrera (decisió de l'usuari, 25/10/2026). Cancel·lar-lo no descarrega res. |
| Nom del fitxer | `<títol>.mp3`, sense caràcters no vàlids a Windows | Si ja existeix, `<títol> (2).mp3`. Mai no se sobreescriu res. |
| Metadades | Títol, canal (com a artista) i l'enllaç d'origen al comentari | Etiquetes ID3 |
| Descàrregues simultànies | 2 | `defaults.YOUTUBE_SIMULTANEOUS_DOWNLOADS`; la resta, a la cua |

**Errors**

| Situació | Missatge |
|---|---|
| Sense connexió | "No hi ha connexió a internet. Comprova la xarxa i torna-ho a provar." |
| Enllaç no vàlid | "Aquest enllaç no és d'un vídeo de YouTube." |
| Vídeo privat, esborrat, amb restricció d'edat o de país | "Aquest vídeo no es pot descarregar (és privat, s'ha esborrat o té restriccions)." |
| Directe en curs | "No es poden descarregar directes." |
| YouTube ha canviat i yt-dlp ja no funciona | "YouTube ha canviat i aquesta versió de PassiMaker ja no pot descarregar. Cal una versió nova del programa." (el detall, al registre) |
| YouTube bloqueja la xarxa ("confirma que no ets un robot", massa peticions) | "YouTube no deixa descarregar des d'aquesta xarxa ara mateix. Torna-ho a provar més tard o des d'una altra connexió." (el detall, al registre) |
| Massa llarg | "Aquest vídeo dura més de 20 minuts." |

**Fora d'abast:** llistes de reproducció senceres, vídeo (només àudio), altres webs que admet yt-dlp, escoltar la
cançó dins del programa (es fa al navegador amb [Obre a YouTube]) i el filtre Creative Commons (descartat a la
decisió 0012).

### 1.7 ter Grava el que sona (decisió 0013, versió 1.2.0)

Gravar en directe el so que sona a l'ordinador (YouTube al navegador, Spotify, qualsevol reproductor) i desar-lo en MP3
per fer-lo servir al passi. No es connecta a internet i no mostra cap avís (G2).

**Recorregut**

| # | Acció de l'usuari | Què passa |
|---|---|---|
| 1 | Franja de música → [+ Música ▾] → "Grava el que sona…" | S'obre la finestra "Grava el que sona" (no modal), directament, sense cap avís. |
| 2 | Tria l'origen (per defecte, la sortida de so que fa servir Windows, p. ex. "Altaveus" o els auriculars Bluetooth) | Les ones i el mesurador de nivell mostren en directe si arriba so, **abans de gravar** (no es desa res). |
| 3 | Posa en marxa la cançó a Spotify, al navegador… i prem [● Grava] | Comença a gravar: les ones es tornen vermelles, i es veuen el temps transcorregut, el mesurador i l'espai lliure al disc. Amb "Comença quan soni", espera el primer so. |
| 4 | [■ Atura] (o s'atura sola després de 5 s de silenci, si està activat) | Mostra l'ona de tota la gravació amb els silencis que es retallaran ombrejats. Retalla el silenci de l'inici i del final, demana on desar-la (cada vegada) i el nom (proposa "Gravació 25-10-2026 18.30"), i la converteix a MP3. |
| 5 | Casella "Afegeix al projecte en acabar" (marcada per defecte) | La cançó s'afegeix a la franja de música (Ctrl+Z la treu, com sempre). |
| — | [Descarta] | Esborra la gravació sense desar-la (amb confirmació si dura més de 10 s). |
| — | Tancar la finestra o el programa mentre es grava | Pregunta "La gravació s'esborrarà. Vols aturar-la i sortir?". Si es confirma, s'esborra. |

**Orígens**
- Llista amb dos grups: "So de l'ordinador" (cada sortida de so) i "Micròfon i entrada de línia" (cada entrada). La
  primera és la sortida per defecte de Windows. Les entrades no es fan servir mai si l'usuari no les tria (G6).
- Es recorda l'última tria mentre el programa és obert.
- Com a molt es graven dos canals: un origen mono, en mono; un de 5.1 o més, la seva mescla estèreo.

**Valors per defecte**

| Paràmetre | Per defecte | Notes |
|---|---|---|
| Origen | La sortida de so per defecte de Windows | |
| "Comença quan soni" | Activat | Comença a desar quan el nivell arriba a −50 dBFS. `defaults.RECORD_START_THRESHOLD_DBFS` |
| "Atura't després de N s de silenci" | Activat, 5 s | 1–60 s, silenci per sota de −50 dBFS. `defaults.RECORD_SILENCE_STOP_S`. Útil per gravar una sola cançó. |
| Retallar el silenci de l'inici i del final | Activat | Per sota de −50 dBFS, amb 0,2 s de marge. `defaults.RECORD_TRIM_*` |
| Durada màxima | 30 min | En arribar-hi, la gravació **s'esborra** (G5). A falta d'1 min, el temps es posa en taronja. `defaults.RECORD_MAX_DURATION_S`, `RECORD_MAX_WARNING_S` |
| Format mentre es grava | WAV de 32 bits flotants a la carpeta temporal, escrit a mesura | No a la memòria (30 min ≈ 690 MB). És temporal fins que l'usuari atura i desa. |
| Normalització en desar | Activada, fins a un pic de −1 dBFS | Si la part que es desa queda fluixa (pic per sota de −1 dBFS), se'n puja el nivell fins a −1 dBFS; mai més amunt, i una gravació més forta no s'abaixa (decisió de l'usuari del 26/10/2026). `defaults.RECORD_NORMALIZE_ENABLED`, `RECORD_NORMALIZE_PEAK_DBFS` |
| Format final | MP3, 192 kbps, 48 kHz estèreo | `defaults.RECORD_MP3_BITRATE_KBPS`; el WAV temporal s'esborra en acabar. |
| Freqüència | La de la sortida de Windows (44,1 o 48 kHz) | L'MP3 es fa a 48 kHz. |
| Espai lliure mínim | 1 GB | Si en queda menys, no comença; si s'hi arriba gravant, s'atura i s'esborra. `defaults.RECORD_MIN_FREE_BYTES` |
| Carpeta i nom | Es pregunta cada vegada; proposa "Gravació <dia-mes-any> <hora>.<minuts>" | Mai no se sobreescriu res (com a YouTube, §1.7 bis). |

**Consell a la finestra** (text fix): "Tanca o silencia les altres aplicacions: es grava tot el que sona a l'ordinador,
també els avisos. Puja el volum de Windows i el de l'aplicació que sona: com més baixos, més fluixa queda la gravació."
(Comprovat al C08: el volum general de Windows i el de cada aplicació **sí** que afecten la gravació.)

**Ones**
- Un carril per canal de l'origen que es grava: esquerre (E) i dret (D) en estèreo, un de sol en mono.
- L'ona dels últims 10 s es desplaça en directe, amb el pic (mínim i màxim) de cada columna: gris abans de gravar (per
  comprovar que arriba so) i vermella mentre es grava. `defaults.RECORD_WAVE_WINDOW_S`, `RECORD_PEAK_COLUMNS_PER_S`
- Al costat de cada carril, el mesurador de nivell del canal en dBFS, amb una marca de saturació (0 dBFS) que es queda
  encesa 2 s.
- En aturar, l'ona de tota la gravació, reduïda a l'amplada de la finestra, amb els silencis de l'inici i del final que
  es retallaran ombrejats.
- Les ones no fan res més: no s'hi pot clicar ni seleccionar.

**Errors**

| Situació | Missatge |
|---|---|
| No hi ha cap sortida de so | "No s'ha trobat cap sortida de so per gravar." |
| La sortida canvia o es desconnecta mentre es grava (p. ex. auriculars Bluetooth) | "S'ha desconnectat la sortida de so i la gravació s'ha descartat." |
| Silenci durant tota la gravació | "No s'ha gravat cap so. Comprova que la música sona per la sortida triada; algunes aplicacions no deixen gravar el seu so." |
| Menys d'1 GB lliure en prémer [● Grava] | "No hi ha prou espai al disc per començar a gravar (cal almenys 1 GB lliure)." |
| Disc ple o gairebé ple mentre es grava | "No queda prou espai al disc per continuar gravant. La gravació s'ha descartat." |
| Durada màxima | "S'ha arribat al màxim de 30 minuts i la gravació s'ha descartat." |
| Error del sistema de so | "No s'ha pogut gravar el so de l'ordinador. La gravació s'ha descartat." (el detall, al registre) |
| Windows no deixa fer servir el micròfon (en triar una entrada) | "Windows no deixa que el programa faci servir el micròfon. Activa-ho a Configuració → Privadesa → Micròfon → "Permet que les aplicacions d'escriptori accedeixin al micròfon" i torna-ho a provar." |
| Tancament inesperat del programa | Res en tornar-lo a obrir: la gravació no es recupera i el fitxer temporal s'esborra. |

**Interrompuda o acabada (G1).** Una gravació es desa només si s'acaba amb [■ Atura] o amb l'aturada automàtica per
silenci. Totes les altres causes, també la durada màxima (G5), esborren el fitxer temporal abans de mostrar el missatge;
no es pregunta mai si es vol conservar.

**Fora d'abast:** gravar només una aplicació (només Spotify i no la resta), editar l'ona, separar automàticament les
cançons d'una llista i gravar vídeo.

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
- Objectiu de velocitat: al PC de referència, exportar no ha de trigar més del triple de la durada del vídeo (decisió 0008). La previsualització, en canvi, és sempre en temps real (§1.8).
- Casos límit:
  - Disc ple: abans de començar es comprova si hi ha prou espai (estimat). Si el disc s'omple durant l'exportació, surt un missatge clar i s'esborra el fitxer a mig fer.
  - Ja existeix un fitxer amb aquest nom: es demana si es vol substituir.
  - Fotos o cançons que no es troben: no s'exporta i se'n mostra la llista.
  - Rutes amb accents o molt llargues: s'admeten.
  - El vídeo s'escriu amb un nom provisional i es reanomena en acabar.

### 1.10 Desar i obrir projectes

- El projecte es desa en un fitxer `.pmk` (text estructurat i llegible) amb tots els ajustos i les rutes de les fotos i les cançons. Els fitxers originals no es copien.
- Desar (Ctrl+S), Desar com a…, Obrir (Ctrl+O) i llista de projectes recents a la pantalla inicial. El títol de la finestra mostra el nom del projecte, amb un asterisc si hi ha canvis sense desar. En tancar, el programa pregunta si es volen desar.
- Cada 2 minuts es fa una còpia de recuperació, fora de la carpeta del projecte. Si el programa es tanca de cop, en tornar-lo a obrir ofereix recuperar el projecte. Cada finestra té la seva còpia: una finestra oberta no esborra ni substitueix la d'una altra (decisió 0010).
- Les rutes es desen de dues maneres: relatives al fitxer del projecte i absolutes. Si es mou tota la carpeta (projecte i fotos), el projecte continua funcionant.
- Fitxers que no es troben: "No es troben 12 fitxers. [Cercar en una carpeta…]". El programa els torna a enllaçar automàticament pel nom.
- El format porta un número de versió. Si s'obre un projecte fet amb una versió més nova del programa, surt un missatge clar en lloc d'una fallada.
- Versió 2 (M08, PassiMaker 1.3.0): desa les fitxes negres. Un projecte de la versió 1 s'obre sense fitxes negres (no
  se n'hi afegeixen) i es desa ja en versió 2; un projecte de la versió 2 obert amb la 1.2.0 dona el missatge de
  versió més nova.
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
| P6 | Instal·lador amb associació de fitxers `.pmk` | Doble clic per obrir projectes | +1 sessió (i un certificat opcional de 200–400 €/any) | No, de moment |

### 1.13 Propostes incorporades a l'abast (decisió D2)

**P1 · Desfer / Refer**
- Ctrl+Z desfà i Ctrl+Y (o Ctrl+Maj+Z) refà. També al menú Edita i amb dos botons a la barra d'eines.
- Cobreix totes les edicions del projecte: afegir, eliminar, moure i duplicar fotos; durades; moviments; encaix; girar; música i ajustos. No cobreix desar, obrir ni exportar.
- Historial de 100 passos. Obrir o recuperar un projecte buida l'historial.
- Es manté la confirmació en eliminar 5 fotos o més (§1.2), també amb el desfer (decisió 0007).
- Implementació: el controlador (B1) desa instantànies del projecte, que és immutable; la interfície (B10, B11) hi afegeix els menús i les dreceres.

**P2 · Girar una foto 90°**
- Menú contextual i botons al panell de la foto: "Girar a l'esquerra" (Ctrl+Maj+R) i "Girar a la dreta" (Ctrl+R). Funciona també amb diverses fotos seleccionades.
- El gir s'aplica després de l'orientació EXIF i es desa al projecte (no es modifica mai el fitxer original).
- En girar una foto es recalculen l'encaix automàtic i el moviment (la proporció canvia).
- Implementació: la font d'imatges (B4) aplica el gir; la interfície (B10) hi afegeix les accions.
