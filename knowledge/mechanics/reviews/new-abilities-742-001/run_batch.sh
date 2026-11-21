#!/usr/bin/env bash
# Run one blind batch: run_batch.sh <batch-file>. Read-only sandbox, empty cwd, no session saved.
# Model gpt-6.2-astra, reasoning effort high (U180); account chosen by codex-prefer.
set -u
root="$(cd "$(dirname "$0")" && pwd)"
batch="$1"; name="$(basename "$batch" .json)"
out="$root/results/$name.json"
[ -s "$out" ] && exit 0
cat "$root/prompt.md" "$batch" | "$HOME/.local/bin/codex-prefer" exec --sandbox read-only \
  --skip-git-repo-check --ephemeral -m gpt-6.2-astra -c model_reasoning_effort=high \
  -C "${EMPTY_CWD:?}" --output-schema "$root/schema.json" -o "$out" - > "$root/results/$name.log" 2>&1
echo "$name exit=$?"
