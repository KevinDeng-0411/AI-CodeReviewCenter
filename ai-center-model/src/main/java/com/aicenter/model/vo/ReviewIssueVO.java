package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 单个评审问题视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "评审问题详情")
public class ReviewIssueVO {

    @Schema(description = "评审维度", example = "性能优化")
    private String dimension;

    @Schema(description = "严重等级：Critical/Warning/Info", example = "Warning")
    private String severity;

    @Schema(description = "行号范围", example = "42-45")
    private String lineRange;

    @Schema(description = "问题标题")
    private String title;

    @Schema(description = "问题描述")
    private String description;

    @Schema(description = "修复建议")
    private String suggestion;

    @Schema(description = "建议的修复代码")
    private String fixCode;
}
