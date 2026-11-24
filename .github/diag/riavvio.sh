#!/bin/sh
# The witness of a restart, the part that runs at the start of the machine (decision 120 (b) of the
# branch m13.11-il-browser-sul-pc), on the branch diag-m13.11-osservazione only, which never
# enters main. launchd starts it as root, from the LaunchDaemon riavvio-installa.sh wrote and did
# not load. At 30, 60 and 120 seconds from the start of the machine it tries to send one comment
# «RIAVVIATA» to the issue — the variant, kern.boottime, /Library/Logs/DiagnosticReports by date,
# the first sixty lines of the newest .panic if there is one, the last dated line of the sampler —
# and stops at the first that answers 201, or after the third. The token is in a file only root
# reads, and goes to curl in a file of headers. Every exit is 0.
#
# For the proof on the Mac: RIAVVIO_BOOT (the second of the start) and RIAVVIO_ATTESE (the
# seconds of the tries) replace kern.boottime and «30 60 120», and RIAVVIO_PATH the PATH, so that the
# proof's curl is the one that answers.
PATH=${RIAVVIO_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}
dir=$(cd "$(dirname "$0")" && pwd)
. "$dir/config"
log=$dir/riavvio.log
fence='```'
boot=${RIAVVIO_BOOT:-$(sysctl -n kern.boottime | sed -E 's/^\{ sec = ([0-9]+),.*/\1/')}
umask 077
headers=$dir/headers
printf 'Authorization: Bearer %s\nAccept: application/vnd.github+json\nX-GitHub-Api-Version: 2022-11-28\n' \
  "$(cat "$dir/token")" > "$headers"
for at in ${RIAVVIO_ATTESE:-30 60 120}; do
  pause=$((boot + at - $(date +%s)))
  [ "$pause" -gt 0 ] && sleep "$pause"
  {
    echo "### RIAVVIATA — $label"
    echo "ora: $(date -u +%Y-%m-%dT%H:%M:%SZ); giro: $run; il tentativo a +${at}s dall'avvio"
    echo "kern.boottime: $(sysctl -n kern.boottime)"
    echo "uptime: $(uptime)"
    echo "$reports, per data:"
    echo "$fence"
    ls -lt "$reports" 2>&1 | head -n 60
    echo "$fence"
    panic=$(ls -t "$reports"/*.panic 2>/dev/null | head -n 1)
    if [ -n "$panic" ]; then
      echo "le prime sessanta righe di $(basename "$panic"):"
      echo "$fence"
      head -n 60 "$panic"
      echo "$fence"
    else
      echo "nessun file .panic"
    fi
    echo "l'ultima riga datata del campionatore ($sampler):"
    echo "$fence"
    grep '^=== 20' "$sampler" 2>&1 | tail -n 1
    echo "$fence"
  } > "$dir/body" 2>&1
  size=$(wc -c < "$dir/body" | tr -d ' ')
  if [ "$size" -ge 59000 ]; then
    head -c 58000 "$dir/body" > "$dir/body.cut"
    printf '\n**tagliato dalla coda**: il corpo era di %s byte.\n' "$size" >> "$dir/body.cut"
    mv "$dir/body.cut" "$dir/body"
  fi
  # The JSON by plutil, which every Mac has: a dictionary with one string, «body».
  rm -f "$dir/payload.plist" "$dir/payload.json"
  plutil -create xml1 "$dir/payload.plist" \
    && plutil -insert body -string "$(tr -d '\000-\010\013\014\016-\037' < "$dir/body")" "$dir/payload.plist" \
    && plutil -convert json -o "$dir/payload.json" "$dir/payload.plist"
  code=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -X POST -H @"$headers" --data-binary @"$dir/payload.json" \
    "$api/repos/$repository/issues/$issue/comments" 2>>"$log")
  echo "$(date -u +%H:%M:%SZ) il tentativo a +${at}s: HTTP $code" >> "$log"
  [ "$code" = 201 ] && break
done
rm -f "$headers"
exit 0
