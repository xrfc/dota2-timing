#!/usr/bin/env bash
# Run one blind batch: run_batch.sh <batch-file>. Read-only sandbox, empty cwd, no session saved.
set -u
root="$(cd "$(dirname "$0")" && pwd)"
batch="$1"; name="$(basename "$batch" .json)"
out="$root/results/$name.json"
[ -s "$out" ] && exit 0
cat "$root/rules.md" "$batch" | "$HOME/.npm-global/bin/codex" exec -m gpt-6.1-sol -c model_reasoning_effort=high --sandbox read-only --skip-git-repo-check --ephemeral \
  -C "${EMPTY_CWD:?}" --output-schema "$root/schema.json" -o "$out" - > "$root/results/$name.log" 2>&1
echo "$name exit=$?"
