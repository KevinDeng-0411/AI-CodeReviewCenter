package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * AI 单元测试生成请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "单元测试生成请求")
public class UnitTestRequest {

    @Schema(description = "项目名称", example = "ai-center")
    private String projectName;

    @Schema(description = "文件路径", example = "src/main/java/com/aicenter/service/UserService.java")
    private String filePath;

    @Schema(description = "待生成单测的源代码")
    private String sourceCode;

    @Schema(description = "测试框架", example = "JUnit5")
    private String testFramework;

    @Schema(description = "Prompt 模板 ID（为空则使用默认模板）")
    private Long promptTemplateId;
}
