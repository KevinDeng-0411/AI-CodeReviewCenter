package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 聊天响应视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "聊天响应")
public class ChatResponseVO {

    @Schema(description = "会话 ID")
    private String sessionId;

    @Schema(description = "会话标题（新会话时有值）")
    private String title;

    @Schema(description = "AI 回复内容")
    private String reply;

    @Schema(description = "本轮使用的短期记忆摘要（调试用）")
    private String memorySummary;
}
