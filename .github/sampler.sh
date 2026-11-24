#!/bin/sh
# The machine's sampler (answer 67 B of the branch m13.11-il-browser-sul-pc): an instrument, not a
# defence. On 2026-11-20 the macOS runner lost communication twice during `make check`, 53 and 56
# minutes into the step, and left no log: what the machine was doing is what this file writes.
#
# Usage: sh .github/sampler.sh <folder> [seconds between samples, 30] [seconds at most, 5400]
#
# Every sample is appended to <folder>/machine.txt: the time, the load, the memory as the system
# gives it (free, used, swap), and the processes by name — how many, and their resident memory
# summed (a page shared by two processes counts twice: not the memory the machine used). The step
# before `make check` starts it in the background in the folder of the suite's log, so the step
# of the log carries it away in the same artifact. It stops by itself after its seconds at most,
# and the end of the job stops it before. Whatever fails here fails the sample, never the job: no
# `set -e`, and every exit is 0.
#
# On the branch diag-m13.11-osservazione only, which never enters main (decision 82 (d) of the
# branch m13.11-il-browser-sul-pc): the workflow of the observation calls it every ten seconds,
# and every sample also writes the free disk — `df -Pk` of the root, of the folder and of the
# process's temporary folder — and, on macOS, the percentage of memory the kernel gives as
# available, `kern.memorystatus_level`. ***Since 2026-11-24*** (decision 101), on macOS, every sample
# also writes how many mdworker_shared there are, counted on every process with `pgrep -x`: the
# list by name below keeps the 40 names with the most memory, and a few small ones stay under it.
# ***Since 2026-11-24*** (decision 111 (b)), on macOS, also six counters of sysctl: kern.num_files,
# kern.maxfiles, kern.maxproc, kern.maxprocperuid, kern.num_tasks, kern.num_threads.
folder=$1
every=${2:-30}
most=${3:-5400}
[ -n "$folder" ] || exit 0
mkdir -p "$folder" 2>/dev/null || exit 0
out=$folder/machine.txt
start=$(date +%s)
echo "=== sampler: $(uname -sm), $(getconf _NPROCESSORS_ONLN) cpus, every ${every}s, at most ${most}s" >> "$out" 2>/dev/null
while :; do
  now=$(date +%s)
  [ $((now - start)) -gt "$most" ] && exit 0
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) +$((now - start))s"
    echo "load: $(uptime)"
    case $(uname -s) in
      Darwin)
        vm_stat | awk -v total="$(sysctl -n hw.memsize)" '
          /page size of/ { size = $8 }
          /^Pages free/ { free = $3 } /^Pages active/ { active = $3 } /^Pages inactive/ { inactive = $3 }
          /^Pages speculative/ { speculative = $3 } /^Pages wired down/ { wired = $4 }
          /^Pages occupied by compressor/ { compressed = $5 }
          END {
            mb = size / 1048576
            printf "memory MB: total %d, used %d (active, wired, compressed), free %d, speculative %d, inactive %d\n",
              total / 1048576, (active + wired + compressed) * mb, free * mb, speculative * mb, inactive * mb
            printf "memory MB: active %d, wired %d, compressed %d\n", active * mb, wired * mb, compressed * mb
          }'
        echo "swap: $(sysctl -n vm.swapusage)"
        echo "memorystatus_level: $(sysctl -n kern.memorystatus_level)"
        echo "mdworker_shared: $(pgrep -x mdworker_shared | wc -l | tr -d ' ')"
        echo "sysctl: $(for name in kern.num_files kern.maxfiles kern.maxproc kern.maxprocperuid kern.num_tasks kern.num_threads; do printf '%s=%s ' "$name" "$(sysctl -n "$name" 2>&1)"; done)"
        ;;
      *)
        free -m
        ;;
    esac
    echo "disk:"
    df -Pk / "$folder" "${TMPDIR:-/tmp}"
    echo "processes: $(ps -A -o pid= | wc -l | tr -d ' ')"
    ps -A -o rss= -o comm= | awk '
      { rss = $1; $1 = ""; sub(/^ +/, ""); n = split($0, part, "/"); name = part[n]; count[name]++; memory[name] += rss }
      END { for (name in count) printf "%9d KB %5d  %s\n", memory[name], count[name], name }' | sort -rn | head -40
  } >> "$out" 2>&1
  sleep "$every"
done
