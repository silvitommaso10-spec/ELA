# ELA — Design System

Le regole visive che ogni superficie di ELA eredita, l'identità minima di cui hanno bisogno, e una
pagina-campionario che le rende (M17.1, ADR 0042). Non è Python e non è un'applicazione: è JSON,
CSS e HTML, **senza JavaScript**, senza un passo di build e senza niente che si carichi dalla rete.

## Che cosa c'è

| File | Scritto | Che cos'è |
|---|---|---|
| `tokens.json` | a mano | **la fonte**: colori, typography, spazi, griglia, raggi, elevazioni, ombre, motion, breakpoint, bersagli, regole delle icone, wordmark, forme, e le tre liste — stati, rischio, attenzione |
| `tokens.css` | **derivato** | le custom property, i due temi, la griglia per fascia, il bersaglio, il movimento ridotto, e una regola per ogni chiave delle tre liste. È il file che ogni superficie collega |
| `components.css` | a mano | i componenti. Legge solo token |
| `components/*.html` | a mano | un frammento per componente: il markup canonico, con le sue varianti |
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

- **Il tema** è un attributo: scuro senza niente, chiaro con `data-theme="light"` su qualunque
  antenato. Un pannello chiaro sta dentro una pagina scura. Seguire l'impostazione del sistema è
  una scelta della superficie, non del design system.
- **Uno stato di ELA** è `data-ela-state="WAITING APPROVAL"` sull'elemento: la chiave è il titolo di
  §6 del design alla lettera, ed è anche il testo che si mostra. Il rischio è
  `data-ela-risk="HIGH"`, il valore che l'API già risponde; l'attenzione è
  `data-ela-attention="PHONE CALL"`. Le tre liste esistono solo in `tokens.json`: `components.css`
  non ne nomina nessuna.
- **Uno stato d'interazione** è quello del browser — `:hover`, `:focus-visible`, `:active`,
  `:disabled`, `aria-invalid="true"` — su elementi nativi. Le classi `.is-hover`,
  `.is-focus-visible`, `.is-active` esistono solo perché la pagina-campionario li mostri fermi.
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
| Il generatore rifiuta una fonte malformata, con una frase | `tests/design/test_generator.py` |
| Ciò che è scritto a mano legge token e non scrive valori: né un colore, né una lunghezza, né una durata, né un angolo, né una curva, né un gradiente. Ciò che resta ammesso è una lista chiusa, con una ragione per voce | `tests/design/test_tokens_only.py` |
| Nessun token è orfano, e i campioni della pagina non contano come lettori | `tests/design/test_tokens_only.py` |
| Gli stati sono i titoli di §6 del design, l'attenzione il blocco di §13 del design, il rischio l'enum `RiskLevel` — in ordine, letti dalla fonte; e nessun enum del dominio acquista uno stato di ELA | `tests/design/test_lists.py` |
| Questo README e `apps/README.md` dicono ciò che c'è | `tests/design/test_documents.py` |

### Niente da fuori, niente che gira, niente disegni

| Regola | La difende |
|---|---|
| Ogni riferimento di ogni pagina e di ogni foglio di stile è un percorso relativo, interno, esistente; nessun `<script>`, nessun `on*`, nessun `javascript:`, nessun `local()` | `tests/design/test_no_network.py` |
| Nella cartella esistono solo i tipi di file di cui il design system è fatto; nessuna pagina porta un'immagine, nessuna favicon; il wordmark è la parola «ELA», come testo | `tests/design/test_closed_world.py` |
| I file di `fonts/` sono esattamente quelli che `tokens.json` dichiara, nei due versi | `tests/design/test_fonts.py` |

### Accessibilità — WCAG 2.1 AA come regola

| Regola | La difende |
|---|---|
| Ogni coppia dichiarata regge la sua soglia **nei due temi**: 4,5 per un colore di testo (criterio 1.4.3), 3 per tutto il resto (criterio 1.4.11). La soglia deriva dal gruppo del colore, non si dichiara; sono dichiarate tutte le combinazioni con le superfici, meno le esenzioni nominate | `tests/design/test_contrast.py` |
| La proprietà `color` riceve solo token di testo | `tests/design/test_tokens_only.py` |
| Mai il solo colore (criterio 1.4.1): la chiave di uno stato, di un rischio, di un livello è sempre testo; due stati non condividono colore e forma, sui valori risolti | `tests/design/test_components.py` |
| Ogni stato d'interazione esiste, l'anteprima non può divergere, il focus si vede; elementi nativi; `id` unici, ogni `for` al suo campo | `tests/design/test_components.py` |
| Il movimento si ferma: ogni `animation` sta dentro `prefers-reduced-motion: no-preference`, e sotto `reduce` ogni durata è zero | `tests/design/test_motion.py` |
| Il testo è in `rem`, e quello di un campo non scende sotto `1rem` | `tests/design/test_responsive.py` |
| Un colore ereditato da una regola sopra uno sfondo impostato da un'altra; nessuno scorrimento orizzontale a 320 px; il testo al 200%; l'ordine del focus; un lettore di schermo | **solo la prova a mano** |

### Responsive

| Regola | La difende |
|---|---|
| Tre fasce, prima il telefono: `phone`, `desktop-compact`, `desktop-extended`. Una `@media` scritta a mano chiede solo una larghezza che è un breakpoint | `tests/design/test_responsive.py`, `tests/design/test_tokens_only.py` |
| La griglia di ogni fascia è derivata: una media query non può leggere una custom property | `tests/design/test_responsive.py` |
| Ogni elemento interattivo prende la dimensione minima da `--ela-target-min`: 32 px col puntatore fine, **44 px dove il puntatore è un dito** (`pointer: coarse`) — il criterio è il dito, non la larghezza | `tests/design/test_components.py` |
| Come la pagina appare, su quale schermo | **solo la prova a mano**: nessun browser gira in CI |

Le fasce corrispondono ai livelli di §19 del design senza costruirli: «desktop compatto» è la
larghezza del livello Expanded, «desktop esteso» quella del livello Full, e il pannello del livello
Compact cade nella fascia del telefono. Chi costruisce i livelli è M17.3.

### Iconografia — solo le regole

Una griglia di `icon.grid`, un'area viva che lascia `icon.live` di margine, un tratto di
`icon.stroke`, e le dimensioni di `icon.size`. La pagina le rende come geometria. **Nessuna icona è
disegnata qui**: le icone arrivano con le viste che le usano. Le forme dell'indicatore di stato non
sono icone: sono parametri (`shape` in `tokens.json`) che una regola sola legge.

## Che cosa non c'è

Nessuna vista, nessuna icona, nessuno stack, nessun logo e nessun simbolo (ADR 0042). Il markup dei
frammenti è il contratto, ma una superficie scritta in un altro stack lo riesprime, e niente qui si
accorge se diverge: è di M17.2.
