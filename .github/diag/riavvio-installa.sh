#!/bin/sh
# The witness of a restart (decision 120 (b) of the branch m13.11-il-browser-sul-pc), on the branch
# diag-m13.11-osservazione only, which never enters main. At the start of the job it writes a
# LaunchDaemon that is NOT loaded now: launchd reads it only at the next start of the machine. If
# the machine starts again with its disk, riavvio.sh sends one comment «RIAVVIATA» to the issue,
# trying at 30, 60 and 120 seconds from the start. The token goes into a file only root reads,
# through a file of this process's own, never in an argument. Best effort: whatever fails here
# fails the witness, never the job; every exit is 0.
#
# Usage: sh riavvio-installa.sh <tools folder> <label> <issue> <file of the sampler>
# DIAG_ROOT, empty on the runner, is a folder put before every system path: the proof on the Mac
# uses it, with a sudo of its own, so that nothing is written in the Mac's /Library.
tools=$1
label=$2
issue=$3
sampler=$4
root=${DIAG_ROOT:-}
name=com.ela.diag.riavvio
dir="$root/Library/Application Support/ela-diag-riavvio"
plist="$root/Library/LaunchDaemons/$name.plist"
if [ -z "$GH_TOKEN" ] || [ -z "$GITHUB_REPOSITORY" ] || [ -z "$label" ] || [ -z "$issue" ]; then
  echo "il testimone non si installa: manca il token, il repository, l'etichetta o la issue"
  exit 0
fi
umask 077
work=$(mktemp -d 2>/dev/null) || exit 0
printf '%s' "$GH_TOKEN" > "$work/token"
{
  echo "label='$label'"
  echo "issue='$issue'"
  echo "repository='$GITHUB_REPOSITORY'"
  echo "run='$GITHUB_RUN_ID'"
  echo "api='${BLACKBOX_API:-https://api.github.com}'"
  echo "sampler='$sampler'"
  echo "reports='$root/Library/Logs/DiagnosticReports'"
} > "$work/config"
cat > "$work/plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$name</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$dir/riavvio.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$dir/riavvio.log</string>
  <key>StandardErrorPath</key>
  <string>$dir/riavvio.log</string>
</dict>
</plist>
PLIST
sudo -n mkdir -p "$dir" "$root/Library/LaunchDaemons"
sudo -n chmod 700 "$dir"
sudo -n install -o root -g wheel -m 600 "$work/token" "$dir/token"
sudo -n install -o root -g wheel -m 600 "$work/config" "$dir/config"
sudo -n install -o root -g wheel -m 700 "$tools/riavvio.sh" "$dir/riavvio.sh"
sudo -n install -o root -g wheel -m 644 "$work/plist" "$plist"
rm -rf "$work"
echo "il LaunchDaemon: $plist"
plutil -lint "$plist" 2>&1
if sudo -n launchctl print "system/$name" > /dev/null 2>&1; then
  echo "caricato adesso: SÌ — non doveva esserlo"
else
  echo "caricato adesso: no — partirà solo al prossimo avvio della macchina"
fi
sudo -n ls -l "$dir" "$plist" 2>&1
exit 0
