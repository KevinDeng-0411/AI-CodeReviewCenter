#!/bin/bash
# C4-C demo: BM25 混合检索 5 项闭环演示。
# 使用一次性 PG/Redis（safe runner），FakeEmbedder（确定性，不需 Ollama）。
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "=== C4 BM25 混合检索演示 ==="
echo "5 项闭环：rare identifier / semantic paraphrase / exact mixed / fallback / rollback"
echo ""

(cd codeaware-py && uv run python scripts/run_tests_safe.py tests/test_bm25_retriever.py -v 2>&1 | grep -E "PASSED|FAILED|C4 BM25|rare|semantic|mixed|unavailable|rollback")

echo ""
echo "=== 演示完成 ==="
