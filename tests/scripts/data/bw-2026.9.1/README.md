# `bw` 2026.9.1, senza account — registrato il 2026-10-10

Le uscite del binario ufficiale (`cli-v2026.9.1`, `bw-macos-arm64`, firmato «Bitwarden Inc», lo sha256
dello zip confrontato con quello della release), lanciato **senza account** e con una cartella dei
dati sua: i suoi aiuti, e ciò che risponde a chi non ha fatto un login. `bw login` e `bw unlock` non
sono stati lanciati.

`tests/scripts/test_misura_m13_9.py` le legge per due cose: ogni comando che
`scripts/misura_m13_9.py` compone sta nell'aiuto del comando vero, e il `bw` finto dei test risponde
senza account ciò che quello vero ha risposto.

**Che cosa è copiato e che cosa è trascritto**: gli aiuti (`*-help.txt`) sono i file della sonda, com'erano;
`version.txt`, `status-no-account.txt` e i tre `*-no-account.txt` sono **trascritti** dall'uscita JSON della
sonda (`bw-no-account.jsonl`) — lo stdout com'era per i primi due, e per gli altri una riga `exit N` seguita
dallo stderr —, perché il test li confronti senza leggere un file di `.git/`.

**Una differenza dall'uscita vera, dichiarata**: `create-help.txt` finisce prima del suo blocco
«Examples», perché l'esempio in base64 di quel blocco è, per il controllo dei segreti del repository,
un segreto. Le uscite intere e la sonda che le ha prodotte sono in `.git/m13.9-reference/bw/out/` e
`.git/m13.9-reference/measure/probe_bw.py` (`docs/milestones/M13.9.md`, «Le misure della notte», 3).
