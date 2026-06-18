package com.aicenter.common.constant;

/**
 * AI 相关常量
 *
 * @author aicenter
 */
public class AiConstants {

    // ======================== 短期记忆 ========================

    /** Redis Key 前缀 — 会话消息 */
    public static final String REDIS_SESSION_MESSAGES = "ai:session:";

    /** Redis Key 前缀 — 会话摘要 */
    public static final String REDIS_SESSION_SUMMARY = "ai:summary:";

    /** 滑动窗口默认大小 */
    public static final int DEFAULT_WINDOW_SIZE = 20;

    /** 摘要触发阈值 */
    public static final int DEFAULT_SUMMARY_THRESHOLD = 10;

    // ======================== RAG ========================

    /** 默认分块大小 (Token) */
    public static final int DEFAULT_CHUNK_SIZE = 500;

    /** 分块重叠大小 (Token) */
    public static final int DEFAULT_CHUNK_OVERLAP = 50;

    /** BM25 检索权重 */
    public static final double BM25_WEIGHT = 0.3;

    /** 向量检索权重 */
    public static final double VECTOR_WEIGHT = 0.7;

    /** 精排 Top-K */
    public static final int RERANK_TOP_K = 5;

    // ======================== Embedding ========================

    /** bge-m3 向量维度 */
    public static final int BGE_M3_DIMENSION = 1024;

    /** Ollama Embedding 模型名 */
    public static final String OLLAMA_EMBEDDING_MODEL = "bge-m3";

    // ======================== AIReadMe 章节 ========================

    public static final String[] AI_README_SECTIONS = {
            "技术架构",
            "核心流程",
            "开发指南",
            "项目结构",
            "业务知识",
            "历史经验"
    };

    // ======================== Code Review 维度 ========================

    public static final String[] REVIEW_DIMENSIONS = {
            "性能优化",
            "安全性",
            "代码质量",
            "可维护性",
            "异常处理",
            "并发安全",
            "资源管理",
            "设计模式"
    };

    private AiConstants() {
    }
}
