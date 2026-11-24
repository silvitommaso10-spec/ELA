#!/bin/sh
# The witness outside the session, the part that runs (decisions 128 and 132 of the branch
# m13.11-il-browser-sul-pc), on the branch diag-m13.11-osservazione only, which never enters main.
# launchd runs it as root, outside the graphical session of the user runner. Every <tick> seconds it
# looks at the pid of WindowServer, the pid of loginwindow, the user of the console, whether
# Runner.Listener is there, and the new files in the two folders of DiagnosticReports. Every
# <alive> seconds a short comment «vivo» on the issue; at every change a comment at once — what
# changed, the values before and after, the reports by date, the first forty lines of the newest
# whose name holds WindowServer, gpuRestart, loginwindow or panic, the last forty lines of
# `log show --last 30s` for WindowServer, loginwindow and watchdogd, and the lines of the kernel of
# the last 30 seconds with «GPU hang» or «AppleParavirtGPU» —; after the first change a comment
# every <tick> seconds for <fast> seconds, then every <alive>, up to <window> seconds from the first
# change. It ends with «finito» when make check's exit code is born, at <window> from the first
# change, or after <most> seconds. A `log show` stops at 6 seconds, and the comment says so.
# Every exit is 0.
#
# For the proof on the Mac: TESTIMONE_PATH replaces the PATH (the proof's own pgrep, stat, log and
# curl answer), and TESTIMONE_TICK, _ALIVE, _FAST, _WINDOW and _MOST the seconds (10, 120, 180,
# 3600, 9000).
PATH=${TESTIMONE_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}
dir=$(cd "$(dirname "$0")" && pwd)
. "$dir/config"
log=$dir/testimone.log
tick=${TESTIMONE_TICK:-10}
alive=${TESTIMONE_ALIVE:-120}
fast=${TESTIMONE_FAST:-180}
window=${TESTIMONE_WINDOW:-3600}
most=${TESTIMONE_MOST:-9000}
fence='```'
system_reports="$root/Library/Logs/DiagnosticReports"
user_reports="$root$runner_home/Library/Logs/DiagnosticReports"
umask 077
headers=$dir/headers
printf 'Authorization: Bearer %s\nAccept: application/vnd.github+json\nX-GitHub-Api-Version: 2022-11-28\n' \
  "$(cat "$dir/token")" > "$headers"

look() {
  ws=$(pgrep -x WindowServer 2>/dev/null | head -n 1)
  lw=$(pgrep -x loginwindow 2>/dev/null | head -n 1)
  console=$(stat -f %Su /dev/console 2>/dev/null)
  if pgrep -f Runner.Listener > /dev/null 2>&1; then listener=sì; else listener=no; fi
  values="WindowServer ${ws:-nessuno}; loginwindow ${lw:-nessuno}; console ${console:-?}; Runner.Listener $listener"
}

reports() {
  for folder in "$system_reports" "$user_reports"; do
    ls -1 "$folder" 2>/dev/null | sed "s|^|$folder/|"
  done | sort
}

# `log show` with a predicate, at most 6 seconds: in the background, and stopped if it is not done.
log_show() {
  rm -f "$dir/log.txt" "$dir/log.done"
  ( log show --last 30s --style compact --predicate "$1" > "$dir/log.txt" 2>&1
    echo done > "$dir/log.done" ) < /dev/null > /dev/null 2>&1 &
  waited=0
  while [ ! -f "$dir/log.done" ] && [ "$waited" -lt 60 ]; do
    sleep 0.1
    waited=$((waited + 1))
  done
  if [ -f "$dir/log.done" ]; then
    log_said="in $((waited / 10)),$((waited % 10)) s"
  else
    pkill -f "log show --last 30s" > /dev/null 2>&1
    log_said="TAGLIATO a 6 s: non era finito"
  fi
}

post() {
  size=$(wc -c < "$dir/body" | tr -d ' ')
  if [ "$size" -ge 59000 ]; then
    head -c 58000 "$dir/body" > "$dir/body.cut"
    printf '\n**tagliato dalla coda**: il corpo era di %s byte.\n' "$size" >> "$dir/body.cut"
    mv "$dir/body.cut" "$dir/body"
  fi
  rm -f "$dir/payload.plist" "$dir/payload.json"
  plutil -create xml1 "$dir/payload.plist" \
    && plutil -insert body -string "$(tr -d '\000-\010\013\014\016-\037' < "$dir/body")" "$dir/payload.plist" \
    && plutil -convert json -o "$dir/payload.json" "$dir/payload.plist"
  code=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -X POST -H @"$headers" --data-binary @"$dir/payload.json" \
    "$api/repos/$repository/issues/$issue/comments" 2>>"$log")
  echo "$(date -u +%H:%M:%SZ) commento $n ($1): HTTP $code" >> "$log"
}

short() {
  n=$((n + 1))
  {
    echo "### testimone — $label — $1 — commento $n"
    echo "ora: $(date -u +%Y-%m-%dT%H:%M:%SZ); giro: $run"
    echo "$values; rapporti nuovi dall'inizio: $born"
  } > "$dir/body"
  post "$1"
}

changed() {
  n=$((n + 1))
  {
    echo "### testimone — $label — CAMBIAMENTO — commento $n"
    echo "ora: $(date -u +%Y-%m-%dT%H:%M:%SZ); giro: $run"
    echo "che cosa è cambiato:"
    echo "$fence"
    printf '%s' "$what"
    echo "$fence"
    echo "prima: $before"
    echo "dopo: $values"
    echo "i rapporti per data, i primi dieci:"
    echo "$fence"
    ls -lt "$system_reports" "$user_reports" 2>&1 | grep -v '^total' | head -n 12
    echo "$fence"
    newest=$(ls -t "$system_reports"/* "$user_reports"/* 2>/dev/null | grep -E 'WindowServer|gpuRestart|loginwindow|panic' | head -n 1)
    if [ -n "$newest" ]; then
      echo "le prime quaranta righe di $newest:"
      echo "$fence"
      head -n 40 "$newest"
      echo "$fence"
    else
      echo "nessun rapporto il cui nome contiene WindowServer, gpuRestart, loginwindow o panic"
    fi
    log_show 'process == "WindowServer" OR process == "loginwindow" OR process == "watchdogd"'
    echo "log show --last 30s di WindowServer, loginwindow e watchdogd, le ultime quaranta righe ($log_said):"
    echo "$fence"
    tail -n 40 "$dir/log.txt" 2>/dev/null
    echo "$fence"
    log_show 'process == "kernel" AND (eventMessage CONTAINS "GPU hang" OR eventMessage CONTAINS "AppleParavirtGPU")'
    echo "le righe del kernel degli ultimi 30 s con «GPU hang» o «AppleParavirtGPU» ($log_said):"
    echo "$fence"
    grep -E 'GPU hang|AppleParavirtGPU' "$dir/log.txt" 2>/dev/null | tail -n 40
    echo "$fence"
  } > "$dir/body" 2>&1
  post "cambiamento"
}

start=$(date +%s)
n=0
born=0
first_change=
last_post=0
reports > "$dir/known.txt"
look
previous_values=$values
pws=$ws
plw=$lw
pconsole=$console
plistener=$listener
while :; do
  now=$(date +%s)
  if [ -f "$exit_file" ]; then
    look
    short "finito"
    break
  fi
  if [ $((now - start)) -ge "$most" ]; then
    look
    short "finito: il tempo massimo"
    break
  fi
  if [ -n "$first_change" ] && [ $((now - first_change)) -ge "$window" ]; then
    look
    short "finito: sessanta minuti dal primo cambiamento"
    break
  fi
  look
  reports > "$dir/now.txt"
  fresh=$(comm -13 "$dir/known.txt" "$dir/now.txt")
  what=
  [ "$ws" != "$pws" ] && what="${what}WindowServer: ${pws:-nessuno} → ${ws:-nessuno}
"
  [ "$lw" != "$plw" ] && what="${what}loginwindow: ${plw:-nessuno} → ${lw:-nessuno}
"
  [ "$console" != "$pconsole" ] && what="${what}console: ${pconsole:-?} → ${console:-?}
"
  [ "$listener" != "$plistener" ] && what="${what}Runner.Listener: $plistener → $listener
"
  if [ -n "$fresh" ]; then
    born=$((born + $(printf '%s\n' "$fresh" | wc -l | tr -d ' ')))
    what="${what}rapporti nuovi:
$fresh
"
  fi
  if [ -n "$what" ]; then
    before=$previous_values
    changed
    [ -z "$first_change" ] && first_change=$now
    cp "$dir/now.txt" "$dir/known.txt"
    previous_values=$values
    pws=$ws
    plw=$lw
    pconsole=$console
    plistener=$listener
    last_post=$now
  elif [ -n "$first_change" ] && [ $((now - first_change)) -lt "$fast" ]; then
    short "dopo il cambiamento"
    last_post=$now
  elif [ $((now - last_post)) -ge "$alive" ]; then
    short "vivo"
    last_post=$now
  fi
  sleep "$tick"
done
rm -f "$headers"
exit 0
