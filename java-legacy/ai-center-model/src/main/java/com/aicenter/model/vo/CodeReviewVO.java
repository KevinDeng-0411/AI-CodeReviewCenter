package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Code Review 结果视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "Code Review 结果")
public class CodeReviewVO {

    @Schema(description = "记录 ID")
    private Long id;

    @Schema(description = "项目名称")
    private String projectName;

    @Schema(description = "文件路径")
    private String filePath;

    @Schema(description = "整体评分 (0-100)")
    private Integer score;

    @Schema(description = "评审摘要")
    private String summary;

    @Schema(description = "问题总数")
    private Integer issuesCount;

    @Schema(description = "Critical 问题数")
    private Integer criticalCount;

    @Schema(description = "Warning 问题数")
    private Integer warningCount;

    @Schema(description = "Info 问题数")
    private Integer infoCount;

    @Schema(description = "问题列表")
    private List<ReviewIssueVO> issues;

    @Schema(description = "代码亮点")
    private List<String> highlights;

    @Schema(description = "使用的 AI 模型")
    private String aiModel;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
