# ELA — le pagine del Command Center

Fase 17 — il Command Center v1 (spec §46, §48; M17.2, ADR 0044). Qui ci sono **i modelli delle
pagine** che `ela.api` compone e serve al browser del Mac, e la guida per arruolarlo.

Non è un'applicazione e non è Python: sono file HTML con delle fessure — `{nome}` — che il
compositore riempie **sempre passando da `html.escape`**. L'aspetto è quello di
`apps/design-system/` (ADR 0042): i modelli usano le sue classi e non ne inventano, e la sfera si
**include** da `components/_orb.html` invece di ricopiarla.

`capabilities.txt` non è un modello: è **l'impronta** di ciò che ELA sapeva fare quando il Command
Center è stato costruito, generata da `scripts/generate_command_center.py`. Dice di sé che cos'è —
un allarme, non una dimostrazione — e che cosa fare quando suona.

## Le regole di questa cartella, e il test che le tiene

Le regole di ciò che sta in `apps/` non camminano Python: vivono nei test della loro cartella.

| Regola | Test |
|---|---|
| Nessun modello contiene uno `<script>`, un attributo `on*`, un `javascript:`, un `<iframe>`, un `<object>`, un `<embed>` o un `<base>` | `tests/command_center/test_templates.py` |
| Ogni classe usata è una che `components.css` definisce | `tests/command_center/test_templates.py` |
| Il `<title>` è «ELA» e basta: la cronologia di un browser viaggia | `tests/command_center/test_templates.py` |
| Ogni `href` e ogni `action` è una rotta della console; gli id viaggiano nella query, mai nel percorso | `tests/command_center/test_templates.py` |
| I modelli e il codice che li riempie sono un mondo chiuso nei due versi | `tests/command_center/test_templates.py` |
| Ogni fessura è un nome minuscolo che il compositore sa vedere | `tests/command_center/test_templates.py` |
| `capabilities.txt` è byte per byte ciò che il generatore produce, e una capability nuova fa fallire | `tests/command_center/test_capabilities.py` |
| Questo README nomina ogni test della cartella, e nessun altro | `tests/command_center/test_documents.py` |
| Ogni pagina risponde con la `Content-Security-Policy` che vieta gli script, e i valori dell'utente arrivano con l'escape | `tests/api/test_console.py` |

La prima e l'ultima riga sono le **due difese di «niente JavaScript»**, e non sono la stessa cosa
detta due volte: se un giorno un valore sfuggisse all'escape, il browser si rifiuterebbe comunque
di eseguirlo.

## Arruolare il browser del Mac

1. **Al Mac**, conia il codice della console:

   ```
   ela node enroll --privacy TRUSTED --role console
   ```

   Il codice dura **dieci minuti** e si usa una volta sola. Presentato su un'altra rotta di
   arruolamento è rifiutato **e non si consuma**: non hai perso niente.

2. **Nel browser**, apri `http://127.0.0.1:8130/console` — oppure l'indirizzo del Mac sulla
   tailnet, se vuoi aprirlo da fuori —, incolla il codice, dai un nome e invia. Da lì in poi il
   browser porta la sua credenziale in un cookie e la pagina si apre da sola.

3. **Da quale indirizzo**, perché conta: un cookie è **di un browser e di un indirizzo**. Arruolata
   su `127.0.0.1`, la console non manda niente all'indirizzo della tailnet e viceversa — misurato
   (M17.2, misura C1). Arruola l'indirizzo che userai; se ne usi due, sono due console, e
   `ela device list` le mostra.

## Che cosa sapere, detto una volta

- **Il tetto di ciò che vedi si deriva da dove stai leggendo** (M17.2 dec. J). Su `127.0.0.1` il
  contenuto dei task `LOCAL_ONLY` è visibile: non sta lasciando la macchina su cui vive.
  Dall'indirizzo della tailnet vedi ciò che vede il telefono — l'id di quei task, non il
  contenuto. **La pagina lo dice nei due versi**, in fondo a ogni vista, e quella frase è anche il
  modo di accorgersi a occhio se qualcosa cominciasse a inoltrare le connessioni attraverso il
  loopback.
- **La console non prende lavoro**: non manda heartbeat e non è mai «disponibile», qualunque sia
  il suo ultimo contatto. Sono due fatti e due colonne, e il Device Center li mostra separati.
- **Il tema è scuro, sempre**, anche su un Mac in tema chiaro: seguire `prefers-color-scheme`
  vuole una media query che deve derivare il generatore del design system, non una superficie
  (M17.2 dec. F).
- **La pagina di arruolamento è senza stile.** I fogli stanno dietro l'identità come tutto il
  resto: chi non è ancora nessuno non li carica.
- **Il contenuto di un risultato non si legge qui.** Il riassunto di un task dice che il risultato
  c'è e dove si legge — `GET /tasks/<id>/results`, dietro il token del Core — e non finisce con
  «completato» come se non ci fosse niente.
- **Il Command Center v1 osserva e risponde**: approva, rifiuta e ferma un task. Non ne avvia, non
  mette in pausa, non cambia dispositivo né priorità: quelle rotte non esistono.
- **Revocare una console** è `ela node revoke <id>`: la pagina successiva è il modulo di
  arruolamento.
