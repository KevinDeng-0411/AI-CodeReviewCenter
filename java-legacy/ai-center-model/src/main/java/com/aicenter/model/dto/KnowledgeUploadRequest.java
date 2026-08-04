package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 知识文档上传请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "知识文档上传请求")
public class KnowledgeUploadRequest {

    @Schema(description = "文档标题", example = "Redis 缓存最佳实践")
    private String title;

    @Schema(description = "文档内容")
    private String content;

    @Schema(description = "来源类型", example = "MANUAL")
    private String sourceType;

    @Schema(description = "所属项目", example = "ai-center")
    private String projectName;
}
