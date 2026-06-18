package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 单元测试生成结果视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "单元测试生成结果")
public class UnitTestVO {

    @Schema(description = "记录 ID")
    private Long id;

    @Schema(description = "项目名称")
    private String projectName;

    @Schema(description = "文件路径")
    private String filePath;

    @Schema(description = "原始代码")
    private String sourceCode;

    @Schema(description = "生成的测试代码")
    private String testCode;

    @Schema(description = "测试框架")
    private String testFramework;

    @Schema(description = "使用的 AI 模型")
    private String aiModel;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
