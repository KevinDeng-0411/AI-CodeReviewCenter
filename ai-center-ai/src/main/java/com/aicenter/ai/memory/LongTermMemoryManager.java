package com.aicenter.ai.memory;

import cn.hutool.json.JSONUtil;
import com.aicenter.common.constant.AiConstants;
import com.aicenter.model.entity.LongTermMemory;
import com.aicenter.model.mapper.LongTermMemoryMapper;
import com.aicenter.model.vo.LongTermMemoryVO;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.model.embedding.EmbeddingModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 长期记忆管理器
 * <p>
 * 「主动录入 + 向量化存储 + 语义相似度召回」
 * - 自动捕获：对话结束后提取关键信息并向量化存储
 * - 语义召回：基于余弦相似度的 Top-K 记忆检索
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LongTermMemoryManager {

    private final LongTermMemoryMapper memoryMapper;
    private final EmbeddingModel embeddingModel;

    /**
     * 手动保存长期记忆
     */
    public LongTermMemory saveMemory(String sessionId, String content, String memoryType,
                                      String metadata) {
        // 1. 向量化
        float[] vector = embed(content);

        // 2. 存储
        LongTermMemory memory = new LongTermMemory()
                .setSessionId(sessionId)
                .setContent(content)
                .setMemoryType(memoryType)
                .setEmbedding(vectorToString(vector))
                .setMetadata(metadata != null ? metadata : "{}");
        memoryMapper.insert(memory);

        log.info("长期记忆已保存: id={}, type={}, content={}", memory.getId(), memoryType,
                content.length() > 50 ? content.substring(0, 50) + "..." : content);
        return memory;
    }

    /**
     * 语义召回 Top-K 记忆
     *
     * @param query     查询文本
     * @param threshold 相似度阈值（0-1）
     * @param topK      返回 Top-K
     * @return 按相似度降序排列的记忆列表
     */
    public List<LongTermMemoryVO> recall(String query, double threshold, int topK) {
        // 1. 查询向量化
        float[] queryVector = embed(query);

        // 2. 从数据库中检索所有长期记忆（生产环境应使用 pgvector 的 <=> 操作符）
        //    这里先用应用层计算，后续可优化为 SQL 层面计算
        List<LongTermMemory> allMemories = memoryMapper.selectList(null);

        // 3. 计算余弦相似度并排序
        List<LongTermMemoryVO> results = new ArrayList<>();
        for (LongTermMemory memory : allMemories) {
            float[] memVector = stringToVector(memory.getEmbedding());
            if (memVector == null) continue;

            double similarity = cosineSimilarity(queryVector, memVector);
            if (similarity >= threshold) {
                LongTermMemoryVO vo = new LongTermMemoryVO();
                vo.setId(memory.getId());
                vo.setContent(memory.getContent());
                vo.setMemoryType(memory.getMemoryType());
                vo.setSimilarity(Math.round(similarity * 10000.0) / 10000.0);
                vo.setCreatedAt(memory.getCreatedAt());
                results.add(vo);
            }
        }

        // 4. 按相似度降序排列
        results.sort(Comparator.comparingDouble(LongTermMemoryVO::getSimilarity).reversed());
        return results.stream().limit(topK).collect(Collectors.toList());
    }

    /**
     * 删除长期记忆
     */
    public void deleteMemory(Long id) {
        memoryMapper.deleteById(id);
    }

    /**
     * 文本向量化
     */
    private float[] embed(String text) {
        Embedding embedding = embeddingModel.embed(text).content();
        return embedding.vector();
    }

    /**
     * 余弦相似度
     */
    private double cosineSimilarity(float[] a, float[] b) {
        if (a.length != b.length) return 0;
        double dotProduct = 0, normA = 0, normB = 0;
        for (int i = 0; i < a.length; i++) {
            dotProduct += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }
        if (normA == 0 || normB == 0) return 0;
        return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    private String vectorToString(float[] vector) {
        return JSONUtil.toJsonStr(vector);
    }

    private float[] stringToVector(String str) {
        if (str == null || str.isEmpty()) return null;
        try {
            // 支持两种格式: JSON 数组 [1.0, 2.0] 或用逗号分隔
            String cleaned = str.trim();
            if (cleaned.startsWith("[")) cleaned = cleaned.substring(1);
            if (cleaned.endsWith("]")) cleaned = cleaned.substring(0, cleaned.length() - 1);
            String[] parts = cleaned.split(",");
            float[] vector = new float[parts.length];
            for (int i = 0; i < parts.length; i++) {
                vector[i] = Float.parseFloat(parts[i].trim());
            }
            return vector;
        } catch (Exception e) {
            log.warn("向量解析失败: {}", e.getMessage());
            return null;
        }
    }
}
