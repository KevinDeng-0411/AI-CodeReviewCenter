#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
baseline_commit="094ede8b24ee396b860461f62e34ea5a31cee96c"
implementation_commit="cd217c8817ed81ddb19fc8268d350300e57cae91"
implementation_parent="2aaf35f7c75088bd84f37afc7be5f14feab72bc3"
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
  echo "[C2 ROLLBACK] main worktree must be clean" >&2
  rmdir "$tmp_root"
  exit 1
fi
if [[ "$(git -C "$repo_root" rev-parse "$implementation_commit^")" != "$implementation_parent" ]]; then
  echo "[C2 ROLLBACK] implementation parent mismatch" >&2
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
      echo "[C2 ROLLBACK] detached worktree cleanup failed" >&2
      rc=1
    fi
  fi
  git -C "$repo_root" worktree prune
  rmdir "$tmp_root"
  if [[ $? -ne 0 ]]; then
    echo "[C2 ROLLBACK] temporary directory cleanup failed" >&2
    rc=1
  fi
  local after_status
  local after_fingerprint
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  after_fingerprint="$(development_fingerprint)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C2 ROLLBACK] main worktree status changed" >&2
    rc=1
  fi
  if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
    echo "[C2 ROLLBACK] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C2 ROLLBACK] PASS worktree_removed=true stacks_removed=true main_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[C2 ROLLBACK] verify 0005 downgrade/upgrade chain in disposable database"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py tests/test_migration.py -q
)

echo "[C2 ROLLBACK] create detached C1 baseline worktree commit=$baseline_commit"
git -C "$repo_root" worktree add --detach "$worktree" "$baseline_commit"
worktree_added=true
if [[ "$(git -C "$worktree" rev-parse HEAD)" != "$baseline_commit" ]]; then
  echo "[C2 ROLLBACK] detached worktree commit mismatch" >&2
  exit 1
fi

echo "[C2 ROLLBACK] verify C1 evidence and representative baseline behavior"
(
  cd "$worktree/codeaware-py"
  export LLM_API_KEY="rollback-placeholder-not-a-secret"
  uv run python scripts/validate_stage_evidence.py C1
  uv run python scripts/run_tests_safe.py \
    tests/test_chat.py \
    tests/test_chat_summary.py \
    tests/test_knowledge_upload.py \
    tests/test_ai_readme_snapshot.py \
    -q
)
