package com.aicenter.ai.memory;

import com.aicenter.common.constant.AiConstants;
import com.aicenter.model.entity.ChatMessage;
import com.aicenter.model.mapper.ChatMessageMapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 短期记忆管理器
 * <p>
 * 基于「滑动窗口 + 摘要 + Redis」的高效短期记忆机制：
 * - 滑动窗口：只保留最近 N 轮对话在上下文中
 * - 摘要触发：对话超过阈值轮时，异步生成历史摘要
 * - Redis 缓存：热数据存 Redis（消息列表 + 摘要），冷数据存 PostgreSQL
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ShortTermMemoryManager {

    private final StringRedisTemplate redisTemplate;
    private final ChatMessageMapper messageMapper;
    private final ChatLanguageModel chatModel;

    private static final int WINDOW_SIZE = AiConstants.DEFAULT_WINDOW_SIZE;
    private static final int SUMMARY_THRESHOLD = AiConstants.DEFAULT_SUMMARY_THRESHOLD;
    private static final String SEP = ":::";

    /**
     * 保存消息到短期记忆
     */
    public void saveMessage(String sessionId, String role, String content) {
        // 1. 保存到 Redis List（最近 N 条）
        String redisKey = AiConstants.REDIS_SESSION_MESSAGES + sessionId;
        String entry = role + SEP + content;
        redisTemplate.opsForList().rightPush(redisKey, entry);
        redisTemplate.expire(redisKey, Duration.ofHours(168)); // 7天

        // 2. 裁剪窗口（保留最近 WINDOW_SIZE 条）
        Long size = redisTemplate.opsForList().size(redisKey);
        if (size != null && size > WINDOW_SIZE) {
            redisTemplate.opsForList().trim(redisKey, -WINDOW_SIZE, -1);
        }

        // 3. 触发摘要（当消息数 >= 阈值时）
        if (size != null && size >= SUMMARY_THRESHOLD && size % 5 == 0) {
            generateSummaryAsync(sessionId);
        }

        // 4. 持久化到 PG
        persistMessage(sessionId, role, content);
    }

    /**
     * 获取上下文窗口（摘要 + 最近消息）
     */
    public String getContextWindow(String sessionId) {
        StringBuilder context = new StringBuilder();

        // 1. 检查是否有摘要
        String summaryKey = AiConstants.REDIS_SESSION_SUMMARY + sessionId;
        String summary = redisTemplate.opsForValue().get(summaryKey);
        if (summary != null && !summary.isEmpty()) {
            context.append("## 历史对话摘要\n").append(summary).append("\n\n");
        }

        // 2. 获取最近消息
        String redisKey = AiConstants.REDIS_SESSION_MESSAGES + sessionId;
        List<String> entries = redisTemplate.opsForList().range(redisKey, 0, -1);
        if (entries != null && !entries.isEmpty()) {
            context.append("## 最近对话\n");
            for (String entry : entries) {
                int sepIdx = entry.indexOf(SEP);
                if (sepIdx > 0) {
                    String role = entry.substring(0, sepIdx);
                    String content = entry.substring(sepIdx + SEP.length());
                    context.append(role).append(": ").append(content).append("\n");
                }
            }
        }

        return context.toString();
    }

    /**
     * 获取消息列表
     */
    public List<MessageEntry> getMessages(String sessionId) {
        String redisKey = AiConstants.REDIS_SESSION_MESSAGES + sessionId;
        List<String> entries = redisTemplate.opsForList().range(redisKey, 0, -1);
        if (entries == null) return List.of();
        List<MessageEntry> result = new ArrayList<>();
        for (String entry : entries) {
            int sepIdx = entry.indexOf(SEP);
            if (sepIdx > 0) {
                result.add(new MessageEntry(
                        entry.substring(0, sepIdx),
                        entry.substring(sepIdx + SEP.length())
                ));
            }
        }
        return result;
    }

    /**
     * 删除会话的短期记忆
     */
    public void clearMemory(String sessionId) {
        redisTemplate.delete(AiConstants.REDIS_SESSION_MESSAGES + sessionId);
        redisTemplate.delete(AiConstants.REDIS_SESSION_SUMMARY + sessionId);
    }

    /**
     * 异步生成对话摘要
     */
    private void generateSummaryAsync(String sessionId) {
        try {
            String summaryKey = AiConstants.REDIS_SESSION_SUMMARY + sessionId;
            String existingSummary = redisTemplate.opsForValue().get(summaryKey);

            List<MessageEntry> messages = getMessages(sessionId);
            if (messages.isEmpty()) return;

            int half = messages.size() / 2;
            List<MessageEntry> toSummarize = messages.subList(0, half);

            String conversation = toSummarize.stream()
                    .map(m -> m.role + ": " + m.content)
                    .collect(Collectors.joining("\n"));

            String prompt = """
                    请将以下对话历史总结为简洁的摘要（200字以内），保留关键信息：
                    %s

                    现有摘要（如有）：%s

                    请合并新旧信息输出最终摘要：
                    """.formatted(conversation, existingSummary != null ? existingSummary : "无");

            String newSummary = chatModel.generate(prompt);
            redisTemplate.opsForValue().set(summaryKey, newSummary, Duration.ofHours(168));
            log.debug("会话摘要已更新: sessionId={}", sessionId);

        } catch (Exception e) {
            log.error("生成摘要失败: sessionId={}", sessionId, e);
        }
    }

    private void persistMessage(String sessionId, String role, String content) {
        try {
            ChatMessage msg = new ChatMessage()
                    .setSessionId(sessionId)
                    .setRole(role)
                    .setContent(content)
                    .setTokenCount(content.length() / 2);
            messageMapper.insert(msg);
        } catch (Exception e) {
            log.warn("持久化消息失败: sessionId={}", sessionId, e);
        }
    }

    /**
     * 消息条目
     */
    public record MessageEntry(String role, String content) {
    }
}
