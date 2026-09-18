# 0042. Il design system: una cartella che non è Python, un file di token da cui il resto deriva per intero, tre liste lette dalla loro fonte, e i nomi dei livelli di attenzione

- **Stato:** Proposta il **2026-09-18**, scritta **prima** della prova a mano di M17.1 (review
  dell'utente del 2026-09-18, punto 16: un commit con l'ADR in «Proposta», prima dei candidati del
  font). Diventa «Accettata» quando la prova è passata e l'utente ha scelto il font, che §9 oggi
  lascia in bianco — il percorso di ADR 0040 con la sua prova. SPEC di M17.1 approvata dall'utente
  il 2026-09-18, con le sue dieci decisioni prese prima della stesura e quindici domande chiuse
  nella review.
- **Data:** 2026-09-18
- **Riferimenti spec:** §6, §7, §29, §48
- **Riferimenti design:** `docs/spec/ELA_design.md` — §6 del design, §13 del design,
  §19 del design, §21 del design, §22 del design, §24 del design, §29 del design, §34 del design.
- **Milestone:** M17.1, la prima della Fase 17 (`docs/STATO.md`, voce 5.10).
- **Continua:** ADR 0024 §1 (una cartella che §48 non prevede si documenta); ADR 0028 §1 (chi
  entra nel gate critico); ADR 0031 §6 (un test afferma solo ciò di cui ha costruito le
  precondizioni); ADR 0039 §1 (dove vive il codice è il livello di verifica); ADR 0041 §3 (ogni
  test nuovo regge il parallelo).

## Contesto

La prima superficie di ELA che non è un terminale è il companion iPhone di M12.5, e §20 del design
vuole che usi la stessa identità del Command Center di M17.2. Un'identità scritta due volte, una per
superficie, smette di essere una alla prima modifica: serve un posto solo da cui entrambe leggano, e
serve prima della prima delle due.

Il repository ha già un modo di tenere vero ciò che si può derivare — `docs/STATO.md` e
`docs/ARCHITECTURE.md`, generati e riconfrontati a ogni `make check` — e ha una regola che lo
riassume: *un documento che non può accorgersi di essere diventato falso è decorazione*. Un design
system è pieno di cose che possono diventare false in silenzio: un colore scritto a mano in un
componente, un contrasto che scende sotto soglia nel tema che nessuno guarda, una lista di stati
ricopiata che non segue più il documento da cui viene. Questo ADR decide la forma in cui il design
system esiste perché `make check` se ne accorga.

Due cose lo distinguono da tutto ciò che il repository contiene: **non è Python**, e **lo stack con
cui le superfici lo useranno non è deciso** — è di M17.2, col suo ADR. La forma scelta qui non deve
presupporne nessuno.

## 1. La cartella: `apps/design-system/`, che §48 non prevede

§48 disegna `apps/desktop/` e `apps/ios/`, e aggiunge: «la struttura può evolvere, ma ogni modifica
architetturale significativa deve essere documentata». `apps/design-system/` è quella modifica, e
sta accanto al futuro `apps/command-center/` (`docs/STATO.md`, voce 5.10) perché è ciò che le
applicazioni condividono. `apps/README.md` la nomina, e `tests/design/test_documents.py` lo
verifica.

Dentro c'è JSON, CSS e HTML. **Nessun JavaScript**: la decisione dell'utente vieta quello di
libreria, e niente di ciò che M17.1 deve rendere ne richiede di proprio. Nessun passo di build,
nessun preprocessore, nessuna dipendenza: `uv.lock` non si muove.

## 2. `tokens.json` è la fonte, e tre file ne derivano per intero — il primo caso

`apps/design-system/tokens.json` è l'unica fonte. `scripts/generate_design_system.py` ne deriva:

| Derivato | Che cosa porta |
|---|---|
| `tokens.css` | le custom property, i due temi, la griglia per fascia, il bersaglio, il movimento ridotto, e una regola per ogni chiave delle tre liste di §4. È il file che ogni superficie collega |
| `specimen-switch.css` | ciò che serve solo alla pagina-campionario e non si può scrivere a mano: il tema a pagina intera, e una regola per ogni token che la pagina mostra come campione |
| `index.html` | la pagina-campionario, composta dai token e dai frammenti di `components/` |

`tests/design/test_generated.py` li riconfronta **byte per byte** a ogni `make check`, e
`--check` esce 1 se uno è stantio senza scrivere mai.

**È il primo caso, nel repository, di file generati per intero.** `generate_stato.py` e
`generate_architecture.py` sostituiscono *blocchi* fra marcatori dentro un documento scritto a mano,
perché quei documenti hanno una parte che nessun codice può derivare. Qui la ragione è opposta: la
registrazione di M17.1 nomina il rischio di «un campionario che dice altro da ciò che le superfici
usano», e quel rischio si chiude solo se la pagina **non ha una copia sua** né dei token né del
markup. Una pagina scritta a mano con un blocco generato dentro terrebbe a mano tutto il resto — i
frammenti ricopiati, le sezioni, gli `id` — e un test dovrebbe riconfrontare le liste nei due versi
per ogni cosa che ricopia. Generata per intero, la pagina collega gli stessi `tokens.css` e
`components.css` che collegheranno M12.5 e M17.2, e include i frammenti così come sono.

**Tre cose che CSS non sa fare** sono il motivo per cui tre specie di regola le scrive il generatore
e non una persona:

1. *Una media query non può leggere una custom property.* La griglia per fascia, il bersaglio sotto
   `pointer: coarse` e le durate sotto `prefers-reduced-motion: reduce` sono `@media` derivate. A
   mano, una `@media` può chiedere solo una larghezza uguale a un token di `breakpoint`, e un test
   la confronta.
2. *Una custom property che contiene `var()` si risolve dove è dichiarata.* Ogni blocco di tema
   riemette **tutto** ciò che è tematizzato — colori, ombre, elevazioni: definita solo in `:root`,
   un'elevazione resterebbe scura dentro un pannello chiaro.
3. *`:has()` legge un controllo e non imposta un attributo.* Il tema è `data-theme` su un antenato;
   il selettore a pagina intera del campionario, che è un `input` letto con `:has()`, non può
   raggiungere quei blocchi, e un selettore con l'`id` di un controllo della pagina non ha posto nel
   file che le superfici collegano. Da qui `specimen-switch.css`.

**La forma delle foglie.** `{"$value": …, "$type": …}`, e un alias si scrive `"{gruppo.nome}"`:
l'involucro e la sintassi degli alias vengono dal formato Design Tokens del W3C Community Group; i
valori no — lì un colore è un oggetto e una dimensione è `{value, unit}`, qui sono `#RRGGBB` e
`720px`. Il file non è conforme e non pretende di esserlo. Il nome di una custom property è
meccanico: `--ela-` più il percorso con i trattini, senza il segmento del tema.

Il generatore **valida** prima di derivare, e rifiuta con una frase: un alias che non risolve o
ciclico, chiavi diverse fra i due temi, un `$type` sconosciuto, un colore di `palette` non opaco,
chiavi che normalizzate collidono, uno stato che nomina una forma o un movimento che non esiste, un
font dichiarato il cui file manca (`tests/design/test_generator.py`).

## 3. Ciò che è scritto a mano legge token, e non scrive valori

`components.css`, i frammenti di `components/` e `specimen.css` sono scritti a mano.
`tests/design/test_tokens_only.py` rifiuta, nel valore di una dichiarazione: un colore letterale, in
ogni sua forma; un numero con unità di lunghezza, di tempo o d'angolo; **una curva** — `ease-in-out`
come `cubic-bezier()`: la decisione dice «durate ed easing da token», e la prima stesura della SPEC
difendeva solo le durate —; un numero nudo dove un token esiste; una funzione `gradient`; un `var()`
che `tokens.css` non definisce; un primitivo di `palette`, che salterebbe il tema; e, nella proprietà
`color`, un token che non sia di testo (§6).

Ciò che resta ammesso è **una lista chiusa dentro il test, una ragione per voce**, appuntata da un
test: è un'eccezione alla lettera della decisione («fallisce se ne trova») che l'utente ha accolto
nella review del 2026-09-18, con una clausola — **se supera la decina torna in review**.

**Nessun token è orfano.** Ogni custom property di `tokens.css` è letta da un file scritto a mano o
da una regola derivata di `tokens.css` stesso, e ogni primitivo di `palette` è l'alias di almeno un
colore semantico. I campioni della pagina **non contano** come lettori — renderebbero vera la regola
per costruzione —, ed è il motivo per cui le loro regole stanno in `specimen-switch.css` e non in
`specimen.css`. Un token entra quando qualcosa lo usa: è la regola di `CLAUDE.md` sugli stub, letta
per un file di token.

Il lettore di CSS è del test, scritto per il CSS che il repository scrive, e **rifiuta ciò che non
riconosce** invece di saltarlo: un lettore che salta in silenzio rende vacuo ogni controllo che ci
si appoggia.

## 4. Le tre liste esistono in un posto solo, e vengono dalla loro fonte

Gli stati di ELA, i livelli di rischio e i livelli di attenzione sono chiavi di `tokens.json`,
**alla lettera** quelle della loro fonte — «WAITING APPROVAL» con lo spazio, `HIGH` come
`RiskLevel.HIGH.value` —, così la lista nel file *è* la lista della fonte, senza una regola di
normalizzazione in mezzo. **La chiave è anche il testo che si mostra**: non c'è un secondo campo
che possa divergere. Il generatore normalizza solo dove CSS lo esige, nei nomi delle custom
property, e rifiuta due chiavi che normalizzate coincidono. Nel markup il valore viaggia alla
lettera: `data-ela-state="WAITING APPROVAL"`, `data-ela-risk="HIGH"`.

Una regola per chiave è **derivata** in `tokens.css`, e `components.css` legge le proprietà
generiche che quella regola imposta: le tre liste non compaiono in nessun file scritto a mano.

`tests/design/test_lists.py` le confronta con la fonte, in ordine e nei due versi:

- **gli stati** con i titoli di §6 del design, letti dal file;
- **il rischio** con `ela.domain.RiskLevel`; e un secondo test confronta l'enum con §29 del design,
  perché se un giorno divergessero il design system seguirebbe l'enum contraddicendo il documento —
  una domanda per l'utente, non per un token;
- **l'attenzione** con il blocco di §13 del design (§5).

Nessun lettore accetta un documento in cui la sua sezione manca o non dà nessuna voce.

**Il dominio non riceve niente.** `docs/STATO.md` (voce 5.10): gli stati di §6 del design sono una
proiezione, mai un valore di `src/ela/domain.py`. M17.1 non tocca `src/`, e un test appunta quali
nomi di §6 del design compaiono *già* in un enum del dominio, ciascuno con un altro significato, e
fallisce se ne entra uno nuovo. Lì serve una normalizzazione, ed è scritta: spazio e trattino basso
si equivalgono, altrimenti `ATTENTION_REQUIRED` non sarebbe mai «ATTENTION REQUIRED» e la difesa non
scatterebbe.

## 5. I nomi dei livelli di attenzione — una decisione

I livelli di attenzione si chiamano, in ordine: **SILENT, NOTIFICATION, PRIORITY, PHONE CALL,
EMERGENCY**.

Sono i nomi di §13 del design. §7 della spec chiama il terzo «PRIORITY NOTIFICATION», ma introduce
l'elenco con «per esempio»: non è una lista chiusa, e non viene contraddetta; §13 del design la
chiude. Deciso dall'utente nella review del 2026-09-18, punto 14, e scritto qui perché **chi
scriverà l'enum del dominio, nella Fase 15, eredita questi nomi**: quel giorno il test di §4 cambia
fonte — dal documento all'enum — e non valori. `tests/design/test_lists.py` appunta i cinque nomi
oltre a leggerli dal documento, così che una modifica a §13 del design non li cambi in silenzio.

## 6. I due temi, e un contrasto la cui soglia non si dichiara

Scuro in `:root`, chiaro con `data-theme="light"` su qualunque antenato: **lo accende solo
l'attributo**. Seguire `prefers-color-scheme` è una riga di ogni superficie, non del design system:
un'identità che cambia faccia con un'impostazione del telefono non è un default.

WCAG 2.1 AA è la regola. Le coppie primo piano–sfondo sono dichiarate in `tokens.json`, e
`tests/design/test_contrast.py` le calcola **nei due temi**. **La soglia non si dichiara: deriva dal
gruppo del colore in primo piano** — 4,5 per un colore di testo (criterio 1.4.3), 3 per ogni altro:
un ruolo di stato, di rischio o di attenzione, il bordo di un campo, l'anello del focus (criterio
1.4.11). La prima stesura faceva dichiarare il tipo alla coppia, ed era una leva: un testo
dichiarato «non testo» sarebbe passato a 3. Le soglie stanno nel test per la stessa ragione — una
regola che si abbassa cambiando un JSON non è una regola —, e il testo grande a 3:1, che le WCAG
ammettono, non entra: nessun testo ne ha bisogno. La metà che chiude il cerchio è in §3: la
proprietà `color` riceve solo token di testo.

Sono dichiarate **tutte** le combinazioni di un colore di testo e di un ruolo con ogni superficie;
le esenzioni sono nominate nel test con la ragione.

## 7. Il movimento, le forme, i bersagli, le fasce

- **Il movimento si ferma per costruzione.** Durate e curve sono token (§3). Sotto
  `prefers-reduced-motion: reduce` `tokens.css` porta ogni durata a zero, quindi ogni transizione si
  spegne perché legge un token; e una `animation` scritta a mano può stare solo dentro
  `@media (prefers-reduced-motion: no-preference)` (`tests/design/test_motion.py`).
- **Una forma è un insieme di parametri, non un disegno** — raggio, pieno o vuoto, stile del bordo,
  rotazione, scala, due lati che possono mancare, un punto interno. Ogni stato è l'alias di una
  forma, i parametri arrivano nella regola derivata dello stato, e una regola sola li legge. Una
  forma che nessuna regola realizza non può esistere, e non è un set di icone.
- **Mai il solo colore.** La chiave di uno stato è sempre testo, ed è lei che regge il criterio
  1.4.1. Colore e forma raggruppano: nessuna coppia di stati condivide l'uno e l'altra, confrontati
  sui **valori risolti** in ciascun tema (`tests/design/test_components.py`).
- **I bersagli.** Ogni elemento interattivo prende la dimensione minima da una custom property
  sola: 32 px col puntatore fine, **44 px sotto `pointer: coarse`**. Il criterio è il dito, non la
  larghezza: un iPhone in orizzontale resta un iPhone. 44 px è il numero della decisione
  dell'utente, e del criterio 2.5.5 delle WCAG, che è di livello AAA: le AA non ne hanno uno.
- **Le fasce sono tre, prima il telefono**: `phone`, `desktop-compact` da 720 px,
  `desktop-extended` da 1200 px. Corrispondono ai livelli di §19 del design senza costruirli:
  «desktop compatto» è la larghezza del livello Expanded, «desktop esteso» quella di Full, e il
  pannello del livello Compact cade nella fascia del telefono. Li costruisce M17.3.
- **Gli stati d'interazione** sono quelli del browser su elementi nativi. Ogni pseudo-classe ha una
  classe gemella **nella stessa lista di selettori**, perché il campionario la mostri ferma senza
  poter divergere.

## 8. Niente da fuori, niente che gira, niente disegni

Ogni riferimento di ogni `.html` e di ogni `.css` della cartella, derivati compresi, è un percorso
relativo che resta dentro la cartella e che esiste (`tests/design/test_no_network.py`). La stessa
proprietà la rende **rilocabile**: M12.5 e M17.2 la serviranno da dove vorranno. Nessun `<script>`,
nessun attributo `on*`, nessun `local()` in un `@font-face`.

L'identità minima è typography, palette e il wordmark tipografico «ELA». **Niente logo, niente
simbolo, nessuna icona** — difeso, non solo dichiarato: nella cartella esistono soltanto i tipi di
file di cui il design system è fatto, così un `logo.png` non ha dove stare, e nessuna pagina porta
un elemento che porti un'immagine (`tests/design/test_closed_world.py`). Dell'iconografia entrano
solo le regole. La palette è neutra e **senza un colore d'accento**: la tinta è riservata a ciò che
significa qualcosa — stato, rischio, attenzione —, ed è la lettura più stretta di §4 del design e
di §22 del design, che vieta lo stereotipo «neon viola + gradienti + orb luminoso».

## 9. Il font

*In bianco finché la prova a mano non è fatta.* La SPEC propone tre candidati — lo stack di sistema,
Inter, IBM Plex Sans —, la pagina-campionario li mostra affiancati, e sceglie l'utente, a occhio. Un
candidato che perde non entra mai in un commit: un binario in un commit resta nella storia per
sempre. Qui si scriverà quale ha vinto, con che versione e licenza, da dove viene il file, e perché
gli altri no. Il monospace è lo stack di sistema, senza un secondo file.

## 10. Il gate: perché `apps/` non entra in `CRITICAL_PACKAGES`

ADR 0028 §1: «**Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI.
Dove questo è falso, il package non deve contenere nessun ramo che decida qualcosa.**»

`apps/design-system/` **non ha rami**: è JSON, CSS e HTML, e nessun JavaScript. Non c'è niente che
la copertura possa misurare, e `CRITICAL_PACKAGES`, che elenca package di `ela`, non si muove.
L'unico codice che decide è il generatore, e sta in `scripts/`: lo vede `ruff`, non `mypy`
(`files = ["src"]`) né la copertura (`source = ["ela"]`), come `generate_stato.py`. ADR 0039 §1 ha
misurato le stesse righe di configurazione per `nodes/` e ne ha tratto il principio — dove vive il
codice è il livello di verifica —; qui il principio dice che il generatore è difeso dai suoi test e
dai loro negativi, e da nient'altro.

Le regole del design system **non entrano in `RULES`**: quel registro cammina `src/ela` con `ast`,
e qui non c'è Python da camminare. `CLAUDE.md` lo dice dalla review del 2026-09-18: le regole di ciò
che sta in `apps/` vivono nei test della loro cartella, e il README della cartella nomina ogni
regola col test che la difende — `tests/design/test_documents.py` chiude quella lista nei due versi.
Ogni controllo è una funzione pura con **un negativo per ogni modo di sbagliare**, nessuno scrive
nell'albero, e i negativi stanno in `tmp_path` o in una stringa (ADR 0041 §3).

Se un giorno `apps/design-system/` ricevesse codice che decide — JavaScript, per esempio — la
domanda del gate si riapre, e la riapre un ADR nuovo.

## Alternative considerate

- **Uno strumento di token** (Style Dictionary e simili) — porterebbe Node e una catena di build in
  un repository che non ne ha, per fare ciò che uno script di poche centinaia di righe fa senza
  dipendenze. La forma delle foglie lascia la porta aperta a M17.2, senza attraversarla.
- **Il CSS delle custom property scritto a mano, con un test che lo confronta col JSON** — due
  fonti e un arbitro. Derivare è la forma che il repository ha già scelto per `STATO.md`.
- **Una pagina-campionario scritta a mano** — terrebbe una copia del markup e delle liste: §2.
- **Le liste degli stati ricopiate in `components.css`**, una regola per stato scritta a mano — la
  forma che la decisione dell'utente vieta. Una regola generica più una derivata per chiave costa un
  livello di indirezione e toglie la lista da ogni file scritto a mano.
- **Una forma come disegno** (SVG, o una regola CSS per forma) — la prima è un'icona, che la
  decisione esclude; la seconda vorrebbe che una regola generica scegliesse un disegno da una custom
  property, e CSS non lo sa fare senza `@container style()`, che non è ovunque.
- **Il tipo di contrasto dichiarato dalla coppia**, e **le soglie in `tokens.json`** — due leve: §6.
- **Un enum del dominio per l'attenzione, adesso** — porterebbe valori che nessun percorso di
  produzione produce. I nomi si decidono qui; l'enum arriva con chi lo usa.
- **Un browser in CI**, per vedere la pagina — un'altra catena di strumenti, e un giudizio che resta
  d'occhio. La pagina la giudica la prova a mano.

## Conseguenze

- M12.5 e M17.2 collegano `tokens.css` e `components.css` e scrivono il markup dei frammenti. Un
  token che manca si aggiunge insieme a chi lo legge.
- Cambiare un colore, una durata, una soglia di larghezza è una riga di `tokens.json` e una
  rigenerazione; `make check` dice se il contrasto regge ancora nei due temi.
- Aggiungere uno stato a §6 del design fa fallire `make check` finché `tokens.json` non lo riceve,
  con un colore, una forma e un movimento — e viceversa.
- Il README della cartella è la lista viva delle regole e dei test; questo ADR non la ricopia.

### Vincoli dichiarati

- **Nessuna vista**: i componenti sono quelli che servono a entrambi i lettori già nominati, il
  companion e il Command Center. Ciò che serve a una vista sola arriva con quella vista.
- **Nessuna icona**: dell'iconografia entrano la griglia, l'area viva, il tratto e le dimensioni. Le
  icone arrivano con le viste che le usano.
- **Nessuno stack**: HTML e CSS senza framework. Lo stack del Command Center è di M17.2.
- **Nessun logo e nessun simbolo**: il wordmark è la parola, come testo. Nessuna favicon.
- **Il markup di un componente si ricopia**: il frammento è il contratto, ma una superficie scritta
  in un altro stack lo riesprime, e niente qui si accorge se diverge. È di M17.2.
- **Il contrasto verificato è quello delle coppie dichiarate**: un colore ereditato da una regola
  sopra uno sfondo impostato da un'altra un test statico non lo vede (§6).
- **Nessun browser gira in CI**: che la pagina appaia come deve lo dice solo la prova a mano, e solo
  per Safari.
- **Delle WCAG un test statico vede una parte**: contrasto, elementi nativi, movimento ridotto, la
  chiave come testo. Reflow, spaziatura del testo, ordine del focus e lettore di schermo no.
- **`tokens.json` non è nel formato Design Tokens del W3C**: ne ha l'involucro, non i valori (§2).
- **«Solo token» ammette una lista chiusa di letterali**: un'eccezione scritta e appuntata, che
  torna in review se supera la decina (§3).
- **Il design system non segue il tema del sistema operativo**: il tema chiaro lo accende solo
  l'attributo; seguire `prefers-color-scheme` è di ogni superficie (§6).
- **Il generatore del design system è al livello di verifica di `scripts/`**: né `mypy` né
  copertura (§10).
- **Il job Windows della CI non esegue `tests/design/`**: è un elenco nominato, e qui non c'è niente
  che dipenda dal sistema.
