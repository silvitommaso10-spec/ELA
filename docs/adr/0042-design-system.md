# 0042. Il design system: una cartella che non è Python, un file di token da cui il resto deriva per intero, tre liste lette dalla loro fonte, e i nomi dei livelli di attenzione

- **Stato:** Proposta il **2026-09-18**, scritta **prima** della prova a mano di M17.1 (review
  dell'utente del 2026-09-18, punto 16: un commit con l'ADR in «Proposta», prima dei candidati del
  font). Diventa «Accettata» quando la prova a mano è passata — il percorso di ADR 0040 con la sua.
  SPEC di M17.1 approvata dall'utente il 2026-09-18. **Rivisto due volte, ancora in «Proposta»**:
  il 2026-09-18, quando al passo 2 della prova l'utente ha deciso che ELA è una sfera; e il
  2026-09-19, con la direzione visiva definitiva, il font e le tre revisioni aperte di
  §22 del design (§7, §8, §9), con ciò che il revisore ha corretto guardando la pagina nei due temi
  (§6), con l'esito del passo 2 della prova: una sfera più tridimensionale e un tema chiaro rifatto
  come materiale (§6, §7); e con le cinque correzioni del revisore perché la sfera legga come luce
  dentro un vetro e non come una bolla di vetro (§7).
- **Data:** 2026-09-18
- **Riferimenti spec:** §6, §7, §29, §48
- **Riferimenti design:** `docs/spec/ELA_design.md` — §6 del design, §13 del design,
  §19 del design, §21 del design, §22 del design, §23 del design, §24 del design,
  §29 del design, §34 del design, §35 del design.
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

**La direzione visiva è dell'utente**, con le sue parole: «stile Apple, futuristico stile JARVIS,
azzurro e bianco per tutto, premium». Il giorno prima, guardando la prima pagina-campionario: «ELA
deve sembrare una sfera, azzurra e bianca; una dashboard futuristica stile JARVIS ma senza
informazioni inutili; ELA deve apparire sul mio schermo come un widget». Il riferimento concreto —
una grammatica dei materiali e della sfera, e cinque schermate che la usano — l'ha preparato il
revisore e **non è nel repository**: qui è tradotto in token, generatore e componenti, con le regole
del design system.

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
| `index.html` | la pagina-campionario, composta dai token, dai frammenti di `components/` e dalle composizioni |

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
   riemette **tutto** ciò che è tematizzato — colori e ombre: definita solo in `:root`, un'ombra
   resterebbe scura dentro un pannello chiaro.
3. *`:has()` legge un controllo e non imposta un attributo.* Il tema è `data-theme` su un antenato;
   il selettore a pagina intera del campionario, che è un `input` letto con `:has()`, non può
   raggiungere quei blocchi, e un selettore con l'`id` di un controllo della pagina non ha posto nel
   file che le superfici collegano. Da qui `specimen-switch.css`.

E altre due, che CSS non sa fare. **Contare**: l'indice di un segmento del `meter` lo scrive il
generatore, e il segmento si accende confrontandolo con la posizione del livello nella sua lista. E
**leggere un token in un fotogramma chiave**: la banda di luce che attraversa la sfera passa in una
parte del suo ciclo che due durate decidono — il passaggio e la pausa —, e il suo `@keyframes` lo
deriva il generatore.

**La forma delle foglie.** `{"$value": …, "$type": …}`, e un alias si scrive `"{gruppo.nome}"`:
l'involucro e la sintassi degli alias vengono dal formato Design Tokens del W3C Community Group; i
valori no. Il file non è conforme e non pretende di esserlo. **Un colore semantico può avere
`$alpha`**, e il generatore lo compone in `#RRGGBBAA`: il vetro è bianco a bassa opacità, il testo
del corpo è bianco al 78%. **La palette resta opaca**: l'alpha è di chi usa un colore, non del
colore. Il nome di una custom property è meccanico: `--ela-` più il percorso con i trattini, senza
il segmento del tema.

**I frammenti si includono.** La sfera è sette strati di markup, e ogni componente che la mostra ne
porterebbe una copia: un frammento il cui nome comincia con `_` è un parziale, `{include:_orb}` lo
inserisce, e un parziale non ne include altri.

Il generatore **valida** prima di derivare, e rifiuta con una frase: un alias che non risolve o
ciclico, chiavi diverse fra i due temi, un `$type` sconosciuto, un colore di `palette` con l'alpha,
un alpha fuori da 0–1 o sopra un colore che ne ha già uno, chiavi che normalizzate collidono, uno
stato a cui manca una foglia o che nomina una luce, un nucleo o un movimento che non esiste, la
chiave di uno stato o di un livello colorata con qualcosa che non è un colore di testo
(`tests/design/test_generator.py`).

## 3. Ciò che è scritto a mano legge token, e non scrive valori

`components.css`, i frammenti di `components/` e `specimen.css` sono scritti a mano.
`tests/design/test_tokens_only.py` rifiuta, nel valore di una dichiarazione: un colore letterale, in
ogni sua forma — `color-mix()` compresa: dove il riferimento mescolava colori a mano, qui ci sono
token con l'alpha e l'opacità degli strati —; un numero con unità di lunghezza, di tempo o
d'angolo; **una curva** — `ease-in-out` come `cubic-bezier()`: la decisione dice «durate ed easing
da token», e la prima stesura della SPEC difendeva solo le durate —; un numero nudo dove un token
esiste; un `var()` che `tokens.css` non definisce; un primitivo di `palette`, che salterebbe il
tema; nella proprietà `color`, qualcosa che non sia un colore di testo (§6); e **un gradiente, un
`filter`, un `backdrop-filter` o un `mix-blend-mode` fuori da dove vivono** (§8).

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
l'attributo**. Seguire `prefers-color-scheme` è una riga di ogni superficie, non del design system.
Il tema chiaro esiste — Apple ha entrambi —, e la sua stanza è un bianco freddo. **Il tema chiaro è un
materiale, non un'inversione** — la prima stesura lo trattava come un'inversione, e l'utente l'ha
giudicato alla prova: «il tema chiaro non regge». La stanza chiara è un bianco freddo con la luce
dall'alto e una vignetta azzurra leggerissima; il testo è blu-notte, non nero; i pannelli sono vetro
bianco con un bordo e un'ombra grigio-blu, mai nera, come le finestre di macOS chiaro. **La
sfera**: il guscio è quasi trasparente, bianco al 12–16% con un bordo grigio-blu — un guscio scuro
sopra il bianco perde la trasparenza e fa della sfera una biglia grigia —; l'alone è la metà,
perché un alone su bianco sporca; l'ombra di contatto è grigio-blu. **La luce è la stessa tinta,
non lo stesso colore**: sul bianco è più satura e più scura, o sparirebbe. Un test verifica che ogni
parte della luce tenga la sua tinta da un tema all'altro entro sei gradi, e che nel chiaro non sia
mai più chiara; il guscio ha i suoi token sotto `light`, e nessun test lo confronta.

WCAG 2.1 AA è la regola. Le coppie primo piano–sfondo sono dichiarate in `tokens.json`, e
`tests/design/test_contrast.py` le calcola **nei due temi**. **La soglia non si dichiara: deriva dal
gruppo del colore in primo piano** — 4,5 per un colore di testo (criterio 1.4.3), 3 per ogni altro:
un segnale di stato, di rischio o di attenzione, il bordo di un campo, l'anello del focus (criterio
1.4.11). La prima stesura faceva dichiarare il tipo alla coppia, ed era una leva: un testo
dichiarato «non testo» sarebbe passato a 3. Le soglie stanno nel test per la stessa ragione — una
regola che si abbassa cambiando un JSON non è una regola. La metà che chiude il cerchio è in §3: la
proprietà `color` riceve solo colori di testo, e il generatore rifiuta la chiave di uno stato
colorata con altro.

**Un colore con l'alpha si compone prima di misurarlo.** Ciò che l'occhio vede è il colore *sopra
ciò che ha dietro*: lo sfondo di una coppia si compone sopra `surface.base`, e il primo piano sopra
lo sfondo composto. Il testo del corpo al 78% e le etichette al 55% sono misurati così, sulla
stanza e sul vetro.

Sono dichiarate **tutte** le combinazioni di un colore di testo e di un segnale con ogni superficie,
e ogni riempimento ha qualcosa sopra. **Le esenzioni hanno un nome e una ragione, nel test**: il
vetro e la luce della sfera e il suo alone — *non sono controlli, e il significato lo porta la
chiave a testo, che è misurata* —, la stanza, i pannelli di vetro, i fili di luce. Un gruppo di
colori che non è né misurato né esentato per nome fa fallire il test.

## 7. La sfera, gli stati, il movimento, i bersagli, le fasce

**La presenza di ELA è una sfera di luce tenuta nel vetro**, e la sua profondità è disegnata a
strati, dal fondo: un'ombra di contatto che la posa sul piano; un alone morbido; la metà lontana di
un'orbita di particelle e di un anello sottile, dietro il vetro; il guscio, con **un solo bordo
interno**, più scuro in alto a destra e quasi assente dove batte la luce; la luce dentro, **un
volume continuo** a due profondità — lontana (più grande, molto sfocata, più lenta, più scura) e
vicina (più piccola, più veloce) — che girano in versi opposti sopra un letto di luce, e sfumano
nel vetro senza un bordo; un nucleo bianco che respira e deriva lentamente su un'orbita piccola;
un'ombra che scurisce il vetro verso il basso a sinistra, lontano dalla luce; una banda chiara che
ogni tanto attraversa il vetro; una seconda luce in basso a destra, del colore dello stato; un
bordo di Fresnel sulla metà bassa della silhouette, più forte in basso; **il riflesso della
stanza**, in due: uno sheen largo e tenue, tangente alla curva del vetro, e un hot spot piccolo e
netto — entrambi **fermi** mentre tutto l'interno ruota, perché sono la luce della stanza ed è ciò
che rende leggibile la rotazione —; e la metà vicina delle orbite, davanti al vetro, con le
particelle come punti rotondi. Ombra, occlusione, le due luci, il Fresnel e il riflesso **non si
muovono**: col movimento ridotto la sfera resta tridimensionale. **Perché luce dentro un vetro e
non una bolla di vetro** — il giudizio del revisore sulla stesura precedente —: il riflesso era un
ovale bianco grande e opaco col bordo netto, e la luce interna due macchie; ora il riflesso è quasi
tutto sheen, e la luce un volume. È **geometria CSS**: nessun file d'immagine,
nessun SVG, e ogni colore, fermata, dimensione, durata e curva è un token. Tre misure: `sm` 24 px nelle righe e nel widget di M17.3, `md` 96 px, `lg` 220 px
nella home del Command Center. Il componente `presence` la rende con la chiave a testo; il
componente `state`, quello delle righe, **è la sfera `sm`** con la chiave accanto, e lì le orbite e
la banda, sotto il pixel, non si disegnano.

**La profondità è disegnata, non calcolata.** Un'orbita è un cerchio inclinato in un'ellisse, e la
stessa orbita è disegnata due volte: la metà lontana in uno strato dipinto prima del vetro, la metà
vicina in uno dopo, con due ritagli complementari fatti nel piano dell'orbita prima
dell'inclinazione. Così una particella sparisce dietro la sfera e riappare davanti. L'ordinamento 3D
del browser avrebbe fatto lo stesso con meno markup, ma un solo `filter`, `opacity` o `isolation`
su un antenato lo spegne in silenzio, e la sfera li usa tutti. L'inclinazione schiaccia tutto ciò
che l'orbita porta, e un punto uscirebbe come un trattino: ogni particella è un elemento rotondo
riallungato di `1 / cos(inclinazione)` — con la funzione trigonometrica di CSS, in Safari dalla
15.4 come `:has()` — che gira contro l'orbita alla sua stessa velocità, così l'allungamento resta
verticale nel piano dell'orbita e l'inclinazione lo riporta a un punto.

Il ritmo della sfera — la sua rotazione — è `spin`; l'anello sottile compare dove ELA lavora
(LISTENING, THINKING, PLANNING, WORKING, UPDATING, EVOLVING) e dove chiede l'utente (WAITING
APPROVAL, ATTENTION REQUIRED), dove sta fermo come il resto della luce; negli altri stati non c'è.
La banda di luce passa solo dove la luce gira.

**Lo stato è la luce**: il suo colore, il suo ritmo, la sua intensità — e il nucleo, e se la luce
gira o sta ferma. Tutto arriva nella regola derivata dello stato; `components.css` non nomina
nessuno stato.

| Stato | Luce | Ritmo | Nucleo |
|---|---|---|---|
| OFFLINE | grigio scuro, quasi spenta | ferma | spento |
| IDLE | azzurro | lento | respira |
| LISTENING | azzurro | lento | pulsa |
| THINKING | azzurro | veloce | respira |
| PLANNING | azzurro | medio | respira |
| WORKING | azzurro, col cuore bianco pieno | il più veloce | respira |
| WAITING | grigio | quasi ferma | respira |
| WAITING APPROVAL | ambra | ferma | respira |
| ATTENTION REQUIRED | arancio, l'alone dà due segnali | ferma | respira |
| ERROR | rosso | ferma | fioco |
| RECOVERING | ambra, più tenue | ferma | fermo |
| UPDATING | bianco-azzurro, quasi bianca | veloce | grande |
| EVOLVING | bianco-azzurro, quasi bianca | lento | grande |

**«Azzurro e bianco per tutto».** Tutto ciò che ELA fa è azzurro, più rapido quanto più lavora; ciò
che è fermo o assente è grigio; quando ELA cambia sé stessa la luce si fa quasi bianca, non verde.
**Le sole eccezioni sono gli stati che chiedono l'utente o segnalano un guasto** — ambra, arancio,
rosso —, e lì la luce **si ferma**: §35 del design vuole ELA «impossibile da fraintendere quando
necessita dell'utente». Rischio e attenzione hanno la stessa rampa: grigio, azzurro, ambra,
arancio, rosso.

- **Il movimento si ferma per costruzione.** Durate e curve sono token (§3), e il ritmo della sfera
  è una durata come le altre. Sotto `prefers-reduced-motion: reduce` `tokens.css` porta ogni durata
  a zero, e una `animation` scritta a mano può stare solo dentro
  `@media (prefers-reduced-motion: no-preference)` (`tests/design/test_motion.py`). La luce sta
  ferma, e il colore e la parola sotto dicono ancora tutto.
- **Mai il solo colore, mai il solo movimento.** La chiave di uno stato è sempre testo, ed è lei che
  regge il criterio 1.4.1: prende l'ambra, l'arancio o il rosso dello stato come *colore di testo*,
  a 4,5. Nessuna coppia di stati ha la stessa luce, confrontata sui **valori risolti** in ciascun
  tema (`tests/design/test_components.py`).
- **I bersagli.** Ogni elemento interattivo prende la dimensione minima da una custom property
  sola: 32 px col puntatore fine, **44 px sotto `pointer: coarse`**. Il criterio è il dito, non la
  larghezza. 44 px è il numero della decisione dell'utente, e del criterio 2.5.5 delle WCAG, che è
  di livello AAA: le AA non ne hanno uno.
- **Le fasce sono tre, prima il telefono**: `phone`, `desktop-compact` da 720 px,
  `desktop-extended` da 1200 px. Corrispondono ai livelli di §19 del design senza costruirli:
  «desktop compatto» è la larghezza del livello Expanded, «desktop esteso» quella di Full, e il
  pannello del livello Compact cade nella fascia del telefono. Li costruisce M17.3.
- **Gli stati d'interazione** sono quelli del browser su elementi nativi. Ogni pseudo-classe ha una
  classe gemella **nella stessa lista di selettori**, perché il campionario la mostri ferma senza
  poter divergere.

## 8. I materiali, e le tre revisioni aperte di §22 del design

**I materiali sono due.** *Il vetro*: bianco a bassa opacità, un bordo bianco al 10%, un filo di
luce interno in alto, ciò che sta dietro sfocato e saturato, un'ombra profonda — nelle varianti
base, morbida e calda, la calda per un'approvazione, con bordo e alone ambra. Il componente `panel`
è questo. *La stanza*: quasi nero blu, con due luci fredde radiali dall'alto e dal basso e un
chiarore al centro; è lo sfondo di ogni superficie. Angoli da 24 px per i pannelli, 14 px per i
controlli, 999 px per le pillole. La tipografia: `display`, `title`, `body` al 78% di bianco,
`eyebrow` maiuscolo e spaziato al 55%, e il wordmark con un tracking largo e una luce azzurra
dietro. I componenti che il riferimento ha chiesto: `pill`, `step`, `meter`, `tile`, e
un'azione primaria che è un gradiente azzurro con un'ombra colorata e il testo scuro.

**Niente da fuori, niente che gira, niente disegni** — questo non cambia. Ogni riferimento di ogni
`.html` e di ogni `.css` della cartella è un percorso relativo, interno, esistente
(`tests/design/test_no_network.py`), e la cartella è **rilocabile**. Nessun `<script>`. Nella
cartella esistono soltanto i tipi di file di cui il design system è fatto, e nessuna pagina porta
un elemento che porti un'immagine (`tests/design/test_closed_world.py`): **la sfera non li aggira**,
perché è CSS e non un file. Le due icone del riferimento — la spunta di un passo, il microfono — non
sono entrate: il passo «fatto» è un anello con un punto, e il pulsante ha una parola. Dell'iconografia
entrano solo le regole.

§22 del design chiede un'identità che non cada nello stereotipo «AI = neon viola + gradienti + orb
luminoso». La direzione scelta lo tocca in tre punti, e **ciascuno è rivisto apertamente, non
aggirato**:

1. **L'orb.** La presenza di ELA è una sfera luminosa. *La scelta è dell'utente, ed è consapevole
   di quella frase*: la sfera è l'identità di ELA — ciò che §5 del design chiama la sua presenza —,
   non un ornamento, ed è ciò che §35 del design chiede: bella quando non fa nulla, chiara quando
   fa qualcosa, impossibile da fraintendere quando ha bisogno dell'utente. Niente viola, niente
   neon: vetro scuro e luce azzurra.
2. **I gradienti.** La prima stesura li vietava ovunque. Ora **vivono in tre posti e in nessun
   altro** — la presenza, i materiali, l'azione primaria —, **ogni fermata è un token**, e
   `filter`, `backdrop-filter` e `mix-blend-mode` vivono solo nella presenza e nei materiali.
   `tests/design/test_tokens_only.py` ammette un gradiente solo se *ogni* selettore della regola è
   di uno di quei posti, e dentro il gradiente cerca i letterali come altrove.
3. **Il colore d'identità.** La prima stesura non aveva nessun accento. Ora ce n'è **uno**,
   l'azzurro con il bianco, ed è di tutto ciò che è ELA: la sfera, la luce di ogni stato in cui ELA
   lavora, l'azione primaria. Le altre tinte sono tre, e significano una cosa sola — ELA ha
   bisogno di te, o qualcosa si è rotto.

## 9. Il font

**Lo stack di sistema**: `system-ui, -apple-system, "Segoe UI", sans-serif`. Deciso dall'utente il
2026-09-19.

«Stile Apple» vuol dire San Francisco su Mac e su iPhone, e lo stack di sistema è **l'unico modo
lecito di averlo**: San Francisco non è ridistribuibile, e non si può includere. Su Windows lo stack
è Segoe UI, che è la sua controparte nativa. Il costo è scritto: tre dispositivi, due facce — ed è
il costo di essere nativi su ciascuno.

La SPEC proponeva tre candidati, e la pagina-campionario li ha mostrati affiancati al passo 2 della
prova a mano: lo stack di sistema, **Inter** 4.1 e **IBM Plex Sans** 1.1.0, entrambi SIL OFL 1.1,
presi dai rilasci upstream come WOFF2 non modificati, con la licenza e lo SHA-256 accanto. **Nessun
`.woff2` è mai entrato in un commit**: i candidati sono vissuti nell'albero di lavoro e ne sono
usciti con il ramo del generatore che li rendeva, perché un binario in un commit resta nella storia
per sempre. `tests/design/test_fonts.py` tiene le due affermazioni che restano vere a zero file:
nessun candidato nella fonte, nessun file di font nella cartella. Il monospace è lo stack di
sistema.

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
  un repository che non ne ha, per fare ciò che uno script fa senza dipendenze.
- **Il CSS delle custom property scritto a mano, con un test che lo confronta col JSON** — due
  fonti e un arbitro. Derivare è la forma che il repository ha già scelto per `STATO.md`.
- **Una pagina-campionario scritta a mano** — terrebbe una copia del markup e delle liste: §2.
- **Le liste degli stati ricopiate in `components.css`**, una regola per stato scritta a mano — la
  forma che la decisione dell'utente vieta.
- **La sfera come immagine, come SVG o come video** — sarebbe un file che nessun test può
  rileggere; e non saprebbe cambiare luce, ritmo e intensità da una custom property. In CSS è fatta
  degli stessi token del resto.
- **`color-mix()` per sfumare la luce**, come nel riferimento — è un colore scritto a mano dentro
  una funzione. I token con l'alpha e l'opacità degli strati fanno lo stesso lavoro, e restano token.
- **Un font incluso nel repository** (Inter, IBM Plex Sans) — provati e scartati: §9.
- **Il tipo di contrasto dichiarato dalla coppia**, e **le soglie in `tokens.json`** — due leve: §6.
- **Un enum del dominio per l'attenzione, adesso** — porterebbe valori che nessun percorso di
  produzione produce. I nomi si decidono qui; l'enum arriva con chi lo usa.
- **Un browser in CI**, per vedere la pagina — un'altra catena di strumenti, e un giudizio che resta
  d'occhio. La pagina la giudica la prova a mano.

## Conseguenze

- M12.5 e M17.2 collegano `tokens.css` e `components.css` e scrivono il markup dei frammenti. Un
  token che manca si aggiunge insieme a chi lo legge.
- Cambiare un colore, una durata, una fermata della luce è una riga di `tokens.json` e una
  rigenerazione; `make check` dice se il contrasto regge ancora nei due temi.
- Aggiungere uno stato a §6 del design fa fallire `make check` finché `tokens.json` non lo riceve,
  con la sua luce, il suo ritmo e il suo nucleo — e viceversa.
- **Le composizioni** — la home, un'approvazione, il widget compatto, l'iPhone — ricostruiscono
  quattro schermate con i soli componenti, e un test verifica che non usino nessuna classe che
  `components.css` non definisce. **Non sono viste**: quelle sono di M17.2 e di M12.5. Sono la prova
  che i componenti bastano a comporle.
- Il README della cartella è la lista viva delle regole e dei test; questo ADR non la ricopia.

### Vincoli dichiarati

- **Nessuna vista**: i componenti sono quelli che servono a entrambi i lettori già nominati, il
  companion e il Command Center, e quelli che le composizioni hanno chiesto. Le composizioni non
  sono viste.
- **Nessuna icona**: dell'iconografia entrano la griglia, l'area viva, il tratto e le dimensioni. Le
  icone arrivano con le viste che le usano.
- **Nessuno stack**: HTML e CSS senza framework. Lo stack del Command Center è di M17.2.
- **Nessun logo e nessun simbolo**: il wordmark è la parola, come testo, e la sfera è geometria CSS
  del componente `presence`: nessun file d'immagine, nessun SVG, nessuna favicon.
- **Il markup di un componente si ricopia**: il frammento è il contratto, ma una superficie scritta
  in un altro stack lo riesprime, e niente qui si accorge se diverge. È di M17.2.
- **Il contrasto verificato è quello delle coppie dichiarate**: un colore ereditato da una regola
  sopra uno sfondo impostato da un'altra un test statico non lo vede (§6).
- **La sfera e i materiali sono esentati dal contrasto**: il vetro, la luce e l'alone non sono
  controlli, e il significato lo porta la chiave a testo, che è misurata (§6).
- **La profondità della sfera è disegnata, non calcolata**: la metà lontana di un'orbita è uno strato
  dipinto prima del vetro e la metà vicina uno dopo, con due ritagli complementari; nessun
  ordinamento 3D del browser, che un `filter`, un'`opacity` o un'`isolation` su un antenato
  spegnerebbero in silenzio (§7).
- **Con il movimento ridotto più stati di ELA al lavoro si somigliano**: IDLE, LISTENING, THINKING
  e PLANNING hanno la stessa luce azzurra e si distinguono dal ritmo; a luce ferma li distingue la
  parola sotto (§7).
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
