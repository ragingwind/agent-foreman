#!/bin/sh
# Every commit subject on the branch starts with add:, fix: or change:.
subjects=$(git log --format=%s "$AF_BASE_SHA..$AF_HEAD") || { echo "cannot read the branch's commits"; exit 1; }
[ -n "$subjects" ] || { echo "no commits on the branch"; exit 1; }
bad=$(printf '%s\n' "$subjects" | grep -Ev '^(add|fix|change): ' || true)
[ -z "$bad" ] || { echo "subjects without a kind: $bad"; exit 1; }
