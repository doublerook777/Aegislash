#!/usr/bin/env bash
# Run every setup with the network OFF (own network namespace), 2 CPUs, and an empty HOME (no caches).
# Linux only (unshare, taskset). Usage: bash experiments/presidio/run_all.sh [repeats]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repeats="${1:-3}"
mkdir -p "$here/out"
: > "$here/out/timings.txt"
for dataset in dev selftest; do
  for setup in ours lg lg_ctx sm xx; do
    for _ in $(seq "$repeats"); do
      empty_home="$(mktemp -d)"
      env -i PATH="$PATH" HOME="$empty_home" LANG=C.UTF-8 OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
        unshare -rn taskset -c 0,1 "$here/.venv/bin/python" "$here/run_setup.py" "$setup" "$dataset" \
        | tee -a "$here/out/timings.txt"
      rm -rf "$empty_home"
    done
  done
done
"$here/.venv/bin/python" "$here/score.py"
