#!/bin/sh
# The witness outside the session (decisions 128 and 132 of the branch m13.11-il-browser-sul-pc), on
# the branch diag-m13.11-osservazione only, which never enters main. It writes a LaunchDaemon of the
# system and loads it at once (`launchctl bootstrap system`): testimone.sh runs as root, outside the
# graphical session of the user runner, and says on the issue whether WindowServer, loginwindow, the
# console's user or Runner.Listener change, and which reports of a crash are born. The token goes
# into a file only root reads, through a file of this process's own, never in an argument. Best
# effort: whatever fails here fails the witness, never the job; every exit is 0.
#
# Usage: sh testimone-installa.sh <tools folder> <label> <issue> <file of make check's exit code>
# DIAG_ROOT, empty on the runner, is a folder put before every system path: the proof on the Mac
# uses it, with a sudo and a launchctl of its own, so that nothing is written in the Mac's /Library.
tools=$1
label=$2
issue=$3
exit_file=$4
root=${DIAG_ROOT:-}
name=com.ela.diag.testimone
dir="$root/Library/Application Support/ela-diag-testimone"
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
  echo "exit_file='$exit_file'"
  echo "root='$root'"
  echo "runner_home='$HOME'"
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
    <string>$dir/testimone.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$dir/testimone.log</string>
  <key>StandardErrorPath</key>
  <string>$dir/testimone.log</string>
</dict>
</plist>
PLIST
sudo -n mkdir -p "$dir" "$root/Library/LaunchDaemons"
sudo -n chmod 700 "$dir"
sudo -n install -o root -g wheel -m 600 "$work/token" "$dir/token"
sudo -n install -o root -g wheel -m 600 "$work/config" "$dir/config"
sudo -n install -o root -g wheel -m 700 "$tools/testimone.sh" "$dir/testimone.sh"
sudo -n install -o root -g wheel -m 644 "$work/plist" "$plist"
rm -rf "$work"
echo "il LaunchDaemon: $plist"
plutil -lint "$plist" 2>&1
sudo -n launchctl bootstrap system "$plist" 2>&1 && echo "launchctl bootstrap system: fatto"
sleep 2
sudo -n launchctl print "system/$name" 2>&1 | grep -E '^\s*(state|pid|last exit code) =' || echo "launchctl print: niente"
sudo -n ls -l "$dir" "$plist" 2>&1
exit 0
