package com.aicenter.ai.memory;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
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
 * 长期记忆管理器 — PGVector 向量存储
 * <p>
 * 「录入 → Ollama bge-m3 向量化 → PGVector → 语义召回」
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
     * 保存长期记忆（PG 元数据 + PGVector 向量）
     */
    public LongTermMemory saveMemory(String sessionId, String content, String memoryType,
                                      String metadata) {
        // 插入 PG 元数据
        LongTermMemory memory = new LongTermMemory()
                .setSessionId(sessionId)
                .setContent(content)
                .setMemoryType(memoryType)
                .setMetadata(metadata != null ? metadata : "{}");
        memoryMapper.insert(memory);

        // 向量化 + 存入 PGVector（UUID 作为 key）
        Embedding embedding = embeddingModel.embed(content).content();
        String uuid = java.util.UUID.randomUUID().toString();
        embeddingStore.add(uuid, embedding);
        // 反向索引写入 PG 记录
        memory.setEmbedding(uuid);
        memoryMapper.updateById(memory);

        log.info("长期记忆已保存(PGVector): id={}, type={}", memory.getId(), memoryType);
        return memory;
    }

    /**
     * 语义召回（PGVector 向量检索）
     */
    public List<LongTermMemoryVO> recall(String query, double threshold, int topK) {
        Embedding queryEmbedding = embeddingModel.embed(query).content();

        var searchResult = embeddingStore.search(
                EmbeddingSearchRequest.builder()
                        .queryEmbedding(queryEmbedding)
                        .maxResults(topK)
                        .minScore(threshold)
                        .build()
        );

        List<LongTermMemoryVO> results = new ArrayList<>();
        for (EmbeddingMatch<TextSegment> match : searchResult.matches()) {
            String uuid = match.embeddingId();
            // 通过 UUID 查找 PG 记录
            LongTermMemory memory = memoryMapper.selectOne(
                    new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<LongTermMemory>()
                            .eq(LongTermMemory::getEmbedding, uuid));

            LongTermMemoryVO vo = new LongTermMemoryVO();
            vo.setId(memory != null ? memory.getId() : null);
            vo.setContent(memory != null ? memory.getContent() : "unknown");
            vo.setMemoryType(memory != null ? memory.getMemoryType() : "KNOWLEDGE");
            vo.setSimilarity(Math.round(match.score() * 10000.0) / 10000.0);
            vo.setCreatedAt(memory != null ? memory.getCreatedAt() : null);
            results.add(vo);
        }

        log.info("长期记忆召回(PGVector): query={}, matches={}", query, results.size());
        return results;
    }

    public void deleteMemory(Long id) {
        var memory = memoryMapper.selectById(id);
        if (memory != null && memory.getEmbedding() != null) {
            embeddingStore.remove(memory.getEmbedding());
        }
        memoryMapper.deleteById(id);
    }

}
