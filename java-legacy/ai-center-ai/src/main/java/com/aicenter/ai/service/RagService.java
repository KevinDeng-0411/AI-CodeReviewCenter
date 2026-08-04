package com.aicenter.ai.service;

import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.ai.rag.QueryRewriter;
import com.aicenter.ai.rag.SemanticChunker;
import com.aicenter.model.entity.KnowledgeDocument;
import com.aicenter.model.mapper.KnowledgeDocumentMapper;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.store.embedding.EmbeddingStore;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * RAG 检索增强生成服务
 * <p>
 * 「查询重写 → 语义分块 → 混合检索(BM25+PGVector) → 知识注入」
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RagService {

    private final QueryRewriter queryRewriter;
    private final SemanticChunker semanticChunker;
    private final HybridRetriever hybridRetriever;
    private final KnowledgeDocumentMapper documentMapper;
    private final EmbeddingModel embeddingModel;
    private final EmbeddingStore<TextSegment> embeddingStore;

    /**
     * 上传知识文档（分块 + 向量化 → PGVector）
     */
    public int uploadDocument(String title, String content, String sourceType, String projectName) {
        List<String> chunks = semanticChunker.chunk(content);
        log.info("文档分块完成: title={}, chunks={}", title, chunks.size());

        int count = 0;
        for (int i = 0; i < chunks.size(); i++) {
            // 插入关系元数据到 PG
            KnowledgeDocument doc = new KnowledgeDocument()
                    .setTitle(title)
                    .setContent(content)
                    .setChunkIndex(i)
                    .setChunkContent(chunks.get(i))
                    .setSourceType(sourceType)
                    .setProjectName(projectName);
            documentMapper.insert(doc);

            // 向量化 + 存入 PGVector（UUID 作为 key）
            Embedding embedding = embeddingModel.embed(chunks.get(i)).content();
            String uuid = java.util.UUID.randomUUID().toString();
            embeddingStore.add(uuid, embedding);
            // 反向索引写入 PG 记录
            doc.setEmbedding(uuid);
            documentMapper.updateById(doc);
            count++;
        }

        log.info("知识文档上传完成(PGVector): title={}, chunks={}", title, count);
        return count;
    }

    public List<HybridRetriever.ScoredDocument> search(String query, int topK) {
        List<String> queries = queryRewriter.rewrite(query);
        List<HybridRetriever.ScoredDocument> allResults = new ArrayList<>();
        for (String q : queries) {
            allResults.addAll(hybridRetriever.search(q, topK * 2));
        }
        allResults.sort((a, b) -> Double.compare(b.fusionScore(), a.fusionScore()));
        List<HybridRetriever.ScoredDocument> deduplicated = new ArrayList<>();
        Set<Long> seen = new HashSet<>();
        for (HybridRetriever.ScoredDocument doc : allResults) {
            if (seen.add(doc.document().getId())) deduplicated.add(doc);
        }
        var top = deduplicated.stream().limit(topK).toList();
        log.info("RAG 检索完成: query={}, results={}", query, top.size());
        return top;
    }

    public String formatContext(List<HybridRetriever.ScoredDocument> docs) {
        StringBuilder sb = new StringBuilder("## 相关知识库文档\n\n");
        for (int i = 0; i < docs.size(); i++) {
            var d = docs.get(i);
            sb.append("### 文档").append(i + 1).append("：").append(d.document().getTitle())
                    .append(" (相关度:").append(String.format("%.2f", d.fusionScore())).append(")\n");
            sb.append(d.document().getChunkContent()).append("\n\n");
        }
        return sb.toString();
    }

    public void deleteDocument(Long id) {
        var doc = documentMapper.selectById(id);
        if (doc != null && doc.getEmbedding() != null) {
            embeddingStore.remove(doc.getEmbedding());
        }
        documentMapper.deleteById(id);
    }
}
