#!/bin/sh
# One round of the observation (decision 82 (c) of the branch m13.11-il-browser-sul-pc), on the
# branch diag-m13.11-osservazione only, which never enters main. It waits up to <seconds>, and
# leaves early when `make check`, in the background, has written its exit code; then it copies the
# folder of the suite's log into <copy>, which the next step carries away as an artifact — what
# the machine knows leaves it every round, before the machine can die with it.
#
# Usage: sh .github/diag/round.sh <folder> <copy> [seconds, 120]
# It tells the workflow two things: `went=1` in the step's outputs, so that the snapshot of this
# round is carried away; and `DONE=1` in the job's environment once `make check` has ended, so
# that the rounds left are skipped. Every exit is 0.
folder=$1
copy=$2
seconds=${3:-120}
exit_file=$folder/make-check-exit.txt
waited=0
while [ ! -f "$exit_file" ] && [ "$waited" -lt "$seconds" ]; do
  sleep 5
  waited=$((waited + 5))
done
[ -f "$exit_file" ] && [ -n "$GITHUB_ENV" ] && echo "DONE=1" >> "$GITHUB_ENV"
rm -rf "$copy" 2>/dev/null
mkdir -p "$copy" 2>/dev/null
cp -R "$folder"/. "$copy"/ 2>/dev/null
{
  echo "round: $(date -u +%Y-%m-%dT%H:%M:%SZ), waited ${waited}s of ${seconds}s"
  df -Pk / "$folder" "${TMPDIR:-/tmp}"
} > "$copy/round.txt" 2>&1
[ -n "$GITHUB_OUTPUT" ] && echo "went=1" >> "$GITHUB_OUTPUT"
exit 0
