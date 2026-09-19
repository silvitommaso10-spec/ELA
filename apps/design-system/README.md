# ELA — Design System

Le regole visive che ogni superficie di ELA eredita, l'identità di cui hanno bisogno, e una
pagina-campionario che le rende (M17.1, ADR 0042). Non è Python e non è un'applicazione: è JSON,
CSS e HTML, **senza JavaScript**, senza un passo di build e senza niente che si carichi dalla rete.

## La direzione

Con le parole dell'utente: **«stile Apple, futuristico stile JARVIS, azzurro e bianco per tutto,
premium»**. E, il giorno prima: «ELA deve sembrare una sfera, azzurra e bianca; una dashboard
futuristica stile JARVIS ma senza informazioni inutili; ELA deve apparire sul mio schermo come un
widget».

- **ELA è una sfera di luce tenuta nel vetro**, e la sua profondità è disegnata a strati: un'ombra
  di contatto, un alone, il guscio, la luce a due profondità che gira in versi opposti, un nucleo
  che respira e deriva, un'occlusione lontano dalla luce, una banda che ogni tanto spazza il vetro,
  due luci — il riflesso della stanza in alto a sinistra, **fermo**, e una luce dello stato in basso
  a destra —, un bordo di Fresnel, e particelle e un anello su un'orbita inclinata che passano
  dietro il vetro e davanti. Geometria CSS, non un'immagine; l'ordine degli strati è in
  `components/_orb.html`, dal fondo.
- **Lo stato è la luce**: il suo colore, il suo ritmo, la sua intensità — e **sempre la chiave, a
  testo**. Azzurro per tutto ciò che ELA fa, più rapido quanto più lavora; grigio quando è ferma o
  assente; quasi bianca quando cambia sé stessa. Ambra, arancio e rosso **solo** quando ELA ha
  bisogno di te o qualcosa si è rotto — e lì la luce si ferma.
- **I materiali sono due**: il vetro (bianco a bassa opacità, un filo di luce in alto, ciò che sta
  dietro sfocato) e la stanza (quasi nero blu, con due luci fredde). **Il tema chiaro è un
  materiale, non un'inversione**: una stanza di bianco freddo con la luce dall'alto, il testo
  blu-notte, il vetro bianco con bordo e ombra grigio-blu. La sfera lì ha un guscio quasi
  trasparente e metà alone, e la sua luce è **la stessa tinta**, più satura e più scura — sul
  bianco, l'azzurro del tema scuro sparirebbe.
- **Il font è lo stack di sistema**: San Francisco su Mac e iPhone — è l'unico modo lecito di
  averlo —, Segoe UI su Windows.

§22 del design mette in guardia dallo stereotipo «neon viola + gradienti + orb luminoso». La
direzione lo tocca in tre punti, e ADR 0042 li registra come **tre revisioni aperte**, non aggirate:

1. **l'orb** — la sfera è l'identità di ELA, e l'utente l'ha scelta consapevolmente; niente viola,
   niente neon;
2. **i gradienti** — vivono in tre posti e in nessun altro (la sfera, i materiali, l'azione
   primaria), e ogni fermata è un token;
3. **il colore d'identità** — è uno, l'azzurro col bianco; le altre tre tinte significano una cosa
   sola.

## Che cosa c'è

| File | Scritto | Che cos'è |
|---|---|---|
| `tokens.json` | a mano | **la fonte**: palette, colori semantici nei due temi, typography, spazi, griglia, raggi, materiali, motion, breakpoint, bersagli, regole delle icone, wordmark, la sfera (`presence`), e le tre liste — stati, rischio, attenzione |
| `tokens.css` | **derivato** | le custom property, i due temi, la griglia per fascia, il bersaglio, il movimento ridotto, e una regola per ogni chiave delle tre liste. È il file che ogni superficie collega |
| `components.css` | a mano | i componenti. Legge solo token |
| `components/*.html` | a mano | un frammento per componente: il markup canonico, con le sue varianti. Un nome che comincia con `_` è un **parziale** — `_orb.html`, i sette strati della sfera —, e `{include:_orb}` lo inserisce |
| `components/compositions/*.html` | a mano | quattro schermate ricostruite **con i soli componenti**: la home, un'approvazione, il widget, l'iPhone. Non sono viste: sono la prova che i componenti bastano |
| `specimen.css` | a mano | il layout della sola pagina-campionario. Legge solo token |
| `specimen-switch.css` | **derivato** | ciò che serve solo alla pagina e non si può scrivere a mano: il tema a pagina intera, e una regola per ogni token che la pagina mostra come campione |
| `index.html` | **derivato** | la pagina-campionario |

I file derivati li scrive `scripts/generate_design_system.py`, per intero, e non si toccano:

```
uv run python scripts/generate_design_system.py            # riscrive i derivati
uv run python scripts/generate_design_system.py --check    # esce 1 se uno è stantio
```

`make check` li riconfronta byte per byte: un token cambiato senza rigenerare fallisce.

## Come si usa da una superficie

Si collegano `tokens.css` e poi `components.css`, e si scrive il markup dei frammenti. Tutti i
riferimenti sono relativi e restano dentro la cartella: la si può servire da dove si vuole.

- **Lo sfondo è la stanza**: `class="ela-room"` sull'elemento che fa da pagina. **Un contenitore è
  vetro**: `ela-panel`, con `--soft`, `--warm` (un'approvazione), `--inset`, `--pill` (il widget).
- **Il tema** è un attributo: scuro senza niente, chiaro con `data-theme="light"` su qualunque
  antenato. Seguire l'impostazione del sistema è una scelta della superficie.
- **La presenza** è `ela-presence` con dentro la sfera e la chiave: `--lg` è la home del Command
  Center, senza modificatore è l'iPhone e un'approvazione, `--sm` è il widget. **Lo stato da solo**
  è `ela-state`: la sfera piccola e la chiave accanto. **Una riga** di un task o di un nodo è
  `ela-row`, con `data-ela-state` sulla riga: la sfera piccola, che cos'è e come sta («MacBook ·
  Active»), e in coda la chiave dello stato di ELA.
- **Uno stato di ELA** è `data-ela-state="WAITING APPROVAL"` sull'elemento: la chiave è il titolo di
  §6 del design alla lettera, ed è anche il testo che si mostra. Il rischio è
  `data-ela-risk="HIGH"`, il valore che l'API già risponde; l'attenzione è
  `data-ela-attention="PHONE CALL"`. Le tre liste esistono solo in `tokens.json`: `components.css`
  non ne nomina nessuna.
- **Uno stato d'interazione** è quello del browser — `:hover`, `:focus-visible`, `:active`,
  `:disabled`, `aria-invalid="true"` — su elementi nativi. Le classi `.is-hover`,
  `.is-focus-visible`, `.is-active` esistono solo perché la pagina-campionario li mostri fermi.
- **Un colore semantico può avere l'alpha** (`$alpha` in `tokens.json`); la palette resta opaca.
- **Un token entra quando qualcosa lo usa.** Se serve un passo di spaziatura che non c'è, si
  aggiunge a `tokens.json` insieme a chi lo legge, e si rigenera.

## Come si apre la pagina

Da disco, in Safari: `open -a Safari apps/design-system/index.html`. Per vederla dall'iPhone si
serve la cartella, e solo quella, sull'indirizzo della tailnet, finché serve:

```
uv run python -m http.server 8171 --bind "$(tailscale ip -4)" --directory apps/design-system
```

Non è il modo in cui l'iPhone raggiungerà ELA: quello è di M12.5.

## Le regole, e che cosa le difende

Una regola senza un test che possa fallire è decorazione. Ogni regola qui sotto nomina il test che
la difende; dove un test non può arrivare, lo dice.

### La fonte è una

| Regola | La difende |
|---|---|
| Ogni derivato è, byte per byte, ciò che il generatore produce | `tests/design/test_generated.py` |
| Il generatore rifiuta una fonte malformata, con una frase: un alias che non risolve, un alpha sulla palette o fuori da 0–1, uno stato senza la sua luce, la chiave di uno stato colorata con qualcosa che non è un colore di testo | `tests/design/test_generator.py` |
| Ciò che è scritto a mano legge token e non scrive valori: né un colore — `color-mix()` compresa —, né una lunghezza, né una durata, né un angolo, né una curva. Ciò che resta ammesso è una lista chiusa, con una ragione per voce | `tests/design/test_tokens_only.py` |
| **Un gradiente vive in tre posti e in nessun altro** — la presenza (`.ela-orb`, `.ela-presence`), i materiali (`.ela-room`, `.ela-panel`), l'azione primaria — e ogni fermata è un token. **`filter`, `backdrop-filter` e `mix-blend-mode`** vivono solo nella presenza e nei materiali | `tests/design/test_tokens_only.py` |
| Nessun token è orfano, e i campioni della pagina non contano come lettori | `tests/design/test_tokens_only.py` |
| Gli stati sono i titoli di §6 del design, l'attenzione il blocco di §13 del design, il rischio l'enum `RiskLevel` — in ordine, letti dalla fonte; e nessun enum del dominio acquista uno stato di ELA | `tests/design/test_lists.py` |
| Questo README, `apps/README.md` e ADR 0042 dicono ciò che c'è, e la direzione è scritta con le parole dell'utente | `tests/design/test_documents.py` |

### Niente da fuori, niente che gira, niente disegni

| Regola | La difende |
|---|---|
| Ogni riferimento di ogni pagina e di ogni foglio di stile è un percorso relativo, interno, esistente; nessun `<script>`, nessun `on*`, nessun `javascript:`, nessun `local()` | `tests/design/test_no_network.py` |
| Nella cartella esistono solo i tipi di file di cui il design system è fatto; nessuna pagina porta un'immagine, nessuna favicon; il wordmark è la parola «ELA», come testo. **La sfera non li aggira: è CSS** | `tests/design/test_closed_world.py` |
| Il font è lo stack di sistema: nessun candidato è rimasto nella fonte, nessun file di font nella cartella | `tests/design/test_fonts.py` |

### Accessibilità — WCAG 2.1 AA come regola

| Regola | La difende |
|---|---|
| Ogni coppia dichiarata regge la sua soglia **nei due temi**: 4,5 per un colore di testo (criterio 1.4.3), 3 per tutto il resto (criterio 1.4.11). La soglia deriva dal gruppo del colore, non si dichiara. **Un colore con l'alpha si compone sopra ciò che ha dietro prima di misurarlo.** Sono dichiarate tutte le combinazioni con le superfici; **le esenzioni hanno un nome e una ragione nel test** — la sfera e il suo alone non sono controlli, e il significato lo porta la chiave a testo; la stanza, il vetro e i fili di luce sono decorazione | `tests/design/test_contrast.py` |
| La luce della sfera tiene la sua tinta da un tema all'altro, entro sei gradi, e nel chiaro non è mai più chiara; il guscio ha i suoi token per tema, e nessun test lo confronta | `tests/design/test_contrast.py` |
| La proprietà `color` riceve solo colori di testo | `tests/design/test_tokens_only.py` |
| Mai il solo colore, mai il solo movimento (criterio 1.4.1): la chiave di uno stato, di un rischio, di un livello è sempre testo; due stati non hanno la stessa luce, sui valori risolti; ogni stato mostra la sfera nelle tre misure | `tests/design/test_components.py` |
| Ogni stato d'interazione esiste, l'anteprima non può divergere, il focus si vede; elementi nativi; `id` unici, ogni `for` al suo campo; **un campo riempie il suo contenitore**, e quanto può allargarsi è un token; una riga si legge da sinistra: la sfera, che cos'è, e in coda la chiave di ELA | `tests/design/test_components.py` |
| Il movimento si ferma: ogni `animation` sta dentro `prefers-reduced-motion: no-preference`, e sotto `reduce` ogni durata è zero — anche il ritmo della sfera, che è una durata. La luce sta ferma, e il colore e la parola sotto dicono ancora tutto | `tests/design/test_motion.py` |
| Ciò che fa la sfera rotonda **non si muove mai**: l'ombra di contatto, l'occlusione, le due luci, il Fresnel, il guscio — col movimento ridotto la sfera resta tridimensionale. La luce vicina gira più in fretta della lontana, e in verso opposto; la banda passa in una parte del ciclo che due durate decidono | `tests/design/test_motion.py` |
| Gli strati della sfera sono in ordine di profondità: la metà lontana delle orbite prima del vetro, quella vicina dopo | `tests/design/test_components.py` |
| Il testo è in `rem`, e quello di un campo non scende sotto `1rem` | `tests/design/test_responsive.py` |
| Con il movimento ridotto più stati di ELA al lavoro si somigliano, e li distingue la parola; un colore ereditato da una regola sopra uno sfondo impostato da un'altra; nessuno scorrimento orizzontale a 320 px; il testo al 200%; l'ordine del focus; un lettore di schermo | **solo la prova a mano** |

### Responsive

| Regola | La difende |
|---|---|
| Tre fasce, prima il telefono: `phone`, `desktop-compact`, `desktop-extended`. Una `@media` scritta a mano chiede solo una larghezza che è un breakpoint | `tests/design/test_responsive.py`, `tests/design/test_tokens_only.py` |
| La griglia di ogni fascia è derivata: una media query non può leggere una custom property | `tests/design/test_responsive.py` |
| La barra della pagina resta in alto, e una sezione a cui porta un link si ferma sotto di lei: l'altezza della barra è nota perché nessuna delle sue due righe va a capo | `tests/design/test_responsive.py` |
| Ogni elemento interattivo prende la dimensione minima da `--ela-target-min`: 32 px col puntatore fine, **44 px dove il puntatore è un dito** (`pointer: coarse`) — il criterio è il dito, non la larghezza | `tests/design/test_components.py` |
| **I componenti bastano**: una composizione non usa nessuna classe che `components.css` non definisca; un `meter` ha un segmento per ogni livello | `tests/design/test_components.py` |
| La pagina mostra ogni stato una volta, in `md`, e ogni misura una volta, a riposo; e non tiene più sfere di quante un iPhone ne faccia girare | `tests/design/test_components.py` |
| Come la pagina appare, su quale schermo, e se scorre senza scatti con tutte le sue sfere | **solo la prova a mano**: nessun browser gira in CI |

Le fasce corrispondono ai livelli di §19 del design senza costruirli: «desktop compatto» è la
larghezza del livello Expanded, «desktop esteso» quella del livello Full, e il pannello del livello
Compact cade nella fascia del telefono. Chi costruisce i livelli è M17.3.

### Iconografia — solo le regole

Una griglia di `icon.grid`, un'area viva che lascia `icon.live` di margine, un tratto di
`icon.stroke`, e le dimensioni di `icon.size`. La pagina le rende come geometria. **Nessuna icona è
disegnata qui**: le icone arrivano con le viste che le usano. Il segno di un passo del piano — un
anello con un punto, un disco pieno, un anello vuoto — non è un'icona: è geometria CSS del
componente `step`, e dice lo stato del passo anche senza colore.

## Che cosa non c'è

Nessuna vista, nessuna icona, nessuno stack, nessun logo e nessun simbolo (ADR 0042). Le
composizioni non sono viste. Il markup dei frammenti è il contratto, ma una superficie scritta in un
altro stack lo riesprime, e niente qui si accorge se diverge: è di M17.2.
