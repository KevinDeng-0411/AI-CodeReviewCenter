package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 长期记忆保存请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "长期记忆保存请求")
public class MemorySaveRequest {

    @Schema(description = "关联会话 ID")
    private String sessionId;

    @Schema(description = "记忆内容", example = "团队使用 MyBatis-Plus 作为 ORM 框架")
    private String content;

    @Schema(description = "记忆类型", example = "KNOWLEDGE")
    private String memoryType;

    @Schema(description = "附加信息 (JSON)")
    private String metadata;
}
