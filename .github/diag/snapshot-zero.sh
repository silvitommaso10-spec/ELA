#!/bin/sh
# Snapshot zero of the observation (decision 82 (c) of the branch m13.11-il-browser-sul-pc), on
# the branch diag-m13.11-osservazione only, which never enters main: before `make check`, the image
# and its version, the cores, the memory and the free disk, into the folder of the suite's log.
#
# Usage: sh .github/diag/snapshot-zero.sh <folder> <variant>
# Whatever fails here fails a line, never the job: no `set -e`, and every exit is 0.
folder=$1
variant=$2
[ -n "$folder" ] || exit 0
mkdir -p "$folder" 2>/dev/null || exit 0
{
  echo "=== snapshot zero: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "variant: $variant"
  echo "commit: $GITHUB_SHA"
  echo "image: ImageOS=$ImageOS ImageVersion=$ImageVersion"
  echo "runner: $RUNNER_NAME, $RUNNER_OS, $RUNNER_ARCH"
  uname -a
  case $(uname -s) in
    Darwin)
      sw_vers
      echo "cores: $(sysctl -n hw.ncpu), physical $(sysctl -n hw.physicalcpu)"
      echo "memory bytes: $(sysctl -n hw.memsize)"
      echo "memorystatus_level: $(sysctl -n kern.memorystatus_level)"
      echo "swap: $(sysctl -n vm.swapusage)"
      ;;
    *)
      cat /etc/os-release
      echo "cores: $(nproc)"
      free -m
      ;;
  esac
  echo "TMPDIR: ${TMPDIR:-unset}"
  df -Pk / "$folder" "${TMPDIR:-/tmp}"
  df -h
} > "$folder/snapshot-zero.txt" 2>&1
exit 0
