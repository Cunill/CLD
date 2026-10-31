---
name: rcvfta
description: Tancament d'un bloc de desenvolupament de PassiMaker (revisió, comprovació, verificació, fusió, tancament i actualització de la documentació) i, al final, llista clara del que queda pendent del bloc. Es fa servir quan el codi del bloc ja és fet i pujat a la branca (/rcvfta, opcionalment amb el número de PR o el nom del bloc).
---

# /rcvfta: Revisar, Comprovar, Verificar, Fusionar, Tancar, Actualitzar

Tanca un bloc (BNN, CNN o MNN) de la sessió actual. Segueix el CLAUDE.md (protocol de sessió i "Comunicació amb
l'usuari"). Tot el que vegi l'usuari, en català. Les hores, amb el rellotge de l'usuari (UTC+1; UTC+2 a l'estiu).

**Argument opcional:** número de PR o nom del bloc. Si no n'hi ha, es dedueix de la branca actual, de la PR oberta
d'aquesta branca i de docs/sessions/. Si no és clar quin bloc és, pregunta-ho (a "Per decidir:") i atura't.

## 0. Preparació

1. `git status` i `git branch --show-current`: l'arbre ha d'estar net i tot ha d'estar pujat (`git log @{u}..`).
   Si hi ha canvis sense desar, desa'ls amb un commit descriptiu en català (o atura't si no són del bloc).
2. Identifica el bloc, la PR (eines `mcp__github__*`; al núvol no hi ha GraphQL, no facis servir `gh pr`/`gh issue`),
   la nota `docs/sessions/BNN.md` i les files del bloc a la taula de seguiment del pla (p. ex. docs/PLA_1_3.md §1.1,
   docs/PLA_YOUTUBE.md §4.1) i a l'apartat "Estat" del CLAUDE.md.
3. Llegeix la nota del bloc, els criteris d'acceptació del prompt/pla i `docs/CONTRACTES.md` (només els apartats
   del bloc). No exploris tot el repositori.

## 1. Revisió (R)

1. Revisa el diff contra `main` (`git diff origin/main...HEAD`), amb la skill `code-review` si és gran.
2. Comprova, com a mínim:
   - Només s'han tocat els fitxers permesos pel bloc; si n'hi ha d'altres, o s'ha canviat un contracte sense
     permís, és una **desviació** (anota-la, no la facis passar en silenci).
   - Regles d'arquitectura 1–10 del CLAUDE.md (Qt només a `ui`/`preview`; projecte només pel controlador; un sol
     compositor; valors per defecte només a `model/defaults.py`; subprocess només a `ffmpeg`; textos amb `tr` i en
     català; cap dependència nova sense aprovació).
   - Proves escrites alhora que el codi; cap prova afeblida, esborrada ni ometuda; cap imatge golden regenerada
     sense permís.
3. Corregeix el que calgui dins del bloc, amb commits petits ("BNN: …"). Si la correcció surt del bloc, aturat i
   proposa-ho.

## 2. Comprovació (C)

Executa, i mostra el resultat real (no resumeixis un fracàs):

```
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/unit/<mòdul del bloc>
uv run pytest -m "not perf"
```

Tot ha de ser verd. Si falla: màxim 2 intents sobre el mateix problema; després commit "WIP", nota a
`docs/sessions/BNN.md` amb l'estat i el pas següent, i atura't (condició de bloqueig del protocol). No saltis cap
comprovació i no marquis res com a fet si no s'ha vist passar.

## 3. Verificació (V)

1. Criteris d'acceptació del bloc, un per un: marca cadascun com a complert amb l'evidència (prova, ordre o
   fitxer), o com a **no complert / no verificable aquí**.
2. CI de la PR a GitHub (Windows inclòs): `mcp__github__pull_request_read` (estat i checks) i, si falla,
   `mcp__github__get_job_logs`. Cal CI **verda** abans de fusionar; si està en curs, espera-la (no facis `sleep`
   en bucle: comprova-ho a intervals raonables) i, si falla, repara-la amb la mateixa regla de 2 intents.
3. La PR ha de tenir resum, criteris marcats i desviacions. Completa'n la descripció si falta
   (`mcp__github__update_pull_request`).
4. Separa el que **només pot provar l'usuari** (Windows, fotos reals, so, ZIP): no ho donis per provat.

## 4. Fusió (F)

Només si les seccions 1–3 són verdes i la PR no té conflictes.

1. Si `main` ha avançat: porta `main` a la branca (`git fetch origin main` i fusió o rebase només si és la teva
   branca), resol conflictes sense perdre canvis d'altres blocs, torna a passar la secció 2 i espera la CI.
2. Fusiona la PR amb `mcp__github__merge_pull_request` (la fusió que faci servir el repositori; mira les últimes
   PR amb `mcp__github__list_pull_requests`). Mai `push --force` ni push directe a `main`.
3. No esborris la branca remota (el núvol no pot), no creïs etiquetes ni versions publicades (això és del flux
   `publicar.yml` o de la sessió local; docs/PUBLICAR.md). Si cal, apunta-ho a "Pendent".
4. Anota el commit de fusió a `main` (`mcp__github__get_commit`/`list_commits`).

## 5. Tancament (T) i actualització (A)

En una sola PR petita de documentació (branca `ccr-…` de la sessió; si la PR del bloc ja és fusionada, parteix de
`main` actualitzat) o, si la PR del bloc encara és oberta, en un commit abans de fusionar-la:

1. `docs/sessions/BNN.md`: estat final (✅ tancat/fusionat a `main` el dia X, PR #N amb descripció breu, commit),
   què s'ha fet, desviacions, decisions de l'usuari, proves fetes i **proves manuals pendents**, i "Com reobrir".
2. Taula de seguiment del pla (§ corresponent): fila del bloc amb Estat (✅ / ⏳ / ⛔), sessions consumides i
   "PR · commit" amb descripció breu.
3. CLAUDE.md, apartat "Estat": una entrada curta del bloc (PR amb descripció, commit, si falta la prova manual).
4. `docs/CHANGELOG.md` i `docs/proves_usuari.md` només si el bloc ho demana o canvia el que veu l'usuari; la guia
   (`ui/help.py`) no és d'aquest pas si el bloc no la té permesa.
5. Comprova que el que has escrit és cert (PR i commits existents, estats coherents entre els tres llocs) abans de
   fer el commit ("BNN: tancament i documentació") i el push a la branca de la sessió. No obris PR de més sense
   que ho demani l'usuari; si cal que la documentació arribi a `main`, ho dius a "Per decidir:".

## 6. Informe final: què queda pendent

Acaba **sempre** amb aquest bloc, ben visible i sense eufemismes. Els avisos que impedeixen fer alguna cosa van al
**principi** del missatge. Format:

**Bloc BNN: <nom>** → ✅ tancat del tot · 🟡 tancat amb pendents · ⛔ no tancat (digues-ho en una línia)

| Comprovació | Resultat |
|---|---|
| Revisió | … |
| Estil, tipus i proves | … |
| Criteris d'acceptació | n de m complerts |
| CI de Windows | … |
| Fusió | PR #N (descripció breu) · commit `…` |
| Documentació | sessions / pla / CLAUDE.md |

**Pendent del bloc:** llista numerada; cada punt amb qui ho fa (tu / usuari / altra sessió) i com. Categories a
revisar sempre, encara que siguin buides ("res"):
1. Criteris d'acceptació no complerts o no verificats.
2. Desviacions i deute tècnic que s'ha deixat (amb on s'ha apuntat).
3. Proves manuals de l'usuari a Windows (passos curts, un cada vegada).
4. Accions que el núvol no pot fer (etiqueta, versió publicada, esborrar branca remota, coses al PC local).
5. Blocs dependents que ara es poden començar o que encara bloqueja aquest.

Si no queda res, digues-ho en una frase: "No queda res pendent del bloc."

**Per decidir:** (numerat, una pregunta per punt, amb les opcions; omet-ho si no n'hi ha.)
