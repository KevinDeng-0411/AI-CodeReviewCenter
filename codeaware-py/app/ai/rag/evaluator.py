"""RetrievalEvaluator - 检索质量评估（确定性，召回数量 + match_type）。

实测（2026-08-05）发现 RRF 分数差检测对排名融合无效：
- RRF 分数 = 1/(k+rank) 累加，相邻排名差恒定 ~1/61 - 1/62 ≈ 0.0003
- 命中查询和无关查询的 top5 分数分布几乎相同（向量腿对任何查询都返回 top chunk）
- 单文档多 chunk 命中时 top5 也是相邻分 -> 分数差无法区分"命中正确"和"模糊无关"

所以放弃分数差阈值，改用两个可靠信号：
1. 召回数量 < MIN_RECALL -> 没捞到，重试
2. match_type：top1 为纯 vector 且无任何 keyword/both -> 词法腿未参与，
   对技术词查询是弱信号，触发重试（保留增强；生产 BM25 命中时自然出现 both/keyword）
"""

import logging

from app.ai.rag.hybrid_retriever import ScoredChunk

logger = logging.getLogger(__name__)

MIN_RECALL = 3          # 少于 3 条视为没捞到


class RetrievalEvaluator:
    async def evaluate(self, docs: list[ScoredChunk]) -> bool:
        """返回 True=满意（停止重试），False=不满意（触发重写）。"""
        if len(docs) < MIN_RECALL:
            logger.debug("eval: recall %d < %d -> unsatisfied", len(docs), MIN_RECALL)
            return False
        # match_type 增强：无任何 keyword/both（纯 vector）时视为弱检索
        if not any(d.match_type in ("keyword", "both") for d in docs):
            logger.debug("eval: all single-leg vector -> weak, unsatisfied")
            return False
        logger.debug("eval: satisfied, %d docs", len(docs))
        return True
