package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 聊天请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "聊天请求")
public class ChatRequest {

    @Schema(description = "会话 ID（新会话为空）")
    private String sessionId;

    @Schema(description = "用户消息", example = "如何优化这段代码的性能？")
    private String message;
}
