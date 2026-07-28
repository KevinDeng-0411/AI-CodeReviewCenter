"""P2：embedding 维度验证。

- test_fake_embedder_dim：mock 路径 1024 维接线（CI，默认跑）。
- test_real_ollama_embedding_dim：真实 bge-m3 1024 维（integration，默认跳过）。
"""

import pytest


async def test_fake_embedder_dim(mock_embedder):
    vec = await mock_embedder.aembed_query("测试")
    assert len(vec) == 1024


@pytest.mark.integration
async def test_real_ollama_embedding_dim():
    """真实 Ollama bge-m3 -> 1024 维。需 Ollama 运行 + bge-m3 已拉取。

    跑法：uv run pytest -m integration tests/test_embedding_dim.py::test_real_ollama_embedding_dim
    """
    from app.ai.config import get_embedding_model

    vec = await get_embedding_model().aembed_query("测试")
    assert len(vec) == 1024
