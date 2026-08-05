"""RetrievalEvaluator - 检索质量评估（确定性，极差 + 数量检测）。

对 RRF 分数使用相对检测而非绝对值阈值：
- RRF 分数是相对值（取决于候选集大小），固定阈值会让简单问题反复重试、复杂问题被放过
- 极差检测（max - 2nd < 0.01）表示模型分不出高下，检索"模糊"
- 召回 < 3 表示没捞到东西
"""

import logging

from app.ai.rag.hybrid_retriever import ScoredChunk

logger = logging.getLogger(__name__)

MIN_RECALL = 3          # 少于 3 条视为没捞到
SCORE_GAP_MIN = 0.01    # 最高分与次高分差距小于此值视为模糊


class RetrievalEvaluator:
    async def evaluate(self, docs: list[ScoredChunk]) -> bool:
        """返回 True=满意（停止重试），False=不满意（触发重写）。"""
        scores = sorted((d.score for d in docs), reverse=True)
        if len(scores) < MIN_RECALL:
            logger.debug("eval: recall %d < %d -> unsatisfied", len(scores), MIN_RECALL)
            return False
        if len(scores) >= 2 and (scores[0] - scores[1]) < SCORE_GAP_MIN:
            logger.debug(
                "eval: score gap %.4f < %.3f -> unsatisfied",
                scores[0] - scores[1],
                SCORE_GAP_MIN,
            )
            return False
        logger.debug("eval: satisfied, top score %.4f", scores[0])
        return True
