#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
rollback_commit="c54459885e2461e3453eed249846adf76ac296b2"
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
freeze_commit="$(git -C "$repo_root" rev-parse HEAD)"
if [[ -n "$before_status" ]]; then
  echo "[C3 ROLLBACK] main worktree must be clean" >&2
  rmdir "$tmp_root"
  exit 1
fi
if ! git -C "$repo_root" merge-base --is-ancestor "$rollback_commit" "$freeze_commit"; then
  echo "[C3 ROLLBACK] rollback commit is not a freeze ancestor" >&2
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
      echo "[C3 ROLLBACK] detached worktree cleanup failed" >&2
      rc=1
    fi
  fi
  git -C "$repo_root" worktree prune
  if ! rmdir "$tmp_root"; then
    echo "[C3 ROLLBACK] temporary directory cleanup failed" >&2
    rc=1
  fi
  local after_status
  local after_fingerprint
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  after_fingerprint="$(development_fingerprint)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C3 ROLLBACK] main worktree status changed" >&2
    rc=1
  fi
  if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
    echo "[C3 ROLLBACK] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C3 ROLLBACK] PASS worktree_removed=true stacks_removed=true backup_restore=true main_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[C3 ROLLBACK] freeze_commit=$freeze_commit rollback_commit=$rollback_commit"
echo "[C3 ROLLBACK] verify 0005 migration chain and logical backup/restore in disposable databases"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py \
    tests/test_migration.py \
    tests/test_release_backup.py \
    -q -s
)

echo "[C3 ROLLBACK] create detached C2 release worktree"
git -C "$repo_root" worktree add --detach "$worktree" "$rollback_commit"
worktree_added=true
if [[ "$(git -C "$worktree" rev-parse HEAD)" != "$rollback_commit" ]]; then
  echo "[C3 ROLLBACK] detached worktree commit mismatch" >&2
  exit 1
fi

echo "[C3 ROLLBACK] verify C2 evidence and seven-domain mocked baseline"
(
  cd "$worktree/codeaware-py"
  export LLM_API_KEY="rollback-placeholder-not-a-secret"
  uv run python scripts/validate_stage_evidence.py C2
)
(
  cd "$worktree"
  ./codeaware-py/scripts/demo_c2_mocked.sh
)
