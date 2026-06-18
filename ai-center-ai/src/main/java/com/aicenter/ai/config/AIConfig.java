package com.aicenter.ai.config;

import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiEmbeddingModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.store.embedding.EmbeddingStore;
import dev.langchain4j.store.embedding.pinecone.PineconeEmbeddingStore;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * AI 核心配置 — LangChain4j Bean 定义
 * <p>
 * LLM: DeepSeek (OpenAI 兼容 API)，免费/超低成本，中文优秀
 * Embedding: text-embedding-v3 (OpenAI 兼容 API，1024 维，SOTA 质量)
 * 向量存储: Pinecone (云托管向量数据库，LangChain4j 原生集成)
 * <p>
 * 模型选择说明：
 * - DeepSeek: 免费/超低成本，中文优秀，OpenAI 兼容 API
 * - text-embedding-3-large: SOTA embedding 质量，1024-dim，中文支持好，
 *   由 langchain4j-open-ai 的 OpenAiEmbeddingModel 原生支持
 * - Pinecone: 全托管向量数据库，无需运维，LangChain4j 提供
 *   PineconeEmbeddingStore 开箱即用
 *
 * @author aicenter
 */
@Configuration
public class AIConfig {

    // ======================== LLM Chat (DeepSeek, OpenAI 兼容) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.llm")
    public LlmProperties llmProperties() {
        return new LlmProperties();
    }

    @Bean
    public OpenAiChatModel chatModel(LlmProperties props) {
        return OpenAiChatModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .temperature(props.getTemperature())
                .maxTokens(props.getMaxTokens())
                .timeout(Duration.ofSeconds(120))
                .logRequests(true)
                .logResponses(true)
                .build();
    }

    @Bean
    public OpenAiStreamingChatModel streamingChatModel(LlmProperties props) {
        return OpenAiStreamingChatModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .temperature(props.getTemperature())
                .maxTokens(props.getMaxTokens())
                .timeout(Duration.ofSeconds(120))
                .build();
    }

    // ======================== Embedding Model (text-embedding-v3) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.embedding")
    public EmbeddingProperties embeddingProperties() {
        return new EmbeddingProperties();
    }

    @Bean
    public EmbeddingModel embeddingModel(EmbeddingProperties props) {
        return OpenAiEmbeddingModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .dimensions(props.getDimensions())
                .timeout(Duration.ofSeconds(60))
                .logRequests(true)
                .logResponses(false)
                .build();
    }

    // ======================== Pinecone Embedding Store ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.pinecone")
    public PineconeProperties pineconeProperties() {
        return new PineconeProperties();
    }

    @Bean
    public EmbeddingStore<dev.langchain4j.data.segment.TextSegment> embeddingStore(
            PineconeProperties props) {
        return PineconeEmbeddingStore.builder()
                .apiKey(props.getApiKey())
                .index(props.getIndex())
                .build();
    }

    // ======================== Properties Classes ========================

    @Data
    public static class LlmProperties {
        private String apiKey;
        private String baseUrl = "https://api.deepseek.com/v1";
        private String model = "deepseek-chat";
        private Double temperature = 0.1;
        private Integer maxTokens = 4096;
    }

    @Data
    public static class EmbeddingProperties {
        private String apiKey;
        private String baseUrl = "https://api.openai.com/v1";
        private String model = "text-embedding-3-large";
        /** 输出向量维度 (text-embedding-3-large: 256-3072, 默认 1024) */
        private Integer dimensions = 1024;
    }

    @Data
    public static class PineconeProperties {
        private String apiKey;
        private String index = "ai-center";
    }
}
