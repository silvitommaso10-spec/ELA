#!/bin/sh
# The micro run (decision 138 of the branch m13.11-il-browser-sul-pc), on the branch
# diag-m13.11-osservazione only, which never enters main: the orphaned process group of decision
# 137, without the suite. Every line goes to <folder>/micro.txt with its time, and to the log.
#
# Usage: sh micro.sh <folder> <riproduzione|senza-fermato-poi-fermato|sessione-sua>
# «riproduzione»: a `sleep 600` in the background, stopped with SIGSTOP; then `sh -c 'sleep 5 &'`
# (with the sleep's streams closed)
# — the sh ends and its sleep is adopted by launchd —; then 30 seconds, a line every 5, and
# «ancora vivo». «senza-fermato-poi-fermato»: first `sh -c 'sleep 5 &'` and 15 seconds with nothing
# stopped, then the same. «sessione-sua»: the same as «riproduzione», in a session of its own — the
# workflow starts this script through os.setsid() —, and its first line says the session.
folder=$1
variant=$2
riga() {
  line="$(date -u +%H:%M:%SZ) $*"
  echo "$line" >> "$folder/micro.txt"
  echo "$line"
}
adopted() {
  # The sleep's streams are closed: with the pipe of $(...) open, the substitution would wait for it.
  A=$(sh -c 'sleep 5 > /dev/null 2>&1 < /dev/null & echo $!')
  riga "sh -c 'sleep 5 &' è uscito; lo sleep adottato: $(ps -o pid=,ppid=,pgid=,stat= -p "$A")"
}
stopped() {
  sleep 600 &
  S=$!
  riga "sleep 600 in sfondo: $(ps -o pid=,ppid=,pgid=,stat= -p "$S")"
  kill -STOP "$S"
  riga "kill -STOP $S: lo stato $(ps -o stat= -p "$S")"
  adopted
  for step in 1 2 3 4 5 6; do
    sleep 5
    riga "in attesa, +$((step * 5)) s: lo sleep adottato $(ps -o stat= -p "$A" 2>/dev/null || echo uscito), il fermo $(ps -o stat= -p "$S" 2>/dev/null || echo uscito)"
  done
}
# On macOS ps gives sess 0 to every process: the true session comes from getsid.
riga "comincia «${variant}»: io $(ps -o pid=,ppid=,pgid=,sess=,stat= -p $$); sid $(python3 -c 'import os; print(os.getsid(0))' 2>&1)"
case $variant in
  senza-fermato-poi-fermato)
    riga "la prima metà: niente di fermo"
    adopted
    for step in 1 2 3; do
      sleep 5
      riga "in attesa, +$((step * 5)) s: lo sleep adottato $(ps -o stat= -p "$A" 2>/dev/null || echo uscito)"
    done
    riga "la prima metà è finita; la seconda: la sequenza di «riproduzione»"
    stopped
    ;;
  *)
    stopped
    ;;
esac
riga "ancora vivo; il fermo: $(ps -o pid=,stat= -p "$S" 2>/dev/null || echo uscito)"
kill -CONT "$S" 2>/dev/null
kill "$S" 2>/dev/null
exit 0
