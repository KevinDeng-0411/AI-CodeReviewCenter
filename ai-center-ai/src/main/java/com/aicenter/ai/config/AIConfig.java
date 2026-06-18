package com.aicenter.ai.config;

import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.ollama.OllamaEmbeddingModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * AI 核心配置 — LangChain4j Bean 定义
 * <p>
 * - DeepSeek (OpenAI 兼容 API) → ChatModel (对话/生成)
 * - Ollama → EmbeddingModel (bge-m3 向量化)
 *
 * @author aicenter
 */
@Configuration
public class AIConfig {

    // ======================== DeepSeek Chat (OpenAI 兼容) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.deepseek")
    public DeepSeekProperties deepSeekProperties() {
        return new DeepSeekProperties();
    }

    @Bean
    public OpenAiChatModel chatModel(DeepSeekProperties props) {
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
    public OpenAiStreamingChatModel streamingChatModel(DeepSeekProperties props) {
        return OpenAiStreamingChatModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .temperature(props.getTemperature())
                .maxTokens(props.getMaxTokens())
                .timeout(Duration.ofSeconds(120))
                .build();
    }

    // ======================== Ollama Embedding (bge-m3) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.ollama")
    public OllamaProperties ollamaProperties() {
        return new OllamaProperties();
    }

    @Bean
    public EmbeddingModel embeddingModel(OllamaProperties props) {
        return OllamaEmbeddingModel.builder()
                .baseUrl(props.getBaseUrl())
                .modelName(props.getEmbeddingModel())
                .timeout(Duration.ofSeconds(60))
                .build();
    }

    // ======================== Properties Classes ========================

    @Data
    public static class DeepSeekProperties {
        private String apiKey;
        private String baseUrl = "https://api.deepseek.com/v1";
        private String model = "deepseek-chat";
        private Double temperature = 0.1;
        private Integer maxTokens = 4096;
    }

    @Data
    public static class OllamaProperties {
        private String baseUrl = "http://localhost:11434";
        private String embeddingModel = "bge-m3";
        private String chatModel = "qwen2.5:7b";
    }
}
