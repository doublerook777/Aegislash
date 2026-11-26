#!/usr/bin/env bash
# Score several versions of aegis/detect on the same fresh cases, with the network off.
#   bash experiments/presidio/score_versions.sh <folder with lines.jsonl and files.jsonl> [revision ...]
# Default revisions: a7faabf (before the header fixes), c05e814 (only those fixes added), cb90eb4 (the merged PR branch,
# which also holds other pull requests) and origin/main. Prints totals only, no case text, so the cases stay unread.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(git -C "$here" rev-parse --show-toplevel)"
cases="$(cd "$1" && pwd)"; shift
[ "$#" -gt 0 ] || set -- a7faabf c05e814 cb90eb4 origin/main
sha256sum "$cases/lines.jsonl" "$cases/files.jsonl"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
for rev in "$@"; do
  side="$work/$(git -C "$repo" rev-parse --short "$rev^{commit}")"
  mkdir -p "$side/experiments/presidio"
  git -C "$repo" archive "$rev" aegis | tar -x -C "$side"
  cp "$here"/{common,run_setup,fresh_test}.py "$side/experiments/presidio/"
  echo "== $rev ($(basename "$side"))"
  (cd "$side/experiments/presidio" && env -i PATH="$PATH" HOME="$work" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
     unshare -rn "$here/.venv/bin/python" fresh_test.py "$cases" --ours-only) | awk '
       /format problems/ {print} /^    case / {print} /^network off/ {print}
       /^### / {title=substr($0,5)} /^\| ALL \|/ {split($0,c,"|"); printf "%-36s%s", title, c[3]}
       /^\| 95% range, ALL/ {split($0,c,"|"); printf "  (95%% range%s)\n", c[3]}'
done
