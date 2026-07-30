#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
implementation_commit="2a0a4e948e20e3d9ff5dbc24ca9d7a1c5b009231"
implementation_parent="b683425c9af7c5cd24d44e8a7d88764bd0590406"
tmp_root="$(mktemp -d)"
worktree="$tmp_root/worktree"
worktree_added=false

development_fingerprint() {
  {
    docker compose -f "$repo_root/docker-compose.yml" ps -a \
      --format '{{.ID}}|{{.Name}}|{{.State}}|{{.Image}}' 2>/dev/null | sort || true
    docker volume inspect \
      ai-center_pgdata ai-center_redisdata ai-center_ollamadata \
      --format '{{.Name}}|{{.Driver}}|{{index .Labels "com.docker.compose.project"}}' \
      2>/dev/null | sort || true
  }
}

before_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
before_fingerprint="$(development_fingerprint)"
if [[ -n "$before_status" ]]; then
  echo "[C1 ROLLBACK] main worktree must be clean" >&2
  rmdir "$tmp_root"
  exit 1
fi
if [[ "$(git -C "$repo_root" rev-parse "$implementation_commit^")" != "$implementation_parent" ]]; then
  echo "[C1 ROLLBACK] implementation parent mismatch" >&2
  rmdir "$tmp_root"
  exit 1
fi

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$worktree_added" == true ]]; then
    git -C "$repo_root" worktree remove --force "$worktree"
    if [[ $? -ne 0 ]]; then
      echo "[C1 ROLLBACK] detached worktree cleanup failed" >&2
      rc=1
    fi
  fi
  git -C "$repo_root" worktree prune
  rmdir "$tmp_root"
  if [[ $? -ne 0 ]]; then
    echo "[C1 ROLLBACK] temporary directory cleanup failed" >&2
    rc=1
  fi
  local after_status
  local after_fingerprint
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  after_fingerprint="$(development_fingerprint)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C1 ROLLBACK] main worktree status changed" >&2
    rc=1
  fi
  if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
    echo "[C1 ROLLBACK] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C1 ROLLBACK] PASS worktree_removed=true stacks_removed=true main_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[C1 ROLLBACK] verify current migration downgrade/upgrade chain"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py tests/test_migration.py -q
)

echo "[C1 ROLLBACK] create detached parent worktree commit=$implementation_parent"
git -C "$repo_root" worktree add --detach "$worktree" "$implementation_parent"
worktree_added=true
if [[ "$(git -C "$worktree" rev-parse HEAD)" != "$implementation_parent" ]]; then
  echo "[C1 ROLLBACK] detached worktree commit mismatch" >&2
  exit 1
fi

echo "[C1 ROLLBACK] verify parent C1-A/C1-B/C1-C baseline in disposable stack"
(
  cd "$worktree/codeaware-py"
  # The historical parent creates the ChatOpenAI dependency before FastAPI
  # rejects malformed requests. A non-secret placeholder keeps this
  # deterministic; all model paths in the selected tests remain mocked.
  export LLM_API_KEY="rollback-placeholder-not-a-secret"
  uv run python scripts/run_tests_safe.py \
    tests/test_chat.py \
    tests/test_chat_summary.py \
    tests/test_knowledge_upload.py \
    tests/test_migration.py \
    -q
)
