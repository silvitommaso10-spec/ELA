#!/bin/sh
# The black box (decision 92 of the branch m13.11-il-browser-sul-pc), on the branch
# diag-m13.11-osservazione only, which never enters main. A loop in the background, not a step of
# the runner: every <every> seconds it sends out of the machine, with curl and the job's token, a
# comment on the issue <issue> — the variant, the time, `uptime`, whether the exit code is born,
# the rows of Runner.Listener and Runner.Worker, the last line of every file of the suite's log,
# the last two lines of the output, and the whole table of `ps -axo pid,ppid,pgid,stat,user,comm`,
# cut from its tail under 60 000 characters, and the cut said. It serves one thing: knowing whether, once the
# runner is lost, the machine is still alive. It ends by itself with a last comment «finito» when
# the exit code is born, or after <most> seconds.
#
# Usage: sh .github/diag/blackbox.sh <folder> <label> <issue> [every, 60] [most, 5400]
# The token comes from GH_TOKEN and goes to curl in a file, never in its arguments. Every exit is 0.
folder=$1
label=$2
issue=$3
every=${4:-60}
most=${5:-5400}
api=${BLACKBOX_API:-https://api.github.com}
[ -n "$folder" ] && [ -n "$issue" ] && [ -n "$GH_TOKEN" ] && [ -n "$GITHUB_REPOSITORY" ] || exit 0
mkdir -p "$folder" 2>/dev/null
umask 077
work=$(mktemp -d 2>/dev/null) || exit 0
headers=$work/headers
body=$work/body
payload=$work/payload.json
log=$folder/blackbox.txt
printf 'Authorization: Bearer %s\nAccept: application/vnd.github+json\nX-GitHub-Api-Version: 2022-11-28\n' \
  "$GH_TOKEN" > "$headers"
exit_file=$folder/make-check-exit.txt
start=$(date +%s)
n=0
fence='```'

send() {
  n=$((n + 1))
  {
    echo "### scatola nera — $label — $1 — commento $n"
    echo "ora: $(date -u +%Y-%m-%dT%H:%M:%SZ); runner: $RUNNER_NAME; giro: $GITHUB_RUN_ID"
    echo "uptime: $(uptime)"
    if [ -f "$exit_file" ]; then
      echo "il codice d'uscita: nato, $(cat "$exit_file")"
    else
      echo "il codice d'uscita: non nato"
    fi
    # The rows the reading of decision 93 (4) needs, repeated here: the whole table below can be
    # longer than the limit, and the cut takes its tail.
    echo "le righe di Runner.Listener e Runner.Worker, dalla stessa tabella:"
    echo "$fence"
    ps -axo pid,ppid,pgid,stat,user,comm | grep -E 'Runner\.(Listener|Worker)' || echo "nessuna"
    echo "$fence"
    echo
    echo "l'ultima riga di ogni .jsonl del log della suite:"
    echo "$fence"
    for file in "$folder"/*.jsonl; do
      [ -f "$file" ] && echo "$(basename "$file"): $(tail -n 1 "$file")"
    done
    echo "$fence"
    echo "le ultime due righe dell'uscita:"
    echo "$fence"
    tail -n 2 "$folder/make-check.txt" 2>/dev/null
    echo "$fence"
    echo "ps -axo pid,ppid,pgid,stat,user,comm:"
    echo "$fence"
    ps -axo pid,ppid,pgid,stat,user,comm
    echo "$fence"
  } > "$body" 2>&1
  size=$(wc -c < "$body" | tr -d ' ')
  if [ "$size" -ge 59000 ]; then
    head -c 58000 "$body" > "$body.cut"
    printf '\n%s\n**tagliato dalla coda**: il corpo era di %s byte; ne restano 58000, sotto i 60 000 caratteri.\n' \
      "$fence" "$size" >> "$body.cut"
    mv "$body.cut" "$body"
  fi
  jq -Rs '{body: .}' < "$body" > "$payload" 2>/dev/null \
    || python3 -c 'import json, sys; print(json.dumps({"body": sys.stdin.buffer.read().decode("utf-8", "replace")}))' \
      < "$body" > "$payload" 2>/dev/null
  code=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -X POST -H @"$headers" --data-binary @"$payload" \
    "$api/repos/$GITHUB_REPOSITORY/issues/$issue/comments" 2>>"$log")
  echo "$(date -u +%H:%M:%SZ) commento $n ($1): HTTP $code, $(wc -c < "$body" | tr -d ' ') byte" >> "$log"
}

while :; do
  if [ -f "$exit_file" ]; then
    send "finito"
    break
  fi
  if [ $(($(date +%s) - start)) -ge "$most" ]; then
    send "finito: il tempo massimo"
    break
  fi
  send "vivo"
  sleep "$every"
done
rm -rf "$work"
exit 0
