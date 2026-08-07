"""RerankerPort + CrossEncoderReranker — 检索后语义精排（ONNX Runtime）。

RRF 融合只基于候选排名，不评估语义相关性。cross-encoder 对 (query, doc) 逐对
打分，从候选池中精选 top_k，解决"召回对但排序不靠前"（semantic_paraphrase /
cross_doc MRR 偏低）。

用 ONNX Runtime 而非 torch：bge-reranker-v2-m3 ONNX 导出推理，无 torch 依赖
（ADR-0009 否决 reranker 的唯一理由），CPU/Metal 均可跑。
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import onnxruntime as ort

if TYPE_CHECKING:
    from app.ai.rag.hybrid_retriever import ScoredChunk

logger = logging.getLogger(__name__)

# 模型文件在项目 models/bge-reranker-v2-m3/ 下（gitignore 不提交权重）
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "bge-reranker-v2-m3"


class RerankerPort(ABC):
    """rerank 窄接口：对 (query, candidates) 打分，返回 top_k 重排结果。"""

    @abstractmethod
    async def rerank(
        self, query: str, candidates: list["ScoredChunk"], top_k: int
    ) -> list["ScoredChunk"]:
        """按语义相关性重排，返回前 top_k。候选不足时原样返回。"""
        ...


class CrossEncoderReranker(RerankerPort):
    """基于 ONNX Runtime 的 bge-reranker-v2-m3 cross-encoder。

    输入格式：`query [SEP] doc`（与 sentence-transformers CrossEncoder 一致）。
    单对打分 CPU ~10-30ms；top-20 批量约 200-600ms。
    """

    def __init__(self, model_dir: Path | str | None = None, max_length: int = 512) -> None:
        from tokenizers import Tokenizer

        model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.max_length = max_length
        try:
            self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
            self.session = ort.InferenceSession(
                str(model_dir / "model.onnx"),
                providers=["CPUExecutionProvider"],
            )
            # 从 ONNX 输入推断是否需要 token_type_ids
            input_names = {i.name for i in self.session.get_inputs()}
            self._has_type_ids = "token_type_ids" in input_names
            self._ready = True
            logger.info("reranker loaded model_dir=%s has_type_ids=%s", model_dir, self._has_type_ids)
        except Exception as exc:
            self._ready = False
            logger.warning(
                "reranker init failed code=RERANKER_INIT_FAILED error=%s "
                "(rerank 降级为纯 RRF)", type(exc).__name__,
            )

    @property
    def ready(self) -> bool:
        return self._ready

    def _encode_pair(self, query: str, doc: str) -> dict[str, np.ndarray]:
        """编码 (query, doc) 对，返回 ONNX 输入。

        tokenizers 库 encode(sequence, pair) 处理 [CLS] query [SEP] doc [SEP]。
        XLM-RoBERTa 无 segment embedding，token_type_ids 恒 0（若模型需要）。
        """
        enc = self.tokenizer.encode(query, doc)
        ids = enc.ids[: self.max_length]
        attn = enc.attention_mask[: self.max_length]
        inputs = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.array([attn], dtype=np.int64),
        }
        if self._has_type_ids:
            inputs["token_type_ids"] = np.zeros_like(np.array([ids], dtype=np.int64))
        return inputs

    def _score(self, inputs: dict[str, np.ndarray]) -> float:
        """单对推理，返回 relevance score。"""
        outputs = self.session.run(None, inputs)
        # cross-encoder 输出 shape [1, num_labels] 或 [1,1]；取 logits[0][0]
        logits = outputs[0]
        return float(logits[0][0])

    async def rerank(
        self, query: str, candidates: list["ScoredChunk"], top_k: int
    ) -> list["ScoredChunk"]:
        if not candidates:
            return []
        if len(candidates) <= top_k:
            return candidates
        if not self._ready:
            return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

        try:
            scores: list[float] = []
            for c in candidates:
                inputs = self._encode_pair(query, c.chunk.chunk_content)
                scores.append(self._score(inputs))
        except Exception as exc:
            logger.warning("rerank failed code=RERANK_INFERENCE_ERROR error=%s", type(exc).__name__)
            return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

        # 按 cross-encoder 相关度降序，并把 score 更新为 rerank 分（前端展示用）
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        top = ranked[:top_k]
        for rel_score, c in top:
            c.score = rel_score
        return [c for _, c in top]
