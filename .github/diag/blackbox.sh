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
# ***Since 2026-11-24*** (decision 111): (a) the table goes with the newest processes first —
# ordered by the time since each started, `etime`, not by pid, which on the runner goes past
# 60 000 and may start again —, so the cut takes the oldest away; (b) a dense phase: from the
# moment the first line of tests/infrastructure appears in the suite's log, for <dense> seconds, a
# short comment every <tick> seconds — the time, the tests in flight, the processes in state T,
# the row of WindowServer, and six counters of sysctl. The comments of every <every> seconds go on
# through it. The loop wakes at least every <tick> seconds.
# ***Since 2026-11-24, again*** (decisions 117 and 120 (a)): the dense phase is denser — a comment
# every <fast tick> seconds for its first <fast> seconds, then every <tick> seconds up to <dense>
# —, and each short comment also carries the last forty lines of `sudo log show --last 15s` for
# faults and errors, cut at 4 seconds and the cut said, the processes whose command holds Chrome,
# chrome or node with their seconds of life, and the count of the processes; of sysctl only
# kern.num_files, kern.maxfiles and kern.maxproc, since kern.num_tasks and kern.num_threads are
# ceilings.
#
# Usage: sh .github/diag/blackbox.sh <folder> <label> <issue> [every, 60] [most, 5400]
#        [fast tick, 5] [fast, 90] [tick, 15] [dense, 240]
# The token comes from GH_TOKEN and goes to curl in a file, never in its arguments. Every exit is 0.
folder=$1
label=$2
issue=$3
every=${4:-60}
most=${5:-5400}
fast_tick=${6:-5}
fast=${7:-90}
tick=${8:-15}
dense=${9:-240}
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
short_n=0
dense_start=
fence='```'
SYSCTLS="kern.num_files kern.maxfiles kern.maxproc"
PREDICATE="messageType == fault OR messageType == error"

# The table of the processes, the newest first: `etime` ([[dd-]hh:]mm:ss) in seconds, sorted, and
# dropped; the columns are those of decision 92.
newest_first() {
  echo "  PID  PPID  PGID STAT USER     COMM (i più nuovi per primi)"
  ps -axo etime=,pid=,ppid=,pgid=,stat=,user=,comm= | awk '{
    e = $1; d = 0
    if (index(e, "-")) { split(e, a, "-"); d = a[1]; e = a[2] }
    k = split(e, p, ":"); s = 0
    for (i = 1; i <= k; i++) s = s * 60 + p[i]
    s += d * 86400
    comm = $7
    for (i = 8; i <= NF; i++) comm = comm " " $i
    printf "%d\t%5d %5d %5d %-4s %-8s %s\n", s, $2, $3, $4, $5, $6, comm
  }' | sort -n -k1,1 | cut -f2-
}

# `sudo log show --last 15s`, faults and errors, at most 4 seconds: it runs in the background and
# leaves a mark when it is done; without the mark after 4 seconds it is stopped, and the comment says
# so. The process sudo runs as root is stopped through sudo.
log_show() {
  rm -f "$work/log.txt" "$work/log.done"
  ( sudo -n log show --last 15s --style compact --predicate "$PREDICATE" > "$work/log.txt" 2>&1
    echo done > "$work/log.done" ) < /dev/null > /dev/null 2>&1 &
  waited=0
  while [ ! -f "$work/log.done" ] && [ "$waited" -lt 40 ]; do
    sleep 0.1
    waited=$((waited + 1))
  done
  if [ -f "$work/log.done" ]; then
    log_said="in $((waited / 10)),$((waited % 10)) s"
  else
    sudo -n pkill -f 'log show --last 15s' > /dev/null 2>&1
    log_said="TAGLIATO a 4 s: non era finito"
  fi
}

# The processes whose command holds Chrome, chrome or node: pid, ppid, state, seconds of life.
browsers() {
  ps -axo etime=,pid=,ppid=,stat=,comm= | awk '{
    e = $1; d = 0
    if (index(e, "-")) { split(e, a, "-"); d = a[1]; e = a[2] }
    k = split(e, p, ":"); s = 0
    for (i = 1; i <= k; i++) s = s * 60 + p[i]
    s += d * 86400
    comm = $5
    for (i = 6; i <= NF; i++) comm = comm " " $i
    if (comm ~ /Chrome|chrome|node/) printf "%5d %5d %-4s %6ds %s\n", $2, $3, $4, s, comm
  }'
}

post() {
  jq -Rs '{body: .}' < "$body" > "$payload" 2>/dev/null \
    || python3 -c 'import json, sys; print(json.dumps({"body": sys.stdin.buffer.read().decode("utf-8", "replace")}))' \
      < "$body" > "$payload" 2>/dev/null
  curl -sS -m 20 -o /dev/null -w '%{http_code}' -X POST -H @"$headers" --data-binary @"$payload" \
    "$api/repos/$GITHUB_REPOSITORY/issues/$issue/comments" 2>>"$log"
}

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
    echo "ps -axo pid,ppid,pgid,stat,user,comm, i più nuovi per primi (decisione 111 a):"
    echo "$fence"
    newest_first
    echo "$fence"
  } > "$body" 2>&1
  size=$(wc -c < "$body" | tr -d ' ')
  if [ "$size" -ge 59000 ]; then
    head -c 58000 "$body" > "$body.cut"
    printf '\n%s\n**tagliato dalla coda**: il corpo era di %s byte; ne restano 58000, sotto i 60 000 caratteri; il taglio toglie i processi più vecchi.\n' \
      "$fence" "$size" >> "$body.cut"
    mv "$body.cut" "$body"
  fi
  code=$(post)
  echo "$(date -u +%H:%M:%SZ) commento $n ($1): HTTP $code, $(wc -c < "$body" | tr -d ' ') byte" >> "$log"
}

send_short() {
  short_n=$((short_n + 1))
  now=$(date +%s)
  {
    echo "### fase fitta — $label — fitto $short_n — +$((now - dense_start))s dalla prima riga di tests/infrastructure"
    echo "ora: $(date -u +%Y-%m-%dT%H:%M:%SZ); giro: $GITHUB_RUN_ID"
    echo "i test in volo (l'ultima riga di ogni file gw*, se è una riga begun):"
    echo "$fence"
    for file in "$folder"/gw*.jsonl; do
      [ -f "$file" ] || continue
      last=$(tail -n 1 "$file")
      case $last in
        *'"begun"'*) echo "$(basename "$file"): $last" ;;
      esac
    done
    echo "$fence"
    echo "i processi in stato T (pid, ppid, stat, comando):"
    echo "$fence"
    ps -axo pid=,ppid=,stat=,comm= | awk '$3 ~ /T/' || true
    echo "$fence"
    echo "WindowServer (pid, stato, tempo di CPU):"
    echo "$fence"
    ps -axo pid=,stat=,time=,comm= | grep 'WindowServer$' || echo "nessuna"
    echo "$fence"
    echo "i processi il cui comando contiene Chrome, chrome o node (pid, ppid, stato, secondi di vita, comando):"
    echo "$fence"
    browsers
    echo "$fence"
    echo "il numero dei processi (ps): $(ps -A -o pid= | wc -l | tr -d ' ')"
    echo "sysctl:"
    echo "$fence"
    for name in $SYSCTLS; do
      echo "$name: $(sysctl -n "$name" 2>&1)"
    done
    echo "$fence"
    log_show
    echo "sudo log show --last 15s --style compact --predicate '$PREDICATE', le ultime quaranta righe ($log_said):"
    echo "$fence"
    tail -n 40 "$work/log.txt" 2>/dev/null
    echo "$fence"
  } > "$body" 2>&1
  size=$(wc -c < "$body" | tr -d ' ')
  if [ "$size" -ge 59000 ]; then
    head -c 58000 "$body" > "$body.cut"
    printf '\n%s\n**tagliato dalla coda**: il corpo era di %s byte.\n' "$fence" "$size" >> "$body.cut"
    mv "$body.cut" "$body"
  fi
  code=$(post)
  echo "$(date -u +%H:%M:%SZ) fitto $short_n: HTTP $code, $(wc -c < "$body" | tr -d ' ') byte" >> "$log"
}

next_full=$start
next_short=0
while :; do
  if [ -f "$exit_file" ]; then
    send "finito"
    break
  fi
  if [ $(($(date +%s) - start)) -ge "$most" ]; then
    send "finito: il tempo massimo"
    break
  fi
  if [ -z "$dense_start" ] && grep -l '"tests/infrastructure' "$folder"/*.jsonl > /dev/null 2>&1; then
    dense_start=$(date +%s)
    echo "$(date -u +%H:%M:%SZ) la fase fitta comincia" >> "$log"
  fi
  if [ "$(date +%s)" -ge "$next_full" ]; then
    send "vivo"
    next_full=$((next_full + every))
    [ "$next_full" -le "$(date +%s)" ] && next_full=$(($(date +%s) + every))
  fi
  in_dense=0
  if [ -n "$dense_start" ] && [ $(($(date +%s) - dense_start)) -lt "$dense" ]; then
    in_dense=1
    if [ "$(date +%s)" -ge "$next_short" ]; then
      send_short
      step=$tick
      [ $((next_short - dense_start)) -lt "$fast" ] && step=$fast_tick
      [ "$next_short" -lt "$dense_start" ] && next_short=$dense_start
      next_short=$((next_short + step))
      [ "$next_short" -le "$(date +%s)" ] && next_short=$(date +%s)
    fi
  fi
  now=$(date +%s)
  target=$next_full
  [ "$in_dense" = 1 ] && [ "$next_short" -lt "$target" ] && target=$next_short
  wait=$((target - now))
  [ "$wait" -gt "$tick" ] && wait=$tick
  [ "$wait" -lt 1 ] && wait=1
  sleep "$wait"
done
rm -rf "$work"
exit 0
