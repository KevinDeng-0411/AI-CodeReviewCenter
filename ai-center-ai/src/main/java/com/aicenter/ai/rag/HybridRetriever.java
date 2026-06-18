package com.aicenter.ai.rag;

import com.aicenter.common.constant.AiConstants;
import com.aicenter.model.entity.KnowledgeDocument;
import com.aicenter.model.mapper.KnowledgeDocumentMapper;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.store.embedding.EmbeddingSearchRequest;
import dev.langchain4j.store.embedding.EmbeddingStore;
import dev.langchain4j.store.embedding.EmbeddingMatch;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 混合检索器 — Pinecone 向量检索 + MySQL BM25 全文匹配
 * <p>
 * 默认权重：BM25=0.3, Pinecone Vector=0.7
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HybridRetriever {

    private final KnowledgeDocumentMapper documentMapper;
    private final EmbeddingModel embeddingModel;
    private final EmbeddingStore<TextSegment> embeddingStore;

    private static final double BM25_WEIGHT = AiConstants.BM25_WEIGHT;
    private static final double VECTOR_WEIGHT = AiConstants.VECTOR_WEIGHT;

    /**
     * 混合检索：BM25 (MySQL) + 向量 (Pinecone)
     *
     * @param query 查询文本
     * @param topK  返回 Top-K
     * @return 按融合分数排序的文档列表
     */
    public List<ScoredDocument> search(String query, int topK) {
        // 1. 向量检索 via Pinecone
        Embedding queryEmbedding = embeddingModel.embed(query).content();
        var searchResult = embeddingStore.search(
                EmbeddingSearchRequest.builder()
                        .queryEmbedding(queryEmbedding)
                        .maxResults(topK * 3)   // oversample for fusion
                        .minScore(0.2)
                        .build()
        );

        // 2. 收集 Pinecone 返回的文档 ID 和分数
        Map<Long, Double> pineconeScores = new HashMap<>();
        for (EmbeddingMatch<TextSegment> match : searchResult.matches()) {
            Long docId = extractDocId(match.embeddingId());
            if (docId != null) {
                pineconeScores.merge(docId, match.score(), Math::max);
            }
        }

        // 3. BM25 关键字检索 (MySQL)
        List<KnowledgeDocument> allDocs = documentMapper.selectList(null);

        // 4. 融合分数
        List<ScoredDocument> scoredDocs = new ArrayList<>();
        for (KnowledgeDocument doc : allDocs) {
            double bm25Score = computeBM25(query, doc.getChunkContent());
            double vectorScore = pineconeScores.getOrDefault(doc.getId(), 0.0);
            double fusionScore = BM25_WEIGHT * bm25Score + VECTOR_WEIGHT * vectorScore;

            if (fusionScore > 0) {
                scoredDocs.add(new ScoredDocument(doc, fusionScore, bm25Score, vectorScore));
            }
        }

        // 5. 按融合分数降序
        scoredDocs.sort(Comparator.comparingDouble(ScoredDocument::fusionScore).reversed());
        return scoredDocs.stream().limit(topK).collect(Collectors.toList());
    }

    /**
     * 简化的 BM25 计算（TF-IDF 变体）
     */
    private double computeBM25(String query, String content) {
        if (content == null || content.isEmpty()) return 0;

        String contentLower = content.toLowerCase();
        double k1 = 1.5, b = 0.75;
        double avgDocLength = 500;
        double docLength = content.length();
        double score = 0;

        String[] queryTerms = query.toLowerCase().split("\\s+");
        for (String term : queryTerms) {
            int tf = countOccurrences(contentLower, term);
            if (tf > 0) {
                double idf = 1.0;
                double numerator = tf * (k1 + 1);
                double denominator = tf + k1 * (1 - b + b * docLength / avgDocLength);
                score += idf * numerator / denominator;
            }
        }
        return Math.min(score, 1.0);
    }

    private int countOccurrences(String text, String term) {
        if (term.isEmpty()) return 0;
        int count = 0, index = 0;
        while ((index = text.indexOf(term, index)) != -1) {
            count++;
            index += term.length();
        }
        return count;
    }

    /**
     * 从 Pinecone ID 提取 MySQL 文档 ID
     */
    private Long extractDocId(String embeddingId) {
        if (embeddingId != null && embeddingId.startsWith("doc:")) {
            try {
                return Long.parseLong(embeddingId.substring("doc:".length()));
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return null;
    }

    /**
     * 打分文档
     */
    public record ScoredDocument(
            KnowledgeDocument document,
            double fusionScore,
            double bm25Score,
            double vectorScore
    ) {
    }
}
