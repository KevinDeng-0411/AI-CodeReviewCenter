"""AI 基建工厂（ADR-0001）：LLM/Embedding 单例 + 共享 VectorRecallService。

- LLM: DeepSeek（OpenAI 兼容 API）
- Embedding: Ollama bge-m3（本地，1024 维）
- VectorRecallService: Memory/Knowledge 共用，消除 Java 版两处复制的 embed+store+recall
"""

from functools import lru_cache

from langchain_deepseek import ChatDeepSeek
from langchain_ollama import OllamaEmbeddings

from app.ai.infra.vector_recall import VectorRecallService
from app.core.config import settings


@lru_cache
def get_chat_model() -> ChatDeepSeek:
    """LLM: DeepSeek（ChatDeepSeek 提取 reasoning_content，供 C6 思考过程展示）。

    切 ChatDeepSeek 而非 ChatOpenAI：ChatOpenAI 官方不提取第三方 provider 的
    reasoning_content（langchain-openai 文档明示）。C6 需流式捕获 reasoning。
    """
    return ChatDeepSeek(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=120,
    )


@lru_cache
def get_embedding_model() -> OllamaEmbeddings:
    """Embedding: Ollama bge-m3（本地，1024 维）。"""
    return OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embedding_model,
    )


@lru_cache
def get_vector_recall_service() -> VectorRecallService:
    """共享向量召回服务（Memory/Knowledge 共用，ADR-0001）。"""
    return VectorRecallService(get_embedding_model())
