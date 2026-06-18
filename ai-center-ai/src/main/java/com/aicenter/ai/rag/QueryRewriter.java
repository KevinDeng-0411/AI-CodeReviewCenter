package com.aicenter.ai.rag;

import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 查询重写器
 * <p>
 * 将用户口语化问题改写为搜索友好格式，并生成 2-3 个变体提高召回率。
 * 例如："这玩意怎么跑起来" → "项目的启动方式和运行步骤"
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class QueryRewriter {

    private final ChatLanguageModel chatModel;

    /**
     * 重写查询 + 生成变体
     *
     * @param originalQuery 用户原始查询
     * @return [改写后的主查询, 变体1, 变体2, ...]
     */
    public List<String> rewrite(String originalQuery) {
        String prompt = """
                你是一个查询优化专家。请将用户的搜索查询改写为更适合文档检索的格式。

                规则：
                1. 修正口语化表达，改为正式技术用语
                2. 补充缺失的上下文关键词
                3. 如果查询过于简短，扩展为完整的技术问题
                4. 生成 2-3 个语义相近但表述不同的变体

                用户查询：%s

                请以 JSON 数组格式返回，第一个为增强后的主查询，后续为变体：
                ["增强主查询", "变体1", "变体2"]
                """.formatted(originalQuery);

        String response = chatModel.generate(prompt);
        return parseQueries(response, originalQuery);
    }

    private List<String> parseQueries(String response, String fallback) {
        try {
            String jsonStr = response.trim();
            int start = jsonStr.indexOf('[');
            int end = jsonStr.lastIndexOf(']');
            if (start != -1 && end != -1 && end > start) {
                jsonStr = jsonStr.substring(start, end + 1);
                // 简单解析 JSON 数组
                List<String> queries = new ArrayList<>();
                String[] parts = jsonStr.substring(1, jsonStr.length() - 1).split("\",\\s*\"");
                for (String part : parts) {
                    queries.add(part.replace("\"", "").trim());
                }
                if (!queries.isEmpty()) {
                    log.debug("查询重写: {} → {} 个变体", fallback, queries.size());
                    return queries;
                }
            }
        } catch (Exception e) {
            log.warn("查询重写解析失败，使用原始查询", e);
        }
        return List.of(fallback);
    }
}
