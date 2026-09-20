# ELA — le pagine dell'iPhone

Fase 12 — il companion iPhone (spec §6, §48; M12.5, ADR 0043). Qui ci sono **i modelli delle
pagine** che `ela.api` compone e serve al browser del telefono, e la guida per arruolarlo.

Non è un'applicazione e non è Python: sono file HTML con delle fessure — `{nome}` — che il
compositore riempie **sempre passando da `html.escape`**. L'aspetto è quello di
`apps/design-system/` (ADR 0042): i modelli usano le sue classi e non ne inventano, e la sfera si
**include** da `components/_orb.html` invece di ricopiarla.

## Le regole di questa cartella, e il test che le tiene

Le regole di ciò che sta in `apps/` non camminano Python: vivono nei test della loro cartella.

| Regola | Test |
|---|---|
| Nessun modello contiene uno `<script>`, un attributo `on*`, un `javascript:`, un `<iframe>`, un `<object>`, un `<embed>` o un `<base>` | `tests/ios/test_templates.py` |
| Ogni classe usata è una che `components.css` definisce | `tests/ios/test_templates.py` |
| Il `<title>` è «ELA» e basta: la cronologia di un browser viaggia | `tests/ios/test_templates.py` |
| Ogni `href` e ogni `action` è una rotta del companion; gli id viaggiano nella query, mai nel percorso | `tests/ios/test_templates.py` |
| I modelli e il codice che li riempie sono un mondo chiuso nei due versi | `tests/ios/test_templates.py` |
| Ogni fessura è un nome minuscolo che il compositore sa vedere | `tests/ios/test_templates.py` |
| Ogni pagina risponde con la `Content-Security-Policy` che vieta gli script, e i valori dell'utente arrivano con l'escape | `tests/api/test_companion.py` |

La prima e l'ultima riga sono le **due difese di «niente JavaScript»**, e non sono la stessa cosa
detta due volte: se un giorno un valore sfuggisse all'escape, il browser si rifiuterebbe comunque
di eseguirlo.

## Arruolare il telefono

1. **Al Mac**, conia il codice del companion:

   ```
   ela node enroll --privacy TRUSTED --role companion
   ```

   Il codice dura **dieci minuti**, si usa una volta sola, e si copia con un doppio clic sulla
   cella `CODE` della tabella.

2. **Sull'iPhone**, apri `http://<indirizzo del Mac sulla tailnet>:8130/companion/` **nel browser
   predefinito del telefono** — quello che si apre quando tocchi un collegamento —, incolla il
   codice nel modulo, lascia «IOS» nel campo Sistema, e invia. Da lì in poi il browser porta la
   sua credenziale in un cookie e la pagina si apre da sola.

   **Perché proprio il browser predefinito:** lo Shortcut e il tocco di una notifica aprono
   *quello*, e un cookie messo in un altro browser lì non si vede. Su questo iPhone il predefinito
   è Chrome.

3. **Lo Shortcut**, per aprire la pagina senza digitare l'indirizzo. In Comandi: un'azione sola,
   **«Apri URL»**, con l'indirizzo del passo 2. **Chiamalo «Cruscotto»**: è il nome misurato che
   Siri riconosce anche a telefono bloccato — chiede il codice di sblocco e poi apre. «ELA» da solo
   Siri non lo capisce, e «esegui ELA prova» funziona solo a telefono sbloccato.

   Lo Shortcut **non contiene nessun segreto**: apre un indirizzo, e la credenziale è quella del
   browser. Condividerlo, esportarlo o sincronizzarlo non porta con sé niente.

## Che cosa sapere, detto una volta

- **Cambiare il browser predefinito vuol dire riarruolarsi**: il cookie sta nel browser in cui
  l'hai messo.
- **Con Chrome la cronologia e le schede possono sincronizzarsi sull'account Google.** Per questo
  gli indirizzi del companion non portano mai uno scopo o un nome: al più un id opaco.
- **L'app web della schermata Home resta fuori scope**: copia i cookie quando la aggiungi e poi li
  tiene separati, quindi non vede né una revoca né un riarruolamento.
- **La pagina di arruolamento è senza stile.** I fogli stanno dietro l'identità come tutto il
  resto: chi non è ancora nessuno non li carica.
- **Un task `LOCAL_ONLY` non si risponde dal telefono**: la pagina mostra la capability, il rischio
  e le ore, e dice che il contenuto resta sul Mac. Per rispondere dall'iPhone, il task va creato
  `TRUSTED`.
