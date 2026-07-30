#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"

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

echo "[C2 MOCKED] route-level seven-domain closure"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py \
    tests/e2e/test_code_review_unit_test.py::test_c2b_demo_code_review_unit_test_route_closure \
    tests/e2e/test_prompt.py::test_c2c_demo_prompt_version_preview_rollback \
    tests/e2e/test_knowledge_memory.py::test_c2d_demo_knowledge_memory_closure \
    tests/e2e/test_chat_ai_readme.py::test_c2e_demo_chat_and_ai_readme_closure \
    -q -s
)

echo "[PASS] Code Review: result + record + filter/detail"
echo "[PASS] Unit Test: result + record + filter/detail"
echo "[PASS] AIReadMe: snapshot + version + latest"
echo "[PASS] Chat: typed SSE + cid + summary/continuation regression"
echo "[PASS] Knowledge: text/file + hybrid search + cascade delete"
echo "[PASS] Memory: manual/automatic + recall + delete"
echo "[PASS] Prompt: create v2 + preview + rollback"

after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
after_fingerprint="$(development_fingerprint)"
if [[ "$before_status" != "$after_status" ]]; then
  echo "[C2 MOCKED] repository status changed during demo" >&2
  exit 1
fi
if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
  echo "[C2 MOCKED] development Docker resource fingerprint changed" >&2
  exit 1
fi

echo "[C2 MOCKED] PASS repository_status_unchanged=true development_resources_unchanged=true"
