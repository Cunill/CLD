# Proves amb usuaris

Protocol i resultats de les proves de les fites F2, F3 i F5 (docs/PLA.md §4.4). Es completa a partir de F2.

## Llista de millores pendents de les proves

Tancada al B16 (24/10/2026), reoberta amb la prova manual del B14 (24/10/2026), tancada al M05 (v1.1) i reoberta
el 25/10/2026. Les observacions de les proves
s'anoten aquí i es corregeixen en un bloc de manteniment. Quan es fa el manteniment està per decidir
(s'havia d'esperar la F5, que ja no es fa).

| # | Prova | Observació | Estat |
|---|---|---|---|
| 1 | B14 (usuari, 24/10/2026) | Mentre sona [Escoltar el tros], la forma d'ona no mostra per on va la reproducció. Afegir-hi una línia que avanci. | **Fet** (M05, v1.1): línia vermella que segueix el rellotge del so |
| 2 | B14 (usuari, 24/10/2026) | "Tornar a sortejar" no s'entén. El botó de la foto ha de dir **"Nou moviment a l'atzar"** (🎲). | **Fet** (M05, v1.1) |
| 3 | B14 (usuari, 24/10/2026) | "Nou moviment a l'atzar" no s'ha de desactivar quan la foto té el moviment triat a mà: s'ha de poder aplicar sempre (la foto torna a automàtic amb un moviment nou). | **Fet** (M05, v1.1) |
| 4 | Fotos reals (usuari, 24/10/2026) | La durada de cada foto ha d'admetre de **0,4 a 24 s** (ara 1–3 s, `defaults.PHOTO_DURATION_RANGE`). Cal revisar-ho amb la fosa (0,5–1,5 s, més llarga que 0,4 s) i els límits de velocitat del moviment (decisions 0004 i 0005). | **Fet** (M05, v1.1; decisió 0011) |
| 5 | Usuari (25/10/2026) | Afegir **uns segons de negre quiet** a l'inici i al final del passi, abans de la fosa des del negre i després de la fosa cap al negre. La durada ha de ser ajustable i s'ha de poder suprimir. **Concretat per l'usuari el 29/10/2026:** per defecte, **dues imatges negres**, una a l'inici i una al final del passi, que **es queden fixes en aquesta posició** mentre l'usuari no les esborri. Al bloc M08 (docs/PLA_1_3.md). | **Fet** (M08, v1.3) |
| 6 | Usuari (25/10/2026) | Afegir **X segons de silenci a l'inici i Y al final** de la música, opcionals i independents del negre quiet de la 5. "Ajustar a la música" els ha de tenir en compte en calcular la durada de les fotos. Al bloc M13 (docs/PLA_1_3.md, decisió de l'usuari del 30/10/2026). | Pendent |
| 7 | Usuari (25/10/2026) | "Ajustar a la música" ha de **respectar les fotos amb la durada canviada a mà**: en manté la durada, en resta el total de la durada de la música i reparteix la resta entre les altres fotos. Si totes les fotos tenen la durada canviada a mà, no toca res i avisa. A més, **el límit de 1–3 s queda obsolet** i no ha de sortir enlloc: l'ajust fa servir el mateix rang que la durada feta a mà (0,4–24 s; canvia la decisió 0011). Ara les escala totes juntes i les limita a 1–3 s, de manera que una foto posada a 10 s queda en 3 s. **Recordat per l'usuari el 29/10/2026** a la prova del ZIP 1.2.0 (pas 7: fotos a 3 s i uns 6 min de música sobrant). Hi ha un esborrany aturat (commit `0d4a10f`, branca `ccr-08701f22-8ayer4`, desfet abans d'arribar a `main`) que posa el límit a 1–24 s: cal canviar-lo a 0,4–24 s i afegir-hi les fotos fixes. Al bloc M07 (docs/PLA_1_3.md). | **Fet (M07)**: decisió 0014; les fotos amb durada a mà es mantenen, la resta es reparteix en 0,4–24 s, i avisa si totes són a mà (docs/sessions/M07.md). Falta la prova manual de l'usuari |

## Resultats

### F2 · prova del resultat
- **21/10/2026**: l'usuari ha provat el vídeo amb les seves fotos, vertical i horitzontal: correcte (vegeu
  `docs/sessions/B09.md`, "Fita F2").
- ~~Ensenyar el vídeo a una persona que no hi hagi participat~~: **no es fa** (decisió de l'usuari, 24/10/2026).

### F3 · primera prova d'ús real
- Prova manual del B11 i del B13 a Windows feta per l'usuari el 23/10/2026: correctes. No s'ha anotat cap prova amb
  una persona sense experiència.

### Fotos reals (usuari, 24/10/2026)
- Carpeta de fotos de càmera i de mòbil, sense HEIC, al PC de referència: les miniatures surten de seguida i es veuen
  nítides (cap de borrosa o pixelada). La nitidesa de la miniatura EXIF (B5, B10) queda comprovada.
- Sense provar: fotos HEIC d'iPhone.

### F5 · prova final
- **No es fa** (decisió de l'usuari, 24/10/2026: cap prova amb persones externes). El protocol es queda per si mai
  es vol fer.

## Protocol de la prova F5

**Objectiu:** dues persones que no han fet servir mai el programa fan un passi complet en **menys de 5 minuts**,
sense ajuda (recorregut de referència de `docs/ESPECIFICACIO.md` §1.0).

**Preparació (10 min)**
1. Un PC amb Windows que no sigui el de desenvolupament. Descomprimir el ZIP `PassiMaker-1.0.0-win64` a l'escriptori.
2. Una carpeta amb **30 fotos** variades (horitzontals, verticals i alguna d'iPhone en HEIC) i **1 cançó** MP3 d'uns
   2 minuts.
3. Cronòmetre i aquest full per apuntar.

**Consigna (es llegeix tal qual):** "Amb aquest programa, fes un vídeo amb les fotos d'aquesta carpeta i aquesta
cançó, i desa'l a l'escriptori. Fes-ho com et sembli; jo no et puc ajudar. Digues en veu alta el que penses."

**Durant la prova:** no ajudar ni assenyalar res. Si la persona queda encallada més d'1 minut, apuntar-ho i
dir-li només "pots mirar el menú Ajuda".

**Què s'apunta**

| Mesura | Persona 1 | Persona 2 |
|---|---|---|
| Temps fins que hi ha les fotos al storyboard | | |
| Temps fins que hi ha la música | | |
| Temps fins que comença l'exportació | | |
| **Temps total** (sense l'espera de l'exportació) | | |
| On ha dubtat (més de 10 s sense fer res) | | |
| Ha obert la guia (F1)? | | |
| Errors o missatges que no ha entès | | |
| Ha mirat la previsualització? | | |
| El vídeo final: queda bé? marejà? la música acaba bé? | | |

**Criteri:** les dues persones acaben en menys de 5 minuts i el vídeo es reprodueix bé al seu mòbil o televisor.
Cada dubte es converteix en una fila de la llista de millores de més amunt.
