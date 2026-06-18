package com.aicenter.ai.memory;

import com.aicenter.model.entity.LongTermMemory;
import com.aicenter.model.mapper.LongTermMemoryMapper;
import com.aicenter.model.vo.LongTermMemoryVO;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.store.embedding.EmbeddingSearchRequest;
import dev.langchain4j.store.embedding.EmbeddingStore;
import dev.langchain4j.store.embedding.EmbeddingMatch;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 长期记忆管理器 — 基于 Pinecone 向量存储
 * <p>
 * 「主动录入 + 向量化存储(Pinecone) + 语义相似度召回」
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LongTermMemoryManager {

    private final LongTermMemoryMapper memoryMapper;
    private final EmbeddingModel embeddingModel;
    private final EmbeddingStore<TextSegment> embeddingStore;

    /**
     * 保存长期记忆（先写 MySQL 获取 ID，再向量化存入 Pinecone）
     */
    public LongTermMemory saveMemory(String sessionId, String content, String memoryType,
                                      String metadata) {
        // 1. 先插入 MySQL 获取自增 ID
        LongTermMemory memory = new LongTermMemory()
                .setSessionId(sessionId)
                .setContent(content)
                .setMemoryType(memoryType)
                .setMetadata(metadata != null ? metadata : "{}");
        memoryMapper.insert(memory);

        // 2. 向量化并存入 Pinecone（内容从 MySQL 查找，这里只存 ID + 向量）
        Embedding embedding = embeddingModel.embed(content).content();
        embeddingStore.add("memory:" + memory.getId(), embedding);

        log.info("长期记忆已保存(Pinecone): id={}, type={}", memory.getId(), memoryType);
        return memory;
    }

    /**
     * 语义召回 Top-K 记忆（通过 Pinecone 向量检索）
     */
    public List<LongTermMemoryVO> recall(String query, double threshold, int topK) {
        // 1. 查询向量化
        Embedding queryEmbedding = embeddingModel.embed(query).content();

        // 2. Pinecone 向量检索
        var searchResult = embeddingStore.search(
                EmbeddingSearchRequest.builder()
                        .queryEmbedding(queryEmbedding)
                        .maxResults(topK)
                        .minScore(threshold)
                        .build()
        );

        // 3. 转换结果
        List<LongTermMemoryVO> results = new ArrayList<>();
        for (EmbeddingMatch<TextSegment> match : searchResult.matches()) {
            Long pgId = extractPgId(match.embeddingId());
            LongTermMemory memory = pgId != null ? memoryMapper.selectById(pgId) : null;

            LongTermMemoryVO vo = new LongTermMemoryVO();
            vo.setId(pgId);
            vo.setContent(memory != null ? memory.getContent() : match.embedded().text());
            vo.setMemoryType(memory != null ? memory.getMemoryType() : "KNOWLEDGE");
            vo.setSimilarity(Math.round(match.score() * 10000.0) / 10000.0);
            vo.setCreatedAt(memory != null ? memory.getCreatedAt() : null);
            results.add(vo);
        }

        log.info("长期记忆召回(Pinecone): query={}, matches={}", query, results.size());
        return results;
    }

    /**
     * 删除长期记忆
     */
    public void deleteMemory(Long id) {
        memoryMapper.deleteById(id);
        embeddingStore.remove("memory:" + id);
    }

    private Long extractPgId(String embeddingId) {
        if (embeddingId != null && embeddingId.startsWith("memory:")) {
            return Long.parseLong(embeddingId.substring("memory:".length()));
        }
        return null;
    }
}
