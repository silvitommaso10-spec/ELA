Fase: post-0.1 — runtime dei nodi dispositivo che eseguono i tool per conto del Core (spec §4, §56).

Il codice di un nodo NON vive qui: vive in `src/ela/node/`, dentro `mypy --strict`, dentro il gate
della copertura, dentro i contratti import-linter e dentro le regole di architettura. La ragione sta
in ADR 0039 §1: è il livello di verifica, non l'indirizzo. Qui fuori un processo che tiene un
segreto ed esegue tool sarebbe il codice meno verificato di ELA.
