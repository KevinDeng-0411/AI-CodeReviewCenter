package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * AI Code Review 请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "Code Review 请求")
public class CodeReviewRequest {

    @Schema(description = "项目名称", example = "ai-center")
    private String projectName;

    @Schema(description = "文件路径", example = "src/main/java/com/aicenter/service/UserService.java")
    private String filePath;

    @Schema(description = "原始代码")
    private String sourceCode;

    @Schema(description = "Prompt 模板 ID（为空则使用默认模板）")
    private Long promptTemplateId;
}
