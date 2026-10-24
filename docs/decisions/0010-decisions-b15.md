# 0010 · Decisions abans del B15: .pmk, cancel·lar la importació, versió i còpies de recuperació

- **Data:** 23/10/2026 · **Estat:** acceptada (decisions de l'usuari) · **Aplicada a:** bloc B15

## 1. Fitxers .pmk: sense doble clic
Es deixa com ara: PassiMaker **no** s'associa amb els fitxers `.pmk`. Els projectes s'obren des del programa
(Obrir, recents), arrossegant-los a la finestra o com a argument de `PassiMaker.exe`. La proposta P6 (instal·lador
amb associació) continua fora del pla.

## 2. Cancel·lar una importació conserva les fotos ja llegides
Resol el pendent del B10 (la seva decisió 2) i del B11. En cancel·lar, s'afegeixen les fotos que ja s'havien llegit,
en l'ordre de sempre, sense fer cap més pregunta (subcarpetes, duplicats); les que fallen s'informen com sempre. Amb
1.000 fotos, cancel·lar no fa perdre la feina feta. Abans: cancel·lar no n'afegia cap.

## 3. Versió 0.5.0
El programa passa de `0.0.1` a **`0.5.0`** (`pyproject.toml` i `passimaker.__version__`). Quan el B15 es fusioni a
`main`, s'hi posa l'etiqueta **`v0.5-mvp`** (la de la fita F3 del pla). La `1.0` és la del B16.

## 4. Una còpia de recuperació per finestra
Abans, totes les finestres desaven la mateixa còpia (`cache_root()/recuperacio/recuperacio.pmk`) i una podia
esborrar o substituir la d'una altra. Ara cada finestra fa servir una carpeta pròpia
(`recuperacio/finestra-<id>/recuperacio.pmk`) amb un fitxer de bloqueig (`oberta.lock`, `QLockFile`) mentre és
oberta. En arrencar, només s'ofereixen les còpies de les finestres que ja no són obertes (s'han tancat malament): la
més recent primer. Si es rebutja, s'esborra; la primera que s'accepta s'obre i passa a la carpeta de la finestra
nova. Com que una finestra només té un projecte, **les altres còpies s'ofereixen en la propera arrencada**.
Una còpia antiga (de la versió amb una sola còpia) també s'ofereix.

No canvia cap contracte: `projectio.save_recovery`, `find_recovery` i `clear_recovery` continuen rebent una carpeta.
