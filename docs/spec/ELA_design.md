# ELA — Design System & Command Center

**Versione:** 1.0  
**Stato:** Specifica di design concettuale  
**Relazione:** Estensione della ELA Master Definition

---

# 1. Obiettivo

ELA non deve essere percepita come una normale applicazione.

La sua interfaccia deve rappresentare la presenza digitale di ELA e permettere all'utente di:

1. percepire ELA;
2. comprendere cosa sta facendo;
3. comprendere lo stato del sistema;
4. controllare ELA;
5. intervenire quando necessario;
6. autorizzare azioni;
7. osservare dispositivi e task;
8. comprendere l'evoluzione del sistema.

Il design deve quindi essere progettato come un **sistema di presenza digitale**, non come una semplice raccolta di schermate.

---

# 2. ELA Command Center

Il centro dell'esperienza visuale di ELA sarà **ELA Command Center**.

Il Command Center è la dashboard principale dalla quale l'utente può sia osservare sia controllare ELA.

Non deve essere una dashboard amministrativa tradizionale.

Deve essere:

- futuristica;
- premium;
- elegante;
- minimale quando possibile;
- estremamente informativa quando necessario;
- animata con criterio;
- coerente su tutti i dispositivi;
- leggibile;
- immediata;
- non invasiva.

---

# 3. Due funzioni fondamentali

Il Command Center deve svolgere due funzioni.

## OBSERVE

Permette di comprendere:

- cosa sta facendo ELA;
- cosa sta per fare;
- quali task sono attivi;
- quali dispositivi sta utilizzando;
- quali problemi sono presenti;
- se è necessaria l'attenzione dell'utente;
- quali automazioni sono in corso;
- quali agenti sono attivi;
- quali modelli vengono utilizzati;
- lo stato generale del sistema.

## CONTROL

Permette di:

- avviare task;
- fermare task;
- mettere in pausa;
- riprendere;
- cambiare priorità;
- cambiare dispositivo;
- approvare;
- rifiutare;
- modificare autorizzazioni;
- interrompere agenti;
- cambiare modalità operative;
- modificare preferenze;
- controllare la percezione;
- gestire dispositivi;
- consultare l'audit;
- controllare l'evoluzione.

---

# 4. La dashboard non deve sembrare un gestionale

Un errore da evitare è trasformare ELA in:

- grafici ovunque;
- tabelle infinite;
- sidebar con decine di menu;
- card ripetitive;
- colori casuali;
- componenti standard;
- estetica "AI dashboard" generica.

ELA deve avere una propria identità.

La dashboard deve sembrare più simile a:

> un ambiente operativo personale

che a:

> un pannello amministrativo SaaS.

---

# 5. ELA Presence

La dashboard deve avere una rappresentazione centrale della presenza di ELA.

Quando ELA è inattiva:

> **ELA**  
> Online · Monitoring

Quando lavora:

> **ELA**  
> Working

Quando sta aspettando:

> **ELA**  
> Waiting for approval

Quando necessita dell'utente:

> **ELA**  
> Attention required

Quando tutto è normale:

> **ELA**  
> All systems normal.

Questa presenza deve essere visiva, ma discreta.

Non deve occupare inutilmente lo schermo.

---

# 6. Stati di ELA

Il design deve definire chiaramente gli stati principali:

### OFFLINE

ELA non è raggiungibile.

### IDLE

ELA è disponibile ma non sta eseguendo attività.

### LISTENING

ELA sta ascoltando.

### THINKING

ELA sta elaborando una richiesta.

### PLANNING

ELA sta costruendo un piano.

### WORKING

ELA sta eseguendo un'attività.

### WAITING

ELA sta aspettando un evento o una risorsa.

### WAITING APPROVAL

Serve un'autorizzazione dell'utente.

### ATTENTION REQUIRED

ELA ha identificato qualcosa che richiede attenzione.

### ERROR

Si è verificato un problema.

### RECOVERING

ELA sta tentando un recupero.

### UPDATING

ELA sta applicando un aggiornamento autorizzato.

### EVOLVING

ELA sta eseguendo un processo di miglioramento controllato.

Ogni stato deve avere una rappresentazione visiva coerente.

---

# 7. Home del Command Center

La schermata principale dovrebbe concentrarsi sulle informazioni più importanti.

Possibile struttura:

```text
┌──────────────────────────────────────────────────────┐
│ ELA                              SYSTEM STATUS ●      │
│                                                      │
│                                                      │
│                     ELA                              │
│                Online · Monitoring                   │
│                                                      │
│          "Everything is under control."              │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│ NOW                                                  │
│ Preparing tomorrow's meeting briefing               │
│                                                      │
│ ● MacBook                                            │
│ ● 3 tasks running                                    │
│ ● Nothing requires approval                          │
│                                                      │
├───────────────┬────────────────┬─────────────────────┤
│ TASKS         │ DEVICES        │ ATTENTION           │
│ 3 running     │ Mac   Active   │ Nothing required    │
│ 1 waiting     │ Win   Ready    │                     │
│ 0 failed      │ iPhone Online  │                     │
└───────────────┴────────────────┴─────────────────────┘
```

Questa è una direzione concettuale, non un layout definitivo.

---

# 8. Now

Il Command Center deve avere una sezione **NOW**.

Questa deve rispondere immediatamente alla domanda:

> "Cosa sta facendo ELA in questo momento?"

Esempio:

**NOW**

> Preparing tomorrow's meeting briefing.

Sotto:

> Reading calendar  
> Searching related emails  
> Analysing documents

L'utente non deve aprire un task manager per capire cosa sta succedendo.

---

# 9. Task Center

ELA deve avere una vista dedicata ai task.

Ogni task può mostrare:

- nome;
- obiettivo;
- stato;
- progresso;
- dispositivo;
- agente;
- modello;
- tempo trascorso;
- priorità;
- dipendenze;
- eventuale richiesta di approvazione.

Un task può essere espanso per mostrare il relativo piano operativo.

---

# 10. Task Intelligence View

L'utente deve poter comprendere perché ELA sta facendo qualcosa.

Non deve essere mostrato il chain-of-thought privato del modello.

Deve invece essere mostrato un **execution summary** strutturato.

Esempio:

```text
OBJECTIVE
Prepare meeting briefing

CONTEXT
Calendar
Email
Documents

PLAN
✓ Identify meeting
✓ Collect related material
● Analyse documents
○ Prepare briefing
○ Verify results

CURRENT ACTION
Analysing documents

DEVICE
MacBook

MODEL
Selected automatically

STATUS
Working
```

Questo rende il sistema trasparente senza esporre ragionamenti interni sensibili.

---

# 11. Device Center

La dashboard deve mostrare tutti i nodi ELA.

### MacBook

**WORK NODE**

Stato:

Active

Capacità:

- Development
- Creative
- General compute
- Local AI

### Windows PC

**POWER NODE**

Stato:

Available

Capacità:

- GPU
- Rendering
- Heavy compute
- Windows applications

### iPhone

**COMPANION NODE**

Stato:

Connected

Capacità:

- Voice
- Notifications
- Approvals
- Remote interaction

---

# 12. Device Orchestration View

L'utente deve poter vedere quando ELA decide di spostare un task.

Esempio:

```text
TASK

Video rendering

START
MacBook

↓

ELA detected:
Windows GPU available

↓

TRANSFER

MacBook → Windows

↓

EXECUTING
Windows Power Node
```

Questo rende visibile uno degli aspetti più importanti dell'architettura distribuita.

---

# 13. Attention Center

Il sistema deve mostrare chiaramente quando ELA necessita dell'utente.

Livelli:

```text
SILENT
NOTIFICATION
PRIORITY
PHONE CALL
EMERGENCY
```

Il design deve rendere immediatamente distinguibile il livello di attenzione richiesto.

---

# 14. Approval Center

Quando ELA necessita di un'autorizzazione, la dashboard deve mostrare:

- cosa vuole fare;
- perché;
- quale dispositivo;
- quale capability;
- livello di rischio;
- conseguenze;
- reversibilità;
- durata;
- cosa succede dopo l'approvazione.

Esempio:

```text
ELA REQUESTS APPROVAL

Action
Send email to client

Reason
Reply to project discussion

Risk
MEDIUM

Recipient
...

Message
...

[ APPROVE ]
[ DENY ]
[ EDIT ]
```

Per azioni critiche, l'interfaccia deve richiedere una conferma inequivocabile.

---

# 15. Memory View

La memoria deve poter essere osservata e gestita.

L'utente deve poter comprendere:

- cosa ELA ricorda;
- perché lo ricorda;
- da dove proviene;
- quanto è sicura dell'informazione;
- quando è stata aggiornata;
- se è temporanea o persistente.

La memoria non deve apparire come un database grezzo.

Deve essere presentata come **conoscenza contestuale di ELA**.

---

# 16. Perception View

ELA deve avere una sezione dedicata alla percezione.

Può mostrare:

```text
MICROPHONE
Available

WEBCAM
Off

SCREEN AWARENESS
Active

BROWSER CONTEXT
Active
```

L'utente deve sapere chiaramente quando ELA sta utilizzando una fonte di percezione.

La privacy deve essere parte del design, non un dettaglio nascosto nelle impostazioni.

---

# 17. Voice Presence

Quando ELA ascolta o parla, l'interfaccia deve comunicarlo.

L'interazione vocale può utilizzare:

- animazioni;
- waveform;
- orb;
- glow;
- movimento;
- variazioni sottili della presenza centrale.

La rappresentazione deve essere elegante e non diventare un semplice "cerchio che pulsa".

---

# 18. Proactive Presence

ELA può comparire senza essere esplicitamente aperta.

Per esempio:

```text
ELA

I noticed something important.

Your 09:00 meeting tomorrow has changed.
I checked the related documents.

Would you like a briefing?
```

La UI deve essere capace di passare:

**ambient → informative → urgent**

senza diventare invasiva.

---

# 19. Desktop Presence

Su Windows e macOS ELA dovrebbe avere diversi livelli di presenza:

### Ambient

ELA è presente ma quasi invisibile.

### Compact

Piccolo pannello o floating presence.

### Expanded

Command Center.

### Full

Esperienza completa di gestione e controllo.

Questo permette all'utente di lavorare senza avere sempre una dashboard enorme sullo schermo.

---

# 20. iPhone

L'iPhone deve utilizzare la stessa identità visiva.

Non deve essere una semplice versione ridotta della dashboard desktop.

Il Companion deve concentrarsi su:

- conversazione;
- notifiche;
- approvazioni;
- task;
- stato;
- richieste urgenti;
- controllo remoto.

L'interfaccia mobile deve essere progettata specificamente per l'interazione rapida.

---

# 21. Design System

ELA deve avere un vero design system.

Deve definire:

- colori;
- typography;
- spacing;
- grid;
- radius;
- elevation;
- shadows;
- iconography;
- motion;
- components;
- states;
- accessibility;
- responsive behavior.

Il design system deve essere una fonte unica di verità.

---

# 22. Visual Identity

L'identità di ELA deve essere progettata prima della UI definitiva.

Devono essere definiti:

- logo;
- simbolo;
- wordmark;
- typography;
- palette;
- icon system;
- visual language;
- motion language;
- presence language.

Il design deve comunicare:

**intelligenza + precisione + eleganza + tecnologia + fiducia**

senza cadere nello stereotipo:

**"AI = neon viola + gradienti + orb luminoso".**

---

# 23. Estetica

La direzione iniziale deve essere:

**Futuristic Luxury / Intelligent Minimalism**

con possibili influenze:

- aerospace;
- high-end automotive;
- advanced computing;
- cinematic interfaces;
- premium industrial design.

Il risultato deve essere sofisticato, non fantascientifico in modo kitsch.

---

# 24. Motion Design

L'animazione deve comunicare stato e gerarchia.

Non deve essere decorativa senza motivo.

Esempi:

**IDLE**

Movimento quasi impercettibile.

**THINKING**

Movimento più dinamico.

**WORKING**

Attività visibile ma non distraente.

**APPROVAL**

Interfaccia più focalizzata.

**ERROR**

Movimento minimo e immediatamente comprensibile.

**SUCCESS**

Feedback breve e raffinato.

---

# 25. Interaction Language

ELA deve avere un proprio linguaggio d'interazione.

L'interfaccia deve comunicare:

> "ELA è presente."

non:

> "Hai aperto un'app."

Questo principio deve guidare:

- transizioni;
- animazioni;
- notifiche;
- voce;
- microcopy;
- feedback;
- stati.

---

# 26. Command Center come centro operativo

Il Command Center deve diventare il punto dal quale l'utente può comprendere l'intero sistema ELA.

Idealmente, da un'unica esperienza deve poter vedere:

```text
ELA
│
├── NOW
├── TASKS
├── DEVICES
├── MEMORY
├── ATTENTION
├── APPROVALS
├── AGENTS
├── MODELS
├── TOOLS
├── SECURITY
├── AUDIT
└── EVOLUTION
```

Queste sezioni non devono necessariamente essere tutte visibili contemporaneamente.

La UI deve adattarsi al contesto.

---

# 27. Adaptive Interface

La dashboard deve cambiare in base a ciò che sta succedendo.

Se non succede nulla:

> minimal.

Se ci sono molti task:

> operational.

Se serve un'approvazione:

> focused.

Se esiste un problema:

> diagnostic.

Se ELA sta evolvendo:

> evolution mode.

La UI stessa deve essere **context-aware**.

---

# 28. Design e autonomia

Il design deve riflettere il modello di autonomia.

L'utente deve poter capire:

**ELA sta osservando.**

**ELA sta pensando.**

**ELA sta pianificando.**

**ELA sta lavorando.**

**ELA sta aspettando.**

**ELA necessita di me.**

**ELA ha completato il lavoro.**

Questa comunicazione deve essere immediata.

---

# 29. Design e sicurezza

La sicurezza deve essere visibile senza diventare opprimente.

Quando un'azione è SAFE:

ELA può eseguirla quasi senza interruzioni.

Quando è LOW:

feedback leggero.

Quando è MEDIUM:

contesto maggiore.

Quando è HIGH:

richiesta esplicita.

Quando è CRITICAL:

conferma inequivocabile.

La UI deve quindi rappresentare il livello di rischio.

---

# 30. Design come estensione dell'architettura

Il design non è un livello separato dal sistema.

Deve riflettere direttamente l'architettura:

```text
ELA CORE
   ↓
CONTEXT
   ↓
TASK
   ↓
ORCHESTRATION
   ↓
ACTION
   ↓
VERIFICATION
   ↓
RESULT
```

L'interfaccia deve rendere questi processi comprensibili all'utente.

---

# 31. Obiettivo finale del design

Il design finale deve far percepire ELA come:

> **un'intelligenza personale persistente che vive attraverso i dispositivi dell'utente.**

Non come:

> una dashboard AI.

Non come:

> un chatbot.

Non come:

> un sistema amministrativo.

Ma come:

> **un ambiente operativo personale intelligente.**

---

# 32. Regola definitiva

Ogni scelta visuale di ELA deve rispondere a una domanda:

> **Questa scelta rende ELA più intelligente, più comprensibile, più elegante o più controllabile?**

Se non lo fa, probabilmente non serve.

---

# 33. Design Workflow

Il design di ELA deve essere sviluppato secondo questo processo:

```text
DISCOVERY
   ↓
VISUAL IDENTITY
   ↓
DESIGN DIRECTION
   ↓
DESIGN SYSTEM
   ↓
COMMAND CENTER
   ↓
INTERACTION STATES
   ↓
PROTOTYPE
   ↓
USER REVIEW
   ↓
IMPLEMENTATION
   ↓
VISUAL QA
   ↓
ITERATION
```

Non si deve saltare direttamente da:

> "ELA deve essere futuristica"

a:

> "scrivi il codice della dashboard".

Prima deve esistere una direzione visuale coerente.

---

# 34. Design Deliverables

La fase di design deve produrre almeno:

1. ELA Visual Identity
2. Logo / Symbol
3. Typography system
4. Color system
5. Design tokens
6. Component library
7. Motion system
8. Interaction states
9. Command Center
10. Task view
11. Device view
12. Approval view
13. Memory view
14. Perception view
15. Evolution view
16. Desktop presence
17. iPhone companion
18. Responsive behavior
19. Accessibility rules
20. Interactive prototype

Solo dopo questi elementi dovrebbe iniziare l'implementazione completa della UI.

---

# 35. Principio finale

**ELA deve essere bella quando non fa nulla, chiara quando fa qualcosa, elegante quando lavora e impossibile da fraintendere quando necessita dell'utente.**