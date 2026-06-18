package com.aicenter.ai.rag;

import com.aicenter.common.constant.AiConstants;
import com.aicenter.model.entity.KnowledgeDocument;
import com.aicenter.model.mapper.KnowledgeDocumentMapper;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.model.embedding.EmbeddingModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 混合检索器 (BM25 + 向量检索)
 * <p>
 * BM25（基于关键词的全文匹配）+ 向量检索（语义相似度）的加权融合。
 * 默认权重：BM25=0.3, Vector=0.7
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HybridRetriever {

    private final KnowledgeDocumentMapper documentMapper;
    private final EmbeddingModel embeddingModel;

    private static final double BM25_WEIGHT = AiConstants.BM25_WEIGHT;
    private static final double VECTOR_WEIGHT = AiConstants.VECTOR_WEIGHT;

    /**
     * 混合检索
     *
     * @param query 查询文本（已重写）
     * @param topK  返回 Top-K
     * @return 按融合分数排序的文档列表
     */
    public List<ScoredDocument> search(String query, int topK) {
        // 1. 向量检索
        float[] queryVector = embed(query);

        // 2. BM25 关键字检索（从所有文档中匹配）
        List<KnowledgeDocument> allDocs = documentMapper.selectList(null);

        // 3. 计算每个文档的融合分数
        List<ScoredDocument> scoredDocs = new ArrayList<>();
        for (KnowledgeDocument doc : allDocs) {
            // BM25 分数
            double bm25Score = computeBM25(query, doc.getChunkContent());
            // 向量相似度
            double vectorScore = computeVectorSimilarity(queryVector, doc.getEmbedding());

            // 归一化融合
            double fusionScore = BM25_WEIGHT * bm25Score + VECTOR_WEIGHT * vectorScore;

            if (fusionScore > 0) {
                scoredDocs.add(new ScoredDocument(doc, fusionScore, bm25Score, vectorScore));
            }
        }

        // 4. 按融合分数降序排列
        scoredDocs.sort(Comparator.comparingDouble(ScoredDocument::fusionScore).reversed());
        return scoredDocs.stream().limit(topK).collect(Collectors.toList());
    }

    /**
     * 简化 BM25 计算（TF-IDF 变体）
     */
    private double computeBM25(String query, String content) {
        if (content == null || content.isEmpty()) return 0;

        String contentLower = content.toLowerCase();
        double k1 = 1.5, b = 0.75;
        double avgDocLength = 500; // 平均文档长度（可动态计算）
        double docLength = content.length();
        double score = 0;

        // 对查询中的每个词计算匹配分数
        String[] queryTerms = query.toLowerCase().split("\\s+");
        for (String term : queryTerms) {
            int tf = countOccurrences(contentLower, term);
            if (tf > 0) {
                // 简化 IDF
                double idf = 1.0;
                double numerator = tf * (k1 + 1);
                double denominator = tf + k1 * (1 - b + b * docLength / avgDocLength);
                score += idf * numerator / denominator;
            }
        }
        return Math.min(score, 1.0); // 归一化到 [0, 1]
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
     * 余弦相似度
     */
    private double computeVectorSimilarity(float[] queryVector, String docEmbeddingStr) {
        if (docEmbeddingStr == null || docEmbeddingStr.isEmpty()) return 0;
        try {
            float[] docVector = stringToVector(docEmbeddingStr);
            if (docVector == null || docVector.length != queryVector.length) return 0;

            double dotProduct = 0, normQ = 0, normD = 0;
            for (int i = 0; i < docVector.length; i++) {
                dotProduct += queryVector[i] * docVector[i];
                normQ += queryVector[i] * queryVector[i];
                normD += docVector[i] * docVector[i];
            }
            if (normQ == 0 || normD == 0) return 0;
            return dotProduct / (Math.sqrt(normQ) * Math.sqrt(normD));
        } catch (Exception e) {
            return 0;
        }
    }

    private float[] embed(String text) {
        return embeddingModel.embed(text).content().vector();
    }

    private float[] stringToVector(String str) {
        if (str == null || str.isEmpty()) return null;
        // 简单逗号分隔解析
        String[] parts = str.replace("[", "").replace("]", "").split(",");
        float[] vector = new float[parts.length];
        for (int i = 0; i < parts.length; i++) {
            vector[i] = Float.parseFloat(parts[i].trim());
        }
        return vector;
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
