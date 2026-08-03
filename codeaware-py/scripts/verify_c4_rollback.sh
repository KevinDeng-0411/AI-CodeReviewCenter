#!/usr/bin/env bash
# C4 回退验证：证明 BM25 增强（migration 0006 + BM25 索引）可安全回退到 C3 pg_trgm。
# 0006 只加索引、不改数据，回退 = DROP INDEX + RAG_LEXICAL_BACKEND=pg_trgm（默认）。
# 在一次性 PG/Redis 验证 0006 迁移链 + 逻辑备份/恢复；detached worktree 到 C3 冻结点
# 验证 pg_trgm 检索仍可用。主工作区与开发 Docker 资源不变。
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
rollback_commit="3f95543c1fb31e630e233332c1bfed850e855c21"
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
  echo "[C4 ROLLBACK] main worktree must be clean" >&2
  rmdir "$tmp_root"
  exit 1
fi
if ! git -C "$repo_root" merge-base --is-ancestor "$rollback_commit" "$freeze_commit"; then
  echo "[C4 ROLLBACK] rollback commit is not a freeze ancestor" >&2
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
      echo "[C4 ROLLBACK] detached worktree cleanup failed" >&2
      rc=1
    fi
  fi
  git -C "$repo_root" worktree prune
  if ! rmdir "$tmp_root"; then
    echo "[C4 ROLLBACK] temporary directory cleanup failed" >&2
    rc=1
  fi
  local after_status
  local after_fingerprint
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  after_fingerprint="$(development_fingerprint)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C4 ROLLBACK] main worktree status changed" >&2
    rc=1
  fi
  if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
    echo "[C4 ROLLBACK] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C4 ROLLBACK] PASS worktree_removed=true stacks_removed=true backup_restore=true main_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[C4 ROLLBACK] freeze_commit=$freeze_commit rollback_commit=$rollback_commit"
echo "[C4 ROLLBACK] verify 0006 migration chain and logical backup/restore in disposable databases"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py \
    tests/test_migration.py \
    tests/test_release_backup.py \
    -q -s
)

echo "[C4 ROLLBACK] create detached C3 freeze worktree (pg_trgm baseline, no BM25)"
git -C "$repo_root" worktree add --detach "$worktree" "$rollback_commit"
worktree_added=true
if [[ "$(git -C "$worktree" rev-parse HEAD)" != "$rollback_commit" ]]; then
  echo "[C4 ROLLBACK] detached worktree commit mismatch" >&2
  exit 1
fi

echo "[C4 ROLLBACK] verify C3 evidence and pg_trgm hybrid retrieval at rolled-back state"
(
  cd "$worktree/codeaware-py"
  export LLM_API_KEY="rollback-placeholder-not-a-secret"
  uv run python scripts/validate_stage_evidence.py C3
)
(
  cd "$worktree/codeaware-py"
  uv run python scripts/run_tests_safe.py tests/test_hybrid_retriever.py -q
)
